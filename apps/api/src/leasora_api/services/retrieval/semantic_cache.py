"""Near-duplicate question cache using embedding cosine similarity.

Complements ``QueryCache`` (exact match) by catching semantically-identical
but differently-worded questions ("When is rent due?" vs "What day of the
month is rent owed?"). Every entry is scoped by ``lease_id``, so a match can
never be served across leases — cosine similarity is only computed against
entries stored under the same lease.

Eviction policy: **true LRU via ``OrderedDict``**. A successful ``get``
promotes the matched entry to most-recently-used; a ``set`` that fills the
cache drops the least-recently-used. ``OrderedDict`` handles LRU
promotion.


Config-awareness: every entry carries a ``config_flags`` snapshot; ``get``
ignores entries whose flags differ from the caller's. This mirrors the
contract of ``QueryCache`` so a settings change (rerank toggle, refusal-
threshold update, model swap) cannot serve a stale answer.
"""

import math
from collections import OrderedDict
from threading import Lock
from typing import TYPE_CHECKING

from leasora_api.core.config import get_settings

if TYPE_CHECKING:
    from leasora_api.schemas.response import AskResponse


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two equal-length vectors.

    Returns 0.0 if either vector has zero magnitude (avoids division by zero).
    """
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class _Entry:
    __slots__ = ("lease_id", "embedding", "config_flags", "response")

    def __init__(
        self,
        lease_id: str,
        embedding: list[float],
        config_flags: tuple[object, ...],
        response: "AskResponse",
    ) -> None:
        self.lease_id = lease_id
        self.embedding = embedding
        self.config_flags = config_flags
        self.response = response


class SemanticCache:
    """Bounded LRU near-duplicate cache keyed by embedding similarity, scoped per lease.

    Each entry is also tagged with the retrieval-affecting ``config_flags``
    that produced it, so a config change (rerank toggle, refusal-threshold
    update, model swap) invalidates matching entries on read. This mirrors
    the contract of ``QueryCache`` (see ``query_cache.build_cache_key``).

    Eviction is **true LRU** via ``OrderedDict``: a successful ``get``
    promotes the entry; ``set`` drops the least-recently-used entry once the
    cache exceeds ``max_size``.
    """

    def __init__(self, threshold: float = 0.92, max_size: int = 512):
        self.threshold = threshold
        self.max_size = max_size
        # OrderedDict[int, _Entry] — uses an auto-incrementing counter as the
        # key so we don't need to hash equality-on-vector embeddings.
        self._counter = 0
        self._entries: OrderedDict[int, _Entry] = OrderedDict()
        # Thread-safety: every mutating method takes this lock.
        self._lock = Lock()

    def _next_key(self) -> int:
        # ``_next_key`` is only called from inside ``set``'s lock, so it
        # doesn't need its own acquire; keep the counter protected
        # transitively by ``set``.
        self._counter += 1
        return self._counter

    def get(
        self,
        lease_id: str,
        embedding: list[float],
        config_flags: tuple[object, ...] = (),
    ) -> "AskResponse | None":
        """Find the most similar cached question for this lease above the threshold.

        Only entries whose stored ``config_flags`` matches the requested
        ``config_flags`` are considered. A stale entry (cached under
        different settings) is not returned.

        Args:
            lease_id: The lease being queried (only entries for this lease
                are considered).
            embedding: Embedding of the incoming question.
            config_flags: Retrieval-affecting settings; entries cached under
                a different set of flags are skipped.

        Returns:
            The cached ``AskResponse`` of the best match, or ``None`` if no
            entry for this lease meets the similarity threshold.
        """
        requested_flags = config_flags
        best_score = -1.0
        best_key: int | None = None
        best_response: AskResponse | None = None
        with self._lock:
            for key, entry in self._entries.items():
                if entry.lease_id != lease_id:
                    continue
                if entry.config_flags != requested_flags:
                    # Entry cached under different settings — skip it.
                    continue
                score = cosine_similarity(embedding, entry.embedding)
                if score >= self.threshold and score > best_score:
                    best_score = score
                    best_key = key
                    best_response = entry.response
            # Promote the matched entry to MRU so it isn't evicted before
            # one-hit wonders on subsequent overflow.
            if best_key is not None:
                self._entries.move_to_end(best_key)
            return best_response

    def set(
        self,
        lease_id: str,
        embedding: list[float],
        response: "AskResponse",
        config_flags: tuple[object, ...] = (),
    ) -> None:
        """Store a question embedding + response; evict LRU entry when full."""
        with self._lock:
            key = self._next_key()
            self._entries[key] = _Entry(lease_id, embedding, config_flags, response)
            # Keep dict size at most ``max_size`` by evicting the LRU entry on
            # overflow. OrderedDict.popitem(last=False) is O(1).
            while len(self._entries) > self.max_size:
                self._entries.popitem(last=False)

    def evict_lease(self, lease_id: str) -> int:
        """Evict all cached entries for a lease (e.g. after re-ingest).

        Returns:
            Number of entries evicted.
        """
        with self._lock:
            before = len(self._entries)
            keys_to_remove = [
                key for key, entry in self._entries.items() if entry.lease_id == lease_id
            ]
            for key in keys_to_remove:
                del self._entries[key]
            return before - len(self._entries)

    def clear(self) -> None:
        """Remove all cached entries."""
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


cache = SemanticCache(threshold=get_settings().cache_threshold)
