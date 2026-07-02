from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from app.core.rate_limit import InMemoryRateLimiter
from app.services.application_history import add_application_history
from app.services.auth import is_expired


class DummyDb:
    def __init__(self) -> None:
        self.added = []

    def add(self, value: object) -> None:
        self.added.append(value)


def test_unit_rate_limiter_blocks_after_limit_and_clear_resets() -> None:
    limiter = InMemoryRateLimiter()

    limiter.check("login:127.0.0.1", limit=2, window_seconds=300)
    limiter.check("login:127.0.0.1", limit=2, window_seconds=300)

    with pytest.raises(HTTPException) as exc_info:
        limiter.check("login:127.0.0.1", limit=2, window_seconds=300)

    assert exc_info.value.status_code == 429

    limiter.clear()
    limiter.check("login:127.0.0.1", limit=2, window_seconds=300)


def test_unit_expiry_helper_treats_naive_datetime_as_utc() -> None:
    expires_at = datetime(2026, 1, 1, 12, 0, 0)
    now = datetime(2026, 1, 1, 12, 0, 1, tzinfo=UTC)

    assert is_expired(expires_at, now=now) is True


def test_unit_application_history_rejects_unknown_actions_before_persisting() -> None:
    db = DummyDb()

    with pytest.raises(ValueError, match="unsupported_application_history_action"):
        add_application_history(
            db,  # type: ignore[arg-type]
            user_id=1,
            action_type="resume_raw_text_viewed",
        )

    assert db.added == []
