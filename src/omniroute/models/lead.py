"""
Lead ORM model.

Requires SQLAlchemy. Falls back to a plain dict-based class if unavailable.
"""

from __future__ import annotations

from typing import Any

from omniroute.models.base import _SA_AVAILABLE, require_sa

if _SA_AVAILABLE:
    from datetime import date
    from typing import Optional

    from sqlalchemy import Date, Float, ForeignKey, Integer, String, Text, UniqueConstraint
    from sqlalchemy.orm import Mapped, mapped_column, relationship

    from omniroute.models.base import Base, DictMixin, TimestampMixin

    class Lead(Base, TimestampMixin, DictMixin):
        """A business lead discovered during sourcing."""

        __tablename__ = "leads"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        business_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
        trade: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
        london_area: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

        phone: Mapped[Optional[str]] = mapped_column(String(64), default=None)
        email: Mapped[Optional[str]] = mapped_column(String(255), default=None, index=True)
        website: Mapped[Optional[str]] = mapped_column(String(512), default=None)

        website_score: Mapped[Optional[int]] = mapped_column(Integer, default=None)
        biggest_flaw: Mapped[Optional[str]] = mapped_column(Text, default=None)
        group: Mapped[Optional[str]] = mapped_column(String(4), default=None)

        google_business_profile: Mapped[Optional[str]] = mapped_column(String(512), default=None)
        social_media: Mapped[Optional[str]] = mapped_column(Text, default=None)
        source: Mapped[str] = mapped_column(String(64), default="osm", nullable=False)

        lead_score: Mapped[Optional[float]] = mapped_column(Float, default=None)
        score_notes: Mapped[Optional[str]] = mapped_column(Text, default=None)

        contacted: Mapped[bool] = mapped_column(default=False, nullable=False, index=True)
        replied: Mapped[bool] = mapped_column(default=False, nullable=False)
        opted_out: Mapped[bool] = mapped_column(default=False, nullable=False)
        status: Mapped[str] = mapped_column(String(32), default="new", nullable=False, index=True)

        contacted_date: Mapped[Optional[date]] = mapped_column(Date, default=None)
        converted_to_customer_id: Mapped[Optional[int]] = mapped_column(
            Integer, ForeignKey("customers.id"), default=None
        )

        conversations = relationship(
            "Conversation", back_populates="lead", cascade="all, delete-orphan"
        )
        # customer relationship is defined in Customer.lead (back_populates="conversations")
        # The converted_to_customer_id FK is used for direct lookup without a relationship.

        __table_args__ = (
            UniqueConstraint("email", name="uq_leads_email"),
            UniqueConstraint("business_name", "trade", name="uq_leads_business_trade"),
        )

        def __repr__(self) -> str:
            return f"<Lead {self.id}: {self.business_name} ({self.trade}, {self.london_area})>"
else:
    class Lead:  # type: ignore[no-redef]
        """Placeholder when SQLAlchemy is not available."""
        pass
