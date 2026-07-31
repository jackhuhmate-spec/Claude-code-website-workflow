"""
Customer and subscription ORM models.

A Customer is a Lead that has been converted (said yes, paid or agreed to pay).
Subscriptions track optional monthly care plan payments.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omniroute.models.base import Base, DictMixin, TimestampMixin


class Customer(Base, TimestampMixin, DictMixin):
    """A converted lead — someone who agreed to buy a website."""

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("leads.id"), default=None, unique=True
    )

    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    trade: Mapped[str] = mapped_column(String(128), nullable=False)
    london_area: Mapped[str] = mapped_column(String(128), nullable=False)

    phone: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    email: Mapped[Optional[str]] = mapped_column(String(255), default=None)
    website: Mapped[Optional[str]] = mapped_column(String(512), default=None)

    # Deal terms
    build_price: Mapped[float] = mapped_column(Float, default=449.0, nullable=False)
    deposit_paid: Mapped[float] = mapped_column(Float, default=0.0)
    balance_paid: Mapped[float] = mapped_column(Float, default=0.0)
    payment_status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False
    )  # pending, deposit_paid, paid_in_full

    # Subscription
    has_subscription: Mapped[bool] = mapped_column(Boolean, default=False)
    subscription_monthly: Mapped[float] = mapped_column(Float, default=39.0)
    subscription_active: Mapped[bool] = mapped_column(Boolean, default=False)

    # Dates
    deal_closed_date: Mapped[Optional[date]] = mapped_column(Date, default=None)
    site_launched_date: Mapped[Optional[date]] = mapped_column(Date, default=None)

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, default=None)

    # Relationships
    lead: Mapped[Optional["Lead"]] = relationship(  # type: ignore  # noqa: F821
        "Lead", foreign_keys=[lead_id]
    )
    projects: Mapped[list["Project"]] = relationship(  # type: ignore  # noqa: F821
        "Project", back_populates="customer", cascade="all, delete-orphan"
    )
    subscriptions: Mapped[list["Subscription"]] = relationship(  # type: ignore  # noqa: F821
        "Subscription", back_populates="customer", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Customer {self.id}: {self.business_name}>"


class Subscription(Base, TimestampMixin, DictMixin):
    """Monthly care plan subscription for a customer."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=False
    )

    monthly_amount: Mapped[float] = mapped_column(Float, default=39.0, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Optional[date]] = mapped_column(Date, default=None)
    cancelled_date: Mapped[Optional[date]] = mapped_column(Date, default=None)

    last_payment_date: Mapped[Optional[date]] = mapped_column(Date, default=None)
    next_payment_date: Mapped[Optional[date]] = mapped_column(Date, default=None)
    payment_method: Mapped[Optional[str]] = mapped_column(String(64), default=None)

    notes: Mapped[Optional[str]] = mapped_column(Text, default=None)

    # Relationships
    customer: Mapped["Customer"] = relationship(
        "Customer", back_populates="subscriptions"
    )

    def __repr__(self) -> str:
        return f"<Subscription {self.id}: Customer {self.customer_id} — £{self.monthly_amount}/mo>"
