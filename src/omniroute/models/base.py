"""
SQLAlchemy declarative base and common mixins for all models.

SQLAlchemy is OPTIONAL — core imports work without it. The database
layer only activates when sqlalchemy is installed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("omniroute.models")

# Lazy SQLAlchemy — raises a clear error on first use if missing
_SA_AVAILABLE = False
_Base = object
_TimestampMixin_base = object

try:
    from sqlalchemy import DateTime, MetaData, func
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

    _SA_AVAILABLE = True

    NAMING_CONVENTION: dict[str, str] = {
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    class Base(DeclarativeBase):  # type: ignore[no-redef]
        metadata = metadata

    class TimestampMixin:
        """Adds created_at and updated_at timestamp columns."""

        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True),
            default=lambda: datetime.now(timezone.utc),
            server_default=func.now(),
            nullable=False,
        )
        updated_at: Mapped[datetime | None] = mapped_column(
            DateTime(timezone=True),
            default=None,
            onupdate=lambda: datetime.now(timezone.utc),
            nullable=True,
        )

except ImportError:
    log.info("SQLAlchemy not installed — ORM models disabled.")

    class Base:  # type: ignore[no-redef]
        """Placeholder when SQLAlchemy is not available."""
        metadata = None
        __table__ = None
        __tablename__ = ""

    class TimestampMixin:  # type: ignore[no-redef]
        created_at: datetime = datetime.now(timezone.utc)
        updated_at: datetime | None = None


def require_sa() -> None:
    """Raise ImportError if SQLAlchemy is not installed.

    Call this at the top of any function that needs ORM features.
    """
    if not _SA_AVAILABLE:
        raise ImportError(
            "SQLAlchemy is required for database features. "
            "Install it with: pip install sqlalchemy"
        )


class DictMixin:
    """Adds a ``to_dict()`` method for serialization."""

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if hasattr(self, "__table__") and self.__table__ is not None:
            for col in self.__table__.columns:
                val = getattr(self, col.name)
                if isinstance(val, datetime):
                    val = val.isoformat()
                result[col.name] = val
        return result
