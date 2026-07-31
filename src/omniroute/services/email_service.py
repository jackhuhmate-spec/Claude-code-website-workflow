"""
Email service — business logic for email outreach and replies.

Coordinates between Gmail adapter, conversation tracking, and
the LLM classification/reply system.
"""

from __future__ import annotations

import logging
from typing import Any

from omniroute.adapters.email.base import EmailMessage, SendResult, ReceivedEmail, ReadResult
from omniroute.adapters.llm.base import ClassificationResult, LLMProvider
from omniroute.db.session import get_db

log = logging.getLogger("omniroute.services.email")


class EmailService:
    """High-level email operations for the outreach pipeline."""

    def __init__(self, sender, reader, llm: LLMProvider | None = None):
        """Initialize the email service.

        Args:
            sender: EmailSender adapter instance.
            reader: EmailReader adapter instance.
            llm: LLMProvider for classification (can be None for keyword fallback).
        """
        self._sender = sender
        self._reader = reader
        self._llm = llm

    def send_cold_email(self, to: str, subject: str, body: str) -> SendResult:
        """Send a cold email with sign-off and tracking.

        Args:
            to: Recipient email.
            subject: Subject line.
            body: Email body.

        Returns:
            SendResult.
        """
        msg = EmailMessage(to=to, subject=subject, body=body)
        result = self._sender.send(msg)

        if result.success:
            log.info("Cold email sent to %s: '%s'", to, subject)
        else:
            log.warning("Failed to send to %s: %s", to, result.error)

        return result

    def read_replies(self, *, days: int = 3, only_new: bool = True) -> ReadResult:
        """Read replies from the inbox.

        Args:
            days: How many days to scan.
            only_new: Skip already-handled messages.

        Returns:
            ReadResult.
        """
        return self._reader.read_inbox(days=days, only_new=only_new)

    def classify_reply(self, email_msg: ReceivedEmail) -> ClassificationResult | None:
        """Classify a reply using the LLM or keyword fallback.

        Args:
            email_msg: The received email.

        Returns:
            ClassificationResult or None.
        """
        if self._llm and self._llm.is_available():
            result = self._llm.classify_reply(
                subject=email_msg.subject,
                body=email_msg.body[:3000],
                sender=email_msg.from_address,
            )
            if result:
                return result

        # Keyword fallback (mirrors run_cycle.py logic)
        return self._keyword_fallback(email_msg)

    def _keyword_fallback(self, msg: ReceivedEmail) -> ClassificationResult | None:
        """Simple keyword-based classification fallback.

        Args:
            msg: The received email.

        Returns:
            ClassificationResult or None.
        """
        lower = (msg.subject + " " + msg.body).lower()

        if any(p in lower for p in ("unsubscribe", "not interested", "no thanks", "remove me")):
            return ClassificationResult(category="OPTOUT", reason="Keyword: opt-out")

        if any(p in lower for p in ("out of office", "automatic reply", "auto-reply")):
            return ClassificationResult(category="AUTO", reason="Keyword: OOO")

        if any(p in lower for p in ("ignore previous", "ignore all previous", "disregard")):
            return ClassificationResult(category="SUSPICIOUS", reason="Keyword: prompt injection")

        if any(p in lower for p in ("let's do it", "go ahead", "sign me up", "when can you start")):
            return ClassificationResult(category="DEAL", reason="Keyword: deal")

        if any(p in lower for p in ("how much", "price", "cost", "interested", "tell me more")):
            return ClassificationResult(category="INTERESTED", reason="Keyword: price/interest")

        if any(p in lower for p in (
            "too expensive", "too much", "out of my budget", "don't have the budget",
            "can't afford", "overpriced", "a bit steep",
            "already have someone", "already have a guy", "already have a web designer",
            "happy with my current", "not right now", "not at this time",
            "maybe later", "some other time", "not interested at this time",
            "bit busy", "not a priority",
        )):
            return ClassificationResult(category="OBJECTION", reason="Keyword: objection")

        if "?" in msg.body and not any(
            # Exclude objection-style phrases even when they end with ?
            p in lower for p in ("too expensive", "already have", "too much", "why would")
        ):
            return ClassificationResult(category="QUESTION", reason="Keyword: contains ?")

        return ClassificationResult(category="REVIEW", reason="Keyword: default", confidence=0.0)

    def mark_handled(self, message_ids: list[str]) -> int:
        """Mark messages as handled.

        Args:
            message_ids: Message-ID values.

        Returns:
            Count of newly handled messages.
        """
        return self._reader.mark_handled(message_ids)

    def test_connection(self) -> dict[str, Any]:
        """Test email connectivity.

        Returns:
            Dict with smtp/imap status.
        """
        return self._sender.test_connection()
