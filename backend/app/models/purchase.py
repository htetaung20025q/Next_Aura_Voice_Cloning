from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PurchaseRequest(Base):
    __tablename__ = "purchase_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plan: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_mmk: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payment_reference: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)  # pending, approved, rejected

    duration_months: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=1)
    plan_active_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    plan_active_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    approved_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True,
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="purchases")
    approved_by = relationship("User", foreign_keys=[approved_by_user_id])

    __table_args__ = (
        Index("ix_purchases_status_created", "status", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<PurchaseRequest id={self.id} user_id={self.user_id} plan='{self.plan}' status='{self.status}'>"
