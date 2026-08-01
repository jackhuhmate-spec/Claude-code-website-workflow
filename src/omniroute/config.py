"""
Configuration management for Omniroute.

Loads settings from environment variables with sensible defaults.
Uses pydantic-settings when available; falls back to simple dataclass.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _find_project_root() -> Path:
    """Find the project root by looking for .git or pyproject.toml.

    Anchor to this file's location (src/omniroute/config.py -> repo root) FIRST so the
    package resolves .env and data paths identically from any working directory —
    a CWD-only walk broke every command when run from a sibling dir (cron, VPS).
    Fall back to the CWD walk only if the package lives outside a repo (pip install).
    """
    here = Path(__file__).resolve()
    for parent in (here.parents[2], here.parents[1], here.parents[0]):
        if (parent / ".git").exists() or (parent / "pyproject.toml").exists():
            return parent
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / ".git").exists() or (parent / "pyproject.toml").exists():
            return parent
    return cwd


PROJECT_ROOT = _find_project_root()


def _env(key: str, default: Any = "") -> Any:
    """Read an env var, trying .env file first."""
    return os.environ.get(key, default)


# Fields whose values are masked in repr/str output to prevent secret leakage.
_SECRET_FIELDS = frozenset({"gmail_app_password", "groq_api_key", "netlify_token"})


@dataclass
class Settings:
    """Application settings loaded from environment variables.

    All settings have sensible defaults. The existing pipeline continues
    to work without any of these being set — they are only required for
    the new structured package features.

    .. note::
       Secret fields (API keys, passwords, tokens) are masked in ``repr()``
       and ``str()`` output to prevent accidental credential leakage in logs.
    """

    # --- Database ---
    database_url: str | None = None
    sqlite_path: str = str(PROJECT_ROOT / "data" / "omniroute.db")

    # --- Email (Gmail) ---
    gmail_user: str = ""
    gmail_app_password: str = ""
    sign_name: str = "Jack"

    # --- LLM ---
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # --- Deployment ---
    netlify_token: str = ""

    # --- Pipeline ---
    daily_email_cap: int = 30
    email_delay_seconds: int = 45
    lead_hunter_max: int = 25
    reply_scan_days: int = 3

    # --- Paths ---
    data_dir: str = str(PROJECT_ROOT)

    # --- Logging ---
    log_level: str = "INFO"
    log_format: str = "text"
    log_file: str | None = None

    # --- Mode ---
    auto_send: bool = False
    paused: bool = False

    def __repr__(self) -> str:
        """Return a safe string representation with secrets masked."""
        fields = []
        for fld in self.__dataclass_fields__:
            val = getattr(self, fld)
            if fld in _SECRET_FIELDS and val:
                val = "****" if isinstance(val, str) and len(val) > 4 else "(empty)"
            fields.append(f"{fld}={val!r}")
        return f"Settings({', '.join(fields)})"

    __str__ = __repr__

    @classmethod
    def from_env(cls) -> Settings:
        """Create Settings from environment variables.

        Also tries to load from ``.env`` file if ``python-dotenv`` is available.
        """
        # Try to load .env file (optional)
        env_path = PROJECT_ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                # Strip 'export ' prefix (common in .env files)
                if line.startswith("export "):
                    line = line[7:].strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip()
                quoted = len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"')
                # Strip inline comments (space before #) ONLY on unquoted values —
                # a quoted value can legitimately contain " #" (e.g. an app password).
                if not quoted:
                    idx = val.find(" #")
                    if idx >= 0:
                        val = val[:idx].rstrip()
                # Strip surrounding quotes (single or double)
                if quoted:
                    val = val[1:-1]
                os.environ.setdefault(key, val)

        s = cls(
            database_url=_env("DATABASE_URL"),
            sqlite_path=_env("SQLITE_PATH", str(PROJECT_ROOT / "data" / "omniroute.db")),
            gmail_user=_env("GMAIL_USER"),
            gmail_app_password=_env("GMAIL_APP_PASSWORD"),
            sign_name=_env("SIGN_NAME", "Jack"),
            groq_api_key=_env("GROQ_API_KEY"),
            groq_model=_env("GROQ_MODEL", "llama-3.3-70b-versatile"),
            netlify_token=_env("NETLIFY_TOKEN"),
            daily_email_cap=int(_env("DAILY_EMAIL_CAP", "30")),
            email_delay_seconds=int(_env("EMAIL_DELAY_SECONDS", "45")),
            lead_hunter_max=int(_env("LEAD_HUNTER_MAX", "25")),
            reply_scan_days=int(_env("REPLY_SCAN_DAYS", "3")),
            data_dir=_env("DATA_DIR", str(PROJECT_ROOT)),
            log_level=_env("LOG_LEVEL", "INFO"),
            log_format=_env("LOG_FORMAT", "text"),
            log_file=_env("LOG_FILE"),
            auto_send=_env("AUTO_SEND", "false").lower() in ("true", "1", "yes"),
            paused=_env("PAUSED", "false").lower() in ("true", "1", "yes"),
        )
        # Warn about missing critical credentials
        if not s.gmail_user:
            print("WARN: GMAIL_USER not set — email features will fail at runtime.", file=sys.stderr)
        if not s.gmail_app_password:
            print("WARN: GMAIL_APP_PASSWORD not set — email features will fail at runtime.", file=sys.stderr)
        if not s.groq_api_key:
            print("WARN: GROQ_API_KEY not set — LLM features will fall back to keyword matching.", file=sys.stderr)
        if not s.netlify_token:
            print("WARN: NETLIFY_TOKEN not set — deploy features will fail at runtime.", file=sys.stderr)
        return s


# Try to use pydantic-settings if available (for validation)
try:
    from pydantic import Field
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class PydanticSettings(BaseSettings):
        """Validated settings via pydantic (optional)."""

        model_config = SettingsConfigDict(
            env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
        )

        database_url: str | None = Field(default=None)
        sqlite_path: str = str(PROJECT_ROOT / "data" / "omniroute.db")
        gmail_user: str = Field(default="")
        gmail_app_password: str = Field(default="")
        sign_name: str = Field(default="Jack")
        groq_api_key: str = Field(default="")
        groq_model: str = Field(default="llama-3.3-70b-versatile")
        netlify_token: str = Field(default="")
        daily_email_cap: int = Field(default=30)
        email_delay_seconds: int = Field(default=45)
        lead_hunter_max: int = Field(default=25)
        reply_scan_days: int = Field(default=3)
        data_dir: str = Field(default=str(PROJECT_ROOT))
        log_level: str = Field(default="INFO")
        log_format: str = Field(default="text")
        log_file: str | None = Field(default=None)
        auto_send: bool = Field(default=False)
        paused: bool = Field(default=False)

    def _load_settings() -> Settings:
        ps = PydanticSettings()
        return Settings(
            database_url=ps.database_url,
            sqlite_path=ps.sqlite_path,
            gmail_user=ps.gmail_user,
            gmail_app_password=ps.gmail_app_password,
            sign_name=ps.sign_name,
            groq_api_key=ps.groq_api_key,
            groq_model=ps.groq_model,
            netlify_token=ps.netlify_token,
            daily_email_cap=ps.daily_email_cap,
            email_delay_seconds=ps.email_delay_seconds,
            lead_hunter_max=ps.lead_hunter_max,
            reply_scan_days=ps.reply_scan_days,
            data_dir=ps.data_dir,
            log_level=ps.log_level,
            log_format=ps.log_format,
            log_file=ps.log_file,
            auto_send=ps.auto_send,
            paused=ps.paused,
        )
except ImportError:
    def _load_settings() -> Settings:
        return Settings.from_env()


# Global singleton — import this everywhere
settings = _load_settings()

# Legacy alias for scripts that still read env vars directly
GMAIL_USER = settings.gmail_user
GMAIL_APP_PASSWORD = settings.gmail_app_password
SIGN_NAME = settings.sign_name
GROQ_API_KEY = settings.groq_api_key
NETLIFY_TOKEN = settings.netlify_token
