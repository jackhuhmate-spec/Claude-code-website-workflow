"""
LLM provider abstraction.

Defines the interface for large language model interactions:
classification, reply generation, and cold email writing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ClassificationResult:
    """Result of classifying an email reply."""

    category: str  # DEAL, INTERESTED, QUESTION, OBJECTION, OPTOUT, AUTO, SUSPICIOUS, REVIEW
    confidence: float = 0.0
    reason: str = ""
    summary: str = ""
    raw: dict[str, Any] | None = None


@dataclass
class GeneratedEmail:
    """A generated cold email."""

    subject: str
    body: str


class LLMProvider(ABC):
    """Abstract interface for LLM interactions."""

    @abstractmethod
    def classify_reply(
        self,
        subject: str,
        body: str,
        sender: str = "",
    ) -> ClassificationResult | None:
        """Classify an email reply into a category.

        Args:
            subject: Email subject line.
            body: Email body text.
            sender: Sender email address.

        Returns:
            ClassificationResult or None if classification failed.
        """
        ...

    @abstractmethod
    def write_reply(
        self,
        category: str,
        subject: str,
        body: str,
        business: str = "",
        sender: str = "",
    ) -> str | None:
        """Write a reply email to a lead.

        Args:
            category: The classification category.
            subject: Original email subject.
            body: Original email body.
            business: Business name.
            sender: Sender email address.

        Returns:
            Reply text or None if generation failed.
        """
        ...

    @abstractmethod
    def write_cold_email(
        self,
        name: str,
        trade: str,
        area: str,
        flaw: str,
        group: str = "A",
    ) -> GeneratedEmail | None:
        """Write a cold outreach email.

        Args:
            name: Business name.
            trade: Business trade/type.
            area: Borough or area.
            flaw: The specific flaw found in auditing.
            group: 'A' (bad site) or 'B' (no site).

        Returns:
            GeneratedEmail or None if generation failed.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the LLM provider is configured and available.

        Returns:
            True if available for use.
        """
        ...
