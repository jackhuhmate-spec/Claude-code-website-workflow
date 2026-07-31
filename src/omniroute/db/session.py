"""
Database session management.

Provides engine creation, session factories, and a dependency-injectable
session context manager. Supports PostgreSQL (primary) and SQLite (fallback).

SQLAlchemy is OPTIONAL — a clear error is raised when a DB function is called
without it being installed.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from omniroute.config import settings

log = logging.getLogger("omniroute.db")


def _sa() -> Any:
    """Lazy-import SQLAlchemy, raising a clear error if missing."""
    try:
        import sqlalchemy as sa_mod
        return sa_mod
    except ImportError:
        raise ImportError(
            "SQLAlchemy is required for database features. "
            "Install with: pip install sqlalchemy"
        ) from None


def _orm() -> Any:
    """Lazy-import SQLAlchemy ORM modules."""
    _sa()  # verify installed
    import sqlalchemy.orm as orm_mod
    return orm_mod


def _get_database_url() -> str:
    """Resolve the database URL from settings."""
    if settings.database_url:
        log.info("Using PostgreSQL database.")
        return settings.database_url
    db_path = Path(settings.sqlite_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    log.info("Using SQLite database at %s", db_path)
    return f"sqlite:///{db_path}"


def create_engine_from_url(url: str | None = None, **kwargs: Any) -> Any:
    """Create a SQLAlchemy engine from a URL.

    Args:
        url: Database URL. If ``None``, resolves from settings.
        **kwargs: Additional arguments passed to ``create_engine``.

    Returns:
        Configured SQLAlchemy Engine.
    """
    sa = _sa()
    db_url = url or _get_database_url()
    connect_args: dict[str, Any] = {}

    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine_kw: dict[str, Any] = {}
    if not db_url.startswith("sqlite"):
        engine_kw["pool_size"] = 5
        engine_kw["max_overflow"] = 10
    engine_kw["pool_pre_ping"] = True

    engine = sa.create_engine(
        db_url,
        connect_args=connect_args,
        echo=log.isEnabledFor(logging.DEBUG),
        **engine_kw,
        **kwargs,
    )

    # Enable WAL mode and foreign keys for SQLite
    if db_url.startswith("sqlite"):
        sa.event.listen(engine, "connect", _sqlite_pragma)

    return engine


def _sqlite_pragma(conn: Any, _record: Any) -> None:
    """Enable WAL mode and foreign keys for SQLite connections."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


# Global engine and session factory (lazy-init)
_engine: Any = None
_SessionLocal: Any = None


def get_engine() -> Any:
    """Get or create the global database engine.

    Returns:
        The global SQLAlchemy Engine instance.
    """
    global _engine  # noqa: PLW0603
    if _engine is None:
        _engine = create_engine_from_url()
    return _engine


def get_session_factory() -> Any:
    """Get or create the global session factory.

    Returns:
        The global sessionmaker bound to the engine.
    """
    global _SessionLocal  # noqa: PLW0603
    if _SessionLocal is None:
        orm = _orm()
        _SessionLocal = orm.sessionmaker(
            autocommit=False,
            autoflush=True,
            expire_on_commit=False,
            bind=get_engine(),
        )
    return _SessionLocal


def create_session() -> Any:
    """Create a new database session.

    Returns:
        A new SQLAlchemy Session.
    """
    return get_session_factory()()


@contextmanager
def get_db() -> Generator[Any, None, None]:
    """Context manager that provides a database session with auto-close.

    Usage::

        with get_db() as db:
            leads = db.query(Lead).all()

    The session is committed on success, rolled back on exception.
    """
    session = create_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def test_connection() -> dict[str, Any]:
    """Test the database connection and return diagnostics.

    Returns:
        Dict with connection test results.
    """
    sa = _sa()
    result: dict[str, Any] = {
        "engine": str(get_engine().url),
        "connected": False,
        "version": None,
        "error": None,
    }

    # Mask password in URL for display
    url_str = str(get_engine().url)
    if ":" in url_str and "@" in url_str:
        parts = url_str.split("@")
        user_part = parts[0].split(":")
        result["engine"] = f"{user_part[0]}:***@{parts[1]}"
    elif "sqlite" in url_str:
        result["engine"] = url_str

    try:
        with get_db() as db:
            db.execute(sa.text("SELECT 1"))
            result["connected"] = True
            try:
                version_row = db.execute(
                    sa.text(
                        "SELECT sqlite_version()"
                        if url_str.startswith("sqlite")
                        else "SELECT version()"
                    )
                ).scalar()
                result["version"] = version_row
            except Exception:
                pass
    except Exception as exc:
        result["error"] = str(exc)

    return result
