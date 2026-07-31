"""
Gmail email adapter — sends via SMTP, reads via IMAP.

Wraps the existing ``ops/gmail.py`` logic into the adapter interface.
Allows the new structured code to use Gmail while preserving the existing
scripts unchanged.
"""

from __future__ import annotations

import csv
import email
import imaplib
import logging
import re
import smtplib
import ssl
import sys
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.message import EmailMessage as EmailMsg
from email.utils import make_msgid, parseaddr
from pathlib import Path
from typing import Any

from omniroute.adapters.email.base import (
    EmailMessage,
    EmailSender,
    EmailService,
    ReadResult,
    ReceivedEmail,
    SendResult,
)
from omniroute.config import settings
from omniroute.exceptions import (
    EmailAuthError,
    EmailRateLimitError,
    EmailRecipientBlocked,
    EmailSendError,
)

log = logging.getLogger("omniroute.adapters.email.gmail")

HERE = Path(__file__).resolve().parent.parent.parent.parent.parent
SENT_LOG = HERE / "sent_log.csv"
HANDLED = HERE / "handled_messages.txt"
DNC = HERE / "do_not_contact.csv"

SIGNOFF = (
    "\n\nBest,\n{name}\n\n(If you'd rather not hear from me, "
    'just reply "no thanks" and I won\'t email again.)'
)

NOISE_PAT = re.compile(
    r"(no-?reply|do-?not-?reply|notifications?@|@notifications\.|mailer-daemon|"
    r"postmaster|@accounts\.google|@mail\.anthropic|@t\.brevo|@email\.neon|"
    r"@render\.com|@mtasv\.net|@github\.com|@netlify\.com|@sendgrid|"
    r"@customer\.io|newsletter|@e\.|@em\.|@mail\.)",
    re.I,
)


