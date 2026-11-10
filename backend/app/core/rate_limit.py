from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Final
import hashlib
import hmac
from functools import lru_cache

from redis import Redis
from redis.exceptions import RedisError

from fastapi import HTTPException, Request, status

from app.core.client_ip import get_client_ip as get_trusted_client_ip
from app.core.config import Settings, get_settings


@dataclass
class RateLimitBucket:
    window_started_at: float
    count: int


class InMemoryRateLimiter:
    """Bounded limiter used only by isolated tests, never production."""

    def __init__(self) -> None:
        self._buckets: dict[str, RateLimitBucket] = {}

    def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = monotonic()
        if len(self._buckets) >= 10000:
            self._buckets = {k: v for k, v in self._buckets.items()
                             if now - v.window_started_at < window_seconds}
            if len(self._buckets) >= 10000:
                raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
        bucket = self._buckets.get(key)
        if bucket is None or now - bucket.window_started_at >= window_seconds:
            self._buckets[key] = RateLimitBucket(window_started_at=now, count=1)
            return

        bucket.count += 1
        if bucket.count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
            )

    def clear(self) -> None:
        self._buckets.clear()


AUTH_RATE_LIMITER: Final = InMemoryRateLimiter()


def _direct_peer_ip(request: Request) -> str:
    return request.client.host[:64] if request.client and request.client.host else "unknown"


def get_client_ip(request: Request, settings: Settings | None = None) -> str:
    resolved_settings = settings or get_settings()
    if resolved_settings.trust_proxy_headers:
        return get_trusted_client_ip(request) or "unknown"
    return _direct_peer_ip(request)


_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return count
"""


@lru_cache(maxsize=4)
def _redis(url: str) -> Redis:
    return Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)


def check_rate_limit(key: str, limit: int, window_seconds: int, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if settings.app_env.lower() == "test":
        AUTH_RATE_LIMITER.check(key, limit, window_seconds)
        return
    digest = hmac.new(settings.session_secret.get_secret_value().encode(), key.encode(), hashlib.sha256).hexdigest()
    try:
        count = _redis(settings.auth_redis_url or settings.redis_url).eval(_LIMIT_SCRIPT, 1, f"rate:{digest}", window_seconds)
    except RedisError as exc:
        # A cache outage must not disable abuse protection.
        raise HTTPException(status_code=503, detail="Service temporarily unavailable.") from exc
    if int(count) > limit:
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.",
                            headers={"Retry-After": str(window_seconds)})


def rate_limit_auth(request: Request, action: str, limit: int = 20, window_seconds: int = 300) -> None:
    check_rate_limit(f"auth:{action}:ip:{get_client_ip(request)}", limit, window_seconds)
    user_id = getattr(request.state, "user_id", None)
    if user_id is not None:
        check_rate_limit(f"auth:{action}:user:{user_id}", limit, window_seconds)
        if action in {"cover-letter-generate", "interview-questions-generate", "recommendation-refresh", "roadmap-create"}:
            check_rate_limit(f"ai:daily:user:{user_id}", 50, 86400)
