from sqlalchemy import Column, Index, String, Integer, DateTime, text
from risk_engine.db.db_setup import Base



class DeviceToken(Base):
    __tablename__ = "device_cookie"

    id = Column(Integer, primary_key=True)

    token_hash = Column(String, nullable=False, unique=True, index=True)

    bound_user_id = Column(String, nullable=False, index=True)
    bound_device_id = Column(String, nullable=False, index=True)

    issued_at_utc = Column(DateTime(timezone=True), nullable=False)
    expires_at_utc = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        # Partial unique index: at most one *active* (revoked=0) token per
        # (user, device) pair. Revoked tokens are excluded so historical rows
        # from previous rotations do not cause constraint violations.
        Index(
            "uq_user_device_active",
            "bound_user_id",
            "bound_device_id",
            unique=True,
            sqlite_where=text("revoked = 0"),
        ),
    )
