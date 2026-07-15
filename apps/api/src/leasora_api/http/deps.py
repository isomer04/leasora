"""FastAPI dependency providers.

Includes a minimal in-process per-IP rate limiter dependency. On a
single-tenant v1, the primary driver is LLM cost control, not public
abuse protection.
"""

import time
from collections import defaultdict
from threading import Lock

from fastapi import Request

from leasora_api.core.config import Settings, get_settings
from leasora_api.core.exceptions import RateLimitError

# Maximum number of distinct client keys to track. Beyond this, the oldest
# (least-recently-seen) key is evicted to prevent unbounded memory growth
# from spoofed X-Forwarded-For headers or many ephemeral clients.
_MAX_TRACKED_CLIENTS = 10_000


async def get_settings_dep() -> Settings:
    """Dependency injection for Settings."""
    return get_settings()


class InMemoryRateLimiter:
    """Simple per-client, per-process token-bucket rate limiter.

    Not distributed and not persistent across restarts — sufficient for a
    single-tenant local deployment where the goal is capping LLM spend, not
    defending against coordinated abuse from many clients/processes.

    Tracks at most ``max_clients`` distinct keys. When the cap is reached,
    the client with the oldest last-seen timestamp is evicted so memory
    stays bounded even under spoofed-header traffic.
    """

    def __init__(self, max_clients: int = _MAX_TRACKED_CLIENTS) -> None:
        self._lock = Lock()
        self._max_clients = max_clients
        # client_key -> list of request timestamps within the current window
        self._requests: dict[str, list[float]] = defaultdict(list)

    def check(self, client_key: str, limit_per_minute: int) -> None:
        """Raise ``RateLimitError`` if ``client_key`` has exceeded the limit.

        Args:
            client_key: Identifier for the caller (e.g. client IP).
            limit_per_minute: Maximum requests allowed per rolling 60s window.

        Raises:
            RateLimitError: If the caller has made more than
                ``limit_per_minute`` requests in the last 60 seconds. The
                exception carries a ``retry_after`` (seconds until the
                oldest timestamp ages out) that the middleware surfaces
                as a ``Retry-After`` response header.
        """
        now = time.monotonic()
        window_start = now - 60.0

        with self._lock:
            timestamps = self._requests[client_key]
            # Drop timestamps outside the rolling window.
            fresh = [t for t in timestamps if t > window_start]
            if len(fresh) >= limit_per_minute:
                self._requests[client_key] = fresh
                # How long until the oldest in-window timestamp ages out and
                # one slot frees up? Always at least 1 second so clients
                # never see ``Retry-After: 0``.
                retry_after = max(1, int(60 - (now - fresh[0])) + 1)
                raise RateLimitError(
                    f"Rate limit exceeded: max {limit_per_minute} requests per minute. "
                    "Please wait and try again.",
                    retry_after=retry_after,
                )
            fresh.append(now)
            self._requests[client_key] = fresh

            # Evict coldest clients if we've exceeded the tracking cap.
            if len(self._requests) > self._max_clients:
                self._evict_cold_clients(now)

    def _evict_cold_clients(self, now: float) -> None:
        """Remove the oldest 10% of tracked clients to stay within cap.

        Called while holding ``_lock``. Evicts clients whose most recent
        request is oldest, which are the least likely to make another
        request soon.
        """
        window_start = now - 60.0
        # First pass: drop any fully-expired entries (no timestamps in window).
        expired = [
            key for key, ts in self._requests.items()
            if not any(t > window_start for t in ts)
        ]
        for key in expired:
            del self._requests[key]

        # If still over cap, drop the 10% with the oldest last-seen time.
        if len(self._requests) > self._max_clients:
            evict_count = max(1, len(self._requests) // 10)
            by_freshness = sorted(
                self._requests.items(),
                key=lambda item: max(item[1]) if item[1] else 0.0,
            )
            for key, _ in by_freshness[:evict_count]:
                del self._requests[key]

    def reset(self) -> None:
        """Clear all tracked request history (primarily for tests)."""
        with self._lock:
            self._requests.clear()


_rate_limiter = InMemoryRateLimiter()


async def enforce_rate_limit(request: Request) -> None:
    """FastAPI dependency: enforce the configured per-client rate limit.

    No-ops when ``settings.rate_limit_enabled`` is False.
    The default is ``True`` so a production deployment is protected from start.
    out via ``LEASORA_RATE_LIMIT_ENABLED=false``.

    Raises:
        RateLimitError: If the client has exceeded
            ``settings.rate_limit_per_minute`` requests in the last 60s.
    """
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return

    client_key = _resolve_client_key(request)
    _rate_limiter.check(client_key, settings.rate_limit_per_minute)


def _resolve_client_key(request: Request) -> str:
    """Resolve a per-client bucket key for rate limiting.

    Prefers the first hop of ``X-Forwarded-For`` (set by reverse proxies like
    nginx/ALB/Cloudflare) over ``request.client.host``, which would otherwise
    be the proxy's own IP for every client behind it. Falls back to a
    per-connection key derived from ``id(request.client)`` instead of a
    single shared ``"unknown"`` bucket, so clientless requests (e.g. test
    transports) don't all collapse into one shared limit.
    """
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return f"unknown-{id(request)}"
