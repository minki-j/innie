"""
Redis-backed token bucket rate limiter for external API calls.

Each API surface gets a named limiter backed by a Redis hash key
`rate_limit:{api}`. Tokens are consumed via an atomic Lua script so
concurrent Prefect task runs never race. If Redis is unreachable the
ConnectionError propagates immediately — there is no fallback.

Usage::

    from utils.rate_limiter import get_rate_limiter

    get_rate_limiter("youtube").acquire()   # blocks until a token is available
    yt_dlp_call(...)
"""

from __future__ import annotations

import time
import logging
from functools import lru_cache

import redis

from config import (
    REDIS_URL,
    YOUTUBE_RATE_LIMIT_CALLS,
    YOUTUBE_RATE_LIMIT_WINDOW,
    OPENAI_RATE_LIMIT_CALLS,
    OPENAI_RATE_LIMIT_WINDOW,
    ANTHROPIC_RATE_LIMIT_CALLS,
    ANTHROPIC_RATE_LIMIT_WINDOW,
    GOOGLE_RATE_LIMIT_CALLS,
    GOOGLE_RATE_LIMIT_WINDOW,
    LANGGRAPH_RATE_LIMIT_CALLS,
    LANGGRAPH_RATE_LIMIT_WINDOW,
)

logger = logging.getLogger(__name__)

# Atomic token-bucket script:
# - Refills tokens proportional to elapsed time since last refill.
# - Consumes one token if available; returns 1 (granted) or 0 (denied).
_LUA_ACQUIRE = """
local key          = KEYS[1]
local capacity     = tonumber(ARGV[1])
local refill_rate  = tonumber(ARGV[2])
local now          = tonumber(ARGV[3])

local data         = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens       = tonumber(data[1]) or capacity
local last_refill  = tonumber(data[2]) or now

local elapsed      = math.max(0, now - last_refill)
local new_tokens   = math.min(capacity, tokens + elapsed * refill_rate)

if new_tokens >= 1 then
    redis.call('HMSET', key, 'tokens', new_tokens - 1, 'last_refill', now)
    redis.call('EXPIRE', key, math.ceil(capacity / refill_rate) * 2)
    return 1
else
    redis.call('HMSET', key, 'tokens', new_tokens, 'last_refill', now)
    redis.call('EXPIRE', key, math.ceil(capacity / refill_rate) * 2)
    return 0
end
"""

_POLL_INTERVAL = 0.25  # seconds between retry polls when no token available


class RedisRateLimiter:
    """
    Token bucket rate limiter backed by Redis.

    Args:
        redis_client: A connected ``redis.Redis`` instance.
        api_name: Logical name used as part of the Redis key (e.g. "youtube").
        max_calls: Bucket capacity — maximum burst size.
        window_seconds: Time window over which ``max_calls`` tokens refill.
        poll_interval: How often (seconds) to re-check when waiting for a token.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        api_name: str,
        max_calls: int,
        window_seconds: int,
        poll_interval: float = _POLL_INTERVAL,
    ) -> None:
        self._redis = redis_client
        self._api_name = api_name
        self._key = f"rate_limit:{api_name}"
        self._capacity = max_calls
        # tokens refilled per second
        self._refill_rate: float = max_calls / window_seconds
        self._poll_interval = poll_interval
        self._script = redis_client.register_script(_LUA_ACQUIRE)

    def acquire(self) -> None:
        """
        Block until a token is available, then consume it.

        Raises ``redis.exceptions.ConnectionError`` if Redis is unreachable.
        """
        while True:
            now = time.time()
            granted = self._script(
                keys=[self._key],
                args=[self._capacity, self._refill_rate, now],
            )
            if granted:
                return
            wait = self._poll_interval
            logger.debug(
                "Rate limit reached for '%s', waiting %.2fs", self._api_name, wait
            )
            time.sleep(wait)


# ── Shared Redis client ───────────────────────────────────────


@lru_cache(maxsize=1)
def _get_redis_client() -> redis.Redis:
    client: redis.Redis = redis.Redis.from_url(REDIS_URL, decode_responses=False)
    client.ping()  # fail fast if unreachable
    return client


# ── Per-API singletons ────────────────────────────────────────

_LIMITERS: dict[str, RedisRateLimiter] = {}


def get_rate_limiter(api_name: str) -> RedisRateLimiter:
    """
    Return (and cache) the ``RedisRateLimiter`` for the given API name.

    Supported names: ``"youtube"``, ``"openai"``, ``"anthropic"``,
    ``"google"``, ``"langgraph"``.
    """
    if api_name not in _LIMITERS:
        client = _get_redis_client()
        configs: dict[str, tuple[int, int]] = {
            "youtube": (YOUTUBE_RATE_LIMIT_CALLS, YOUTUBE_RATE_LIMIT_WINDOW),
            "openai": (OPENAI_RATE_LIMIT_CALLS, OPENAI_RATE_LIMIT_WINDOW),
            "anthropic": (ANTHROPIC_RATE_LIMIT_CALLS, ANTHROPIC_RATE_LIMIT_WINDOW),
            "google": (GOOGLE_RATE_LIMIT_CALLS, GOOGLE_RATE_LIMIT_WINDOW),
            "langgraph": (LANGGRAPH_RATE_LIMIT_CALLS, LANGGRAPH_RATE_LIMIT_WINDOW),
        }
        if api_name not in configs:
            raise ValueError(
                f"Unknown API name '{api_name}'. Valid names: {sorted(configs)}"
            )
        max_calls, window = configs[api_name]
        _LIMITERS[api_name] = RedisRateLimiter(client, api_name, max_calls, window)
    return _LIMITERS[api_name]
