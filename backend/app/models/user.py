from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    plan: Mapped[str] = mapped_column(String(32), default="free", nullable=False)
    plan_active_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    plan_active_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Brute-force protection & account locking
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    generations = relationship("Generation", back_populates="user", cascade="all, delete-orphan")
    purchases = relationship("PurchaseRequest", back_populates="user", cascade="all, delete-orphan", foreign_keys="PurchaseRequest.user_id")

    def __repr__(self) -> str:
        return f"<User id={self.id} email='{self.email}' plan='{self.plan}' is_admin={self.is_admin}>"
