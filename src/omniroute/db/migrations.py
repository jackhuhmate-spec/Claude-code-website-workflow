"""
Database schema creation and migration.

Creates all tables on startup if they don't exist. Intentionally simple —
avoids the full Alembic dependency. SQLAlchemy is OPTIONAL.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("omniroute.db.migrations")


def _sa() -> Any:
    """Lazy-import SQLAlchemy."""
    try:
        import sqlalchemy as sa_mod
        return sa_mod
    except ImportError:
        raise ImportError(
            "SQLAlchemy is required for database features. "
            "Install with: pip install sqlalchemy"
        ) from None


def table_exists(engine: Any, table_name: str) -> bool:
    """Check if a table exists in the database.

    Args:
        engine: SQLAlchemy Engine.
        table_name: Name of the table to check.

    Returns:
        True if the table exists.
    """
    sa_inspect = _sa().inspect(engine)
    return table_name in sa_inspect.get_table_names()


def run_migrations(engine: Any | None = None, verbose: bool = True) -> dict[str, Any]:
    """Create all tables that don't exist yet.

    Uses ``Base.metadata.create_all()`` which is safe to run repeatedly.

    Args:
        engine: SQLAlchemy Engine. If ``None``, uses the global engine.
        verbose: If ``True``, log table creation details.

    Returns:
        Dict with migration results.
    """
    from omniroute.db.session import get_engine
    from omniroute.models.base import _SA_AVAILABLE

    if not _SA_AVAILABLE:
        return {"success": False, "error": "SQLAlchemy not installed"}

    from omniroute.models import Base

    eng = engine or get_engine()
    result: dict[str, Any] = {
        "tables_created": [],
        "tables_existing": [],
        "success": True,
        "error": None,
    }

    try:
        sa_inspect = _sa().inspect(eng)
        existing = set(sa_inspect.get_table_names())
        all_tables = sorted(Base.metadata.tables.keys())
        result["tables_existing"] = [t for t in all_tables if t in existing]
        result["tables_created"] = [t for t in all_tables if t not in existing]

        Base.metadata.create_all(eng)

        if verbose and result["tables_created"]:
            log.info("Created tables: %s", ", ".join(result["tables_created"]))
        if verbose and result["tables_existing"]:
            log.info("Existing tables (unchanged): %s", ", ".join(result["tables_existing"]))

        log.info(
            "Migration complete: %d created, %d existing",
            len(result["tables_created"]),
            len(result["tables_existing"]),
        )
    except Exception as exc:
        result["success"] = False
        result["error"] = str(exc)
        log.exception("Migration failed: %s", exc)
        raise

    return result


def reset_database(engine: Any | None = None, confirm: bool = False) -> None:
    """Drop all tables and recreate them.

    DANGER: This destroys all data. Only use in development.

    Args:
        engine: SQLAlchemy Engine.
        confirm: Must be ``True`` to actually execute.
    """
    if not confirm:
        log.warning("reset_database called without confirm=True — doing nothing.")
        return

    from omniroute.models import Base

    from omniroute.db.session import get_engine

    eng = engine or get_engine()
    log.warning("DROPPING ALL TABLES!")
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    log.info("All tables recreated.")


if __name__ == "__main__":
    import json
    import sys

    logging.basicConfig(level=logging.INFO)

    if "--test" in sys.argv:
        result = test_connection()
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["connected"] else 1)

    result = run_migrations(verbose=True)
    print(json.dumps(result, indent=2, default=str))
