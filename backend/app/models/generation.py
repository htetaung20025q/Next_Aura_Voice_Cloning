from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


FREE_ONCE_PREDICATE = (
    "plan = 'free' AND status IN ('reserved', 'completed') AND user_id IS NOT NULL"
)


class Generation(Base):
    __tablename__ = "generations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    anonymous_identifier: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    plan: Mapped[str] = mapped_column(String(32), nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)  # reserved, completed, failed
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
        index=True,
    )

    # Relationships
    user = relationship("User", back_populates="generations")

    __table_args__ = (
        Index("ix_generations_user_created", "user_id", "created_at"),
        Index("ix_generations_anon_created", "anonymous_identifier", "created_at"),
        # Database-enforced "1 free generation per user": only one reserved/completed
        # free row may exist per user. Failed rows are excluded so retries stay possible.
        Index(
            "uq_generations_free_once_per_user",
            "user_id",
            unique=True,
            sqlite_where=text(FREE_ONCE_PREDICATE),
            postgresql_where=text(FREE_ONCE_PREDICATE),
        ),
    )

    def __repr__(self) -> str:
        return f"<Generation id={self.id} user_id={self.user_id} plan='{self.plan}' word_count={self.word_count} status='{self.status}'>"
