from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Final

from fastapi import HTTPException, Request, status


@dataclass
class RateLimitBucket:
    window_started_at: float
    count: int


class InMemoryRateLimiter:
    """Small fixed-window limiter for sensitive endpoints.

    This is intentionally local-process only. A Redis-backed limiter should replace it
    when the deployment moves beyond a single backend process.
    """

    def __init__(self) -> None:
        self._buckets: dict[str, RateLimitBucket] = {}

    def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = monotonic()
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


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()[:64]
    if request.client and request.client.host:
        return request.client.host[:64]
    return "unknown"


def rate_limit_auth(request: Request, action: str, limit: int = 20, window_seconds: int = 300) -> None:
    AUTH_RATE_LIMITER.check(f"auth:{action}:{get_client_ip(request)}", limit, window_seconds)
