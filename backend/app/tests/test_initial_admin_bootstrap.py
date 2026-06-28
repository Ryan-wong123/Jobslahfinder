from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.account import User, UserProfile
from app.models.audit import AuditLog
from app.models.enums import UserRole
from app.security.passwords import verify_password
from app.services.admin_bootstrap import InitialAdminCreationError, create_initial_admin


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [User.__table__, UserProfile.__table__, AuditLog.__table__]
    Base.metadata.create_all(bind=engine, tables=tables)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine, tables=tables)
        engine.dispose()


def test_create_initial_admin_hashes_prompted_password_and_audits(
    db_session: Session,
) -> None:
    user = create_initial_admin(
        db_session,
        email="Admin@Example.COM",
        password="StrongAdminPass123",
    )

    assert user.email == "admin@example.com"
    assert user.role == UserRole.ADMIN.value
    assert user.profile is not None
    assert user.password_hash != "StrongAdminPass123"
    assert verify_password("StrongAdminPass123", user.password_hash)

    audit = db_session.scalar(select(AuditLog).where(AuditLog.event_type == "admin.initial_admin_create"))
    assert audit is not None
    assert audit.outcome == "SUCCESS"
    assert audit.user_id == user.id
    assert "StrongAdminPass123" not in str(audit.details_json)


def test_create_initial_admin_rejects_second_admin(db_session: Session) -> None:
    create_initial_admin(
        db_session,
        email="admin@example.com",
        password="StrongAdminPass123",
    )

    with pytest.raises(InitialAdminCreationError):
        create_initial_admin(
            db_session,
            email="second-admin@example.com",
            password="AnotherStrongPass123",
        )

    admins = db_session.scalars(select(User).where(User.role == UserRole.ADMIN.value)).all()
    assert len(admins) == 1


def test_create_initial_admin_uses_password_strength_validation(db_session: Session) -> None:
    with pytest.raises(ValueError):
        create_initial_admin(
            db_session,
            email="admin@example.com",
            password="weak",
        )

    assert db_session.scalar(select(User)) is None
