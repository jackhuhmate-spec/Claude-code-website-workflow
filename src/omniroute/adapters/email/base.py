"""
Email sender abstraction.

Defines the interface for sending and reading emails. Implementations
can use Gmail SMTP/IMAP, SendGrid, Brevo, or any other provider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EmailMessage:
    """An email to send."""

    to: str
    subject: str
    body: str
    from_name: str = "Jake"
    from_email: str = ""
    in_reply_to: str | None = None
    thread_id: str | None = None
    message_id: str | None = None


@dataclass
class ReceivedEmail:
    """An email received from the inbox."""

    message_id: str
    from_address: str
    from_name: str
    subject: str
    body: str
    date: str
    known_sender: bool = False
    machine: bool = False
    already_replied: bool = False
    thread_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SendResult:
    """Result of sending an email."""

    success: bool
    to: str
    subject: str
    message_id: str | None = None
    error: str | None = None


@dataclass
class ReadResult:
    """Result of reading the inbox."""

    messages: list[ReceivedEmail]
    total_scanned: int
    new_count: int
    error: str | None = None


class EmailSender(ABC):
    """Abstract interface for sending emails."""

    @abstractmethod
    def send(self, message: EmailMessage) -> SendResult:
        """Send an email.

        Args:
            message: The email to send.

        Returns:
            SendResult indicating success or failure.
        """
        ...

    @abstractmethod
    def test_connection(self) -> dict[str, Any]:
        """Test the email provider connection.

        Returns:
            Dict with 'smtp' and 'imap' status keys.
        """
        ...


class EmailReader(ABC):
    """Abstract interface for reading emails from an inbox."""

    @abstractmethod
    def read_inbox(
        self,
        *,
        days: int = 3,
        only_new: bool = True,
        include_noise: bool = False,
    ) -> ReadResult:
        """Read messages from the inbox.

        Args:
            days: How many days back to scan.
            only_new: Only return unhandled messages.
            include_noise: Include machine/notification emails.

        Returns:
            ReadResult with the messages found.
        """
        ...

    @abstractmethod
    def mark_handled(self, message_ids: list[str]) -> int:
        """Mark messages as handled so they won't be reprocessed.

        Args:
            message_ids: List of Message-ID values to mark.

        Returns:
            Number of messages newly marked.
        """
        ...

    @abstractmethod
    def test_connection(self) -> dict[str, Any]:
        """Test the inbox reader connection.

        Returns:
            Dict with status information.
        """
        ...


class EmailService(EmailSender, EmailReader, ABC):
    """Combined email sender + reader interface."""
