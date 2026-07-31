"""
Omniroute exception hierarchy.

All custom exceptions inherit from OmnirouteError so callers can catch
a single base type when they don't need specific handling.
"""


class OmnirouteError(Exception):
    """Base exception for all Omniroute errors."""

    def __init__(self, message: str = "", *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause


# ── Configuration ──────────────────────────────────────────────────────


class ConfigurationError(OmnirouteError):
    """Missing or invalid configuration."""


class MissingCredentialError(ConfigurationError):
    """A required credential (API key, password) was not set."""


# ── Data / Leads ───────────────────────────────────────────────────────


class LeadError(OmnirouteError):
    """Base for lead-related errors."""


class LeadNotFoundError(LeadError):
    """Requested lead does not exist."""


class DuplicateLeadError(LeadError):
    """Lead already exists in the database."""


class LeadValidationError(LeadError):
    """Lead data failed validation."""


# ── Email ──────────────────────────────────────────────────────────────


class EmailError(OmnirouteError):
    """Base for email-related errors."""


class EmailAuthError(EmailError):
    """SMTP/IMAP authentication failure."""


class EmailSendError(EmailError):
    """Failed to send an email."""


class EmailRateLimitError(EmailError):
    """Daily email cap reached or rate-limited by provider."""


class EmailRecipientBlocked(EmailError):
    """Recipient is on the do-not-contact list."""


# ── Deployment ─────────────────────────────────────────────────────────


class DeployError(OmnirouteError):
    """Base for deployment-related errors."""


class NetlifyError(DeployError):
    """Netlify API returned an error."""


# ── Agents ─────────────────────────────────────────────────────────────


class AgentError(OmnirouteError):
    """Base for agent-related errors."""


class AgentTimeoutError(AgentError):
    """Agent execution exceeded the timeout."""


class AgentStateError(AgentError):
    """Agent state is invalid or corrupted."""


class AgentExecutionError(AgentError):
    """Agent subprocess or execution failed."""


# ── Database ───────────────────────────────────────────────────────────


class DatabaseError(OmnirouteError):
    """Base for database-related errors."""


class MigrationError(DatabaseError):
    """Database migration failed."""


class ConnectionError(DatabaseError):
    """Database connection failed."""


# ── Adapters ───────────────────────────────────────────────────────────


class AdapterError(OmnirouteError):
    """Base for adapter (external provider) errors."""


class AdapterNotConfigured(AdapterError):
    """Adapter was called but not configured (missing credential/API key)."""
