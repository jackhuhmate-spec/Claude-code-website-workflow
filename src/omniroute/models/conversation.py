"""
Conversation and Message ORM models.

Tracks full e-mail conversation history with leads and customers.
Enables context-aware replies and follow-up scheduling.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omniroute.models.base import Base, DictMixin, TimestampMixin


class Conversation(Base, TimestampMixin, DictMixin):
    """A conversation thread with a lead or customer."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("leads.id"), default=None, index=True
    )
    customer_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("customers.id"), default=None, index=True
    )

    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    thread_id: Mapped[Optional[str]] = mapped_column(
        String(255), default=None, unique=True
    )  # Email Message-ID for threading
    status: Mapped[str] = mapped_column(
        String(32), default="active", nullable=False
    )  # active, waiting, closed

    category: Mapped[Optional[str]] = mapped_column(
        String(32), default=None
    )  # interested, question, objection, deal, etc.

    # Relationships
    lead: Mapped[Optional["Lead"]] = relationship(  # type: ignore  # noqa: F821
        "Lead", back_populates="conversations", foreign_keys=[lead_id]
    )
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan",
        order_by="Message.sent_at",
    )

    def __repr__(self) -> str:
        return (
            f"<Conversation {self.id}: {self.subject[:40]} "
            f"(Lead {self.lead_id})>"
        )


class Direction:
    """Direction constants for messages."""

    OUTBOUND = "outbound"
    INBOUND = "inbound"


class Message(Base, TimestampMixin, DictMixin):
    """A single email message within a conversation."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id"), nullable=False, index=True
    )

    message_id: Mapped[Optional[str]] = mapped_column(
        String(255), default=None, unique=True
    )  # RFC 2822 Message-ID
    in_reply_to: Mapped[Optional[str]] = mapped_column(String(255), default=None)
    references: Mapped[Optional[str]] = mapped_column(Text, default=None)

    direction: Mapped[str] = mapped_column(
        String(16), nullable=False, default=Direction.OUTBOUND
    )  # outbound or inbound
    from_address: Mapped[str] = mapped_column(String(255), nullable=False)
    to_address: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    body_html: Mapped[Optional[str]] = mapped_column(Text, default=None)

    sent_at: Mapped[Optional[str]] = mapped_column(
        String(64), default=None
    )  # ISO 8601 datetime string

    was_auto_reply: Mapped[bool] = mapped_column(default=False)
    classification: Mapped[Optional[str]] = mapped_column(
        String(32), default=None
    )  # The LLM classification if inbound
    classification_confidence: Mapped[Optional[float]] = mapped_column(
        default=None
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="messages"
    )

    def __repr__(self) -> str:
        return (
            f"<Message {self.id}: [{self.direction}] "
            f"{self.subject[:40]}>"
        )
