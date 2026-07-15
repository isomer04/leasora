"""Exact-hash answer cache, scoped per lease.

Caches ``AskResponse`` objects keyed by a hash of
``(lease_id, normalized_question, config_flags)`` so repeated identical
questions against the same lease skip retrieval + the LLM call entirely.
Bounded LRU eviction keeps memory use predictable. Every entry is scoped by
``lease_id`` so no answer can ever be served across leases, and
``evict_lease`` lets the ingest pipeline invalidate a lease's entries after
a new upload/re-ingest without needing to know cache internals.
"""

import hashlib
import re
from collections import OrderedDict
from threading import Lock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from leasora_api.schemas.response import AskResponse

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_question(question: str) -> str:
    """Normalize a question for cache-key purposes.

    Lowercases and collapses whitespace so trivially different phrasings
    ("When is rent due?" vs "when  is rent due ?") hit the same cache entry.
    """
    return _WHITESPACE_RE.sub(" ", question.strip().lower())


def build_cache_key(lease_id: str, question: str, config_flags: tuple[object, ...]) -> str:
    """Build a stable hash key for an exact-match cache lookup.

    Args:
        lease_id: The lease being queried.
        question: The raw question text (normalized internally).
        config_flags: Retrieval config values that affect the answer (e.g.
            rerank/hybrid enabled, refusal_threshold) so toggling config
            doesn't silently serve a stale answer computed under different
            settings.

    Returns:
        A SHA256 hex digest suitable for use as a dict key.
    """
    normalized_question = normalize_question(question)
    payload = f"{lease_id}|{normalized_question}|{config_flags}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class QueryCache:
    """Bounded LRU exact-match cache for ``AskResponse`` objects, scoped by lease.

    Thread-safe: every mutating method (``get`` promotes, ``set`` writes +
    evicts, ``evict_lease`` iterates-and-deletes, ``clear`` empties,
    ``__len__`` reads) is guarded by a single ``threading.Lock``. The
    ``asyncio.to_thread`` calls in the retrieval hot path can otherwise
    race a re-ingest's ``evict_lease`` and corrupt the OrderedDict
    (RuntimeError: dictionary changed size during iteration).
    """

    def __init__(self, max_size: int = 256):
        self.max_size = max_size
        self._store: OrderedDict[str, tuple[str, "AskResponse"]] = OrderedDict()
        self._lock = Lock()

    def get(
        self, lease_id: str, question: str, config_flags: tuple[object, ...] = ()
    ) -> "AskResponse | None":
        """Look up a cached response for an exact question match.

        Returns:
            The cached ``AskResponse``, or ``None`` on a cache miss.
        """
        key = build_cache_key(lease_id, question, config_flags)
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            stored_lease_id, response = entry
            if stored_lease_id != lease_id:
                # Defensive: should be unreachable since lease_id is part of the
                # hash input, but never serve a cross-lease answer under any
                # circumstance.
                return None
            self._store.move_to_end(key)
            return response

    def set(
        self,
        lease_id: str,
        question: str,
        response: "AskResponse",
        config_flags: tuple[object, ...] = (),
    ) -> None:
        """Store a response in the cache, evicting the LRU entry if full."""
        key = build_cache_key(lease_id, question, config_flags)
        with self._lock:
            self._store[key] = (lease_id, response)
            self._store.move_to_end(key)
            while len(self._store) > self.max_size:
                self._store.popitem(last=False)

    def evict_lease(self, lease_id: str) -> int:
        """Evict all cached entries for a lease (e.g. after re-ingest).

        Returns:
            Number of entries evicted.
        """
        with self._lock:
            keys_to_remove = [
                key
                for key, (stored_lease_id, _) in self._store.items()
                if stored_lease_id == lease_id
            ]
            for key in keys_to_remove:
                del self._store[key]
            return len(keys_to_remove)

    def clear(self) -> None:
        """Remove all cached entries."""
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


query_cache = QueryCache()