class GmailAdapter(EmailService):
    """Send and read email through Gmail SMTP + IMAP.

    Uses the same credentials and data files as the existing ``ops/gmail.py``
    scripts so both can coexist.
    """

    def __init__(self) -> None:
        self._user = settings.gmail_user
        self._pw = settings.gmail_app_password.replace(" ", "")
        self._sign = settings.sign_name or "Jake"
        self._ssl_ctx = ssl.create_default_context()

    # ── Helpers ─────────────────────────────────────────────────────────

    def _need_creds(self) -> None:
        if not self._user or not self._pw:
            raise EmailAuthError(
                "GMAIL_USER and GMAIL_APP_PASSWORD not set.",
            )

    def _decode(self, val: str | None) -> str:
        try:
            return str(make_header(decode_header(val or "")))
        except Exception:
            return val or ""

    def _strip_html(self, html: str) -> str:
        h = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", html)
        h = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</tr>", "\n", h)
        h = re.sub(r"(?s)<!--.*?-->", " ", h)
        h = re.sub(r"(?s)<[^>]+>", " ", h)
        import html as _html

        h = _html.unescape(h)
        h = re.sub(r"[​-‏﻿ ]", " ", h)
        h = re.sub(r"[ \t]+", " ", h)
        h = re.sub(r"\n\s*\n\s*\n+", "\n\n", h)
        return h.strip()

    def _body_of(self, msg: email.message.Message) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/plain" and "attachment" not in str(
                    part.get("Content-Disposition", "")
                ):
                    try:
                        return part.get_payload(decode=True).decode(
                            part.get_content_charset() or "utf-8", "replace"
                        )
                    except Exception:
                        continue
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    try:
                        return self._strip_html(
                            part.get_payload(decode=True).decode(
                                part.get_content_charset() or "utf-8", "replace"
                            )
                        )
                    except Exception:
                        continue
            return ""
        try:
            raw = msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", "replace"
            )
        except Exception:
            raw = str(msg.get_payload())
        return self._strip_html(raw) if "<" in raw and ">" in raw else raw

    def _known_recipients(self) -> set[str]:
        out: set[str] = set()
        if SENT_LOG.exists():
            with SENT_LOG.open(newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    addr = (row.get("Email") or "").strip().lower()
                    if addr and "@" in addr:
                        out.add(addr)
        return out

    def _opted_out(self) -> set[str]:
        out: set[str] = set()
        if DNC.exists():
            for line in DNC.read_text(encoding="utf-8").splitlines():
                addr = line.split(",")[0].strip().lower()
                if addr and "@" in addr:
                    out.add(addr)
        return out

    def _handled_ids(self) -> set[str]:
        if HANDLED.exists():
            return {
                l.strip()
                for l in HANDLED.read_text(encoding="utf-8").splitlines()
                if l.strip()
            }
        return set()

    # ── EmailSender ─────────────────────────────────────────────────────

    def send(self, message: EmailMessage) -> SendResult:
        """Send an email via Gmail SMTP.

        Args:
            message: The email to send.

        Returns:
            SendResult indicating success or failure.

        Raises:
            EmailAuthError: If credentials are missing.
            EmailRecipientBlocked: If recipient is on the opt-out list.
        """
        self._need_creds()
        to = message.to.strip().lower()

        if to in self._opted_out():
            return SendResult(
                success=False,
                to=to,
                subject=message.subject,
                error="Recipient is on do-not-contact list",
            )
        # Reply guard: never mail a stranger. Only addresses we've already emailed
        # (sent_log.csv) may be mailed, unless force is set for a deliberately
        # verified new recipient. Without this, a prompt-injected inbound email
        # could make the adapter mail an arbitrary address.
        if not message.force and to not in self._known_recipients():
            return SendResult(
                success=False,
                to=to,
                subject=message.subject,
                error=f"Blocked by reply guard: {to} not in sent_log.csv (use force for a verified new recipient)",
            )

        msg = EmailMsg()
        msg["From"] = f"{message.from_name} <{self._user}>"
        msg["To"] = to
        msg["Subject"] = message.subject
        msg["Message-ID"] = make_msgid(domain="gmail.com")
        if message.in_reply_to:
            msg["In-Reply-To"] = message.in_reply_to
            msg["References"] = message.in_reply_to

        body = message.body
        # Cold emails get the sign-off; in-thread replies already carry one (the
        # drafter writes it), so appending again would double-sign and double the
        # unsubscribe boilerplate.
        if not message.in_reply_to:
            body += SIGNOFF.format(name=message.from_name)
        msg.set_content(body)

        try:
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as s:
                s.starttls(context=self._ssl_ctx)
                s.login(self._user, self._pw)
                s.send_message(msg)
            log.info("Sent to %s: %s", to, message.subject)
            return SendResult(
                success=True,
                to=to,
                subject=message.subject,
                message_id=msg["Message-ID"],
            )
        except smtplib.SMTPAuthenticationError:
            raise EmailAuthError("Gmail SMTP authentication failed.") from None
        except smtplib.SMTPSenderRefused as exc:
            raise EmailSendError(f"Gmail refused send: {exc}") from exc
        except smtplib.SMTPDataError as exc:
            if "rate" in str(exc).lower():
                raise EmailRateLimitError("Gmail rate limit hit.") from exc
            raise EmailSendError(f"SMTP data error: {exc}") from exc
        except Exception as exc:
            raise EmailSendError(f"Failed to send: {exc}") from exc

    def test_connection(self) -> dict[str, Any]:
        """Test Gmail SMTP and IMAP connectivity.

        Returns:
            Dict with 'smtp', 'imap', and diagnostic keys.
        """
        self._need_creds()
        result: dict[str, Any] = {"smtp": "FAIL", "imap": "FAIL", "user": self._user}
        try:
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as s:
                s.starttls(context=self._ssl_ctx)
                s.login(self._user, self._pw)
            result["smtp"] = "OK"
        except Exception as exc:
            result["smtp"] = f"FAIL: {exc}"

        try:
            m = imaplib.IMAP4_SSL("imap.gmail.com", 993, ssl_context=self._ssl_ctx)
            m.login(self._user, self._pw)
            m.select("INBOX")
            m.logout()
            result["imap"] = "OK"
        except Exception as exc:
            result["imap"] = f"FAIL: {exc}"

        result["known_recipients"] = len(self._known_recipients())
        result["opted_out"] = len(self._opted_out())
        return result

    # ── EmailReader ─────────────────────────────────────────────────────

    def read_inbox(
        self,
        *,
        days: int = 3,
        only_new: bool = True,
        include_noise: bool = False,
    ) -> ReadResult:
        """Read messages from the Gmail inbox via IMAP.

        Args:
            days: How many days back to scan.
            only_new: If True, skip already-handled messages.
            include_noise: If True, include machine/notification emails.

        Returns:
            ReadResult with ReceivedEmail objects.
        """
        self._need_creds()
        handled = self._handled_ids() if only_new else set()
        known = self._known_recipients()
        out: list[ReceivedEmail] = []

        try:
            m = imaplib.IMAP4_SSL("imap.gmail.com", 993, ssl_context=self._ssl_ctx)
            m.login(self._user, self._pw)
            m.select("INBOX")

            since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
                "%d-%b-%Y"
            )
            _typ, data = m.search(None, f'(SINCE "{since}")')
            ids = data[0].split()

            for i in reversed(ids[-200:]):
                _typ, d = m.fetch(i, "(RFC822)")
                if _typ != "OK" or not d or not d[0]:
                    continue

                msg = email.message_from_bytes(d[0][1])
                mid = (msg.get("Message-ID") or "").strip()

                if only_new and mid in handled:
                    continue

                from_addr = parseaddr(msg.get("From", ""))[1].lower()
                if from_addr == self._user.lower():
                    continue

                is_known = from_addr in known
                is_machine = bool(NOISE_PAT.search(from_addr))

                if is_machine and not is_known and not include_noise:
                    continue

                out.append(
                    ReceivedEmail(
                        message_id=mid,
                        from_address=from_addr,
                        from_name=self._decode(msg.get("From", "")),
                        subject=self._decode(msg.get("Subject", "")),
                        body=self._body_of(msg).strip()[:4000],
                        date=msg.get("Date", ""),
                        known_sender=is_known,
                        machine=is_machine,
                        already_replied=False,
                    )
                )

            m.logout()
        except imaplib.IMAP4.error as exc:
            raise EmailAuthError(f"IMAP authentication failed: {exc}") from exc
        except Exception as exc:
            log.exception("Failed to read inbox: %s", exc)
            return ReadResult(
                messages=out,
                total_scanned=len(ids) if ids else 0,
                new_count=len(out),
                error=str(exc),
            )

        return ReadResult(
            messages=out,
            total_scanned=len(ids) if ids else 0,
            new_count=len(out),
        )

    def mark_handled(self, message_ids: list[str]) -> int:
        """Mark messages as handled (append-only, concurrency-safe).

        Args:
            message_ids: List of Message-ID values to mark.

        Returns:
            Number of messages newly marked.
        """
        existing = self._handled_ids()
        new = [x.strip() for x in message_ids if x.strip() and x.strip() not in existing]
        if new:
            with HANDLED.open("a", encoding="utf-8") as f:
                f.write("\n".join(new) + "\n")
        return len(new)
