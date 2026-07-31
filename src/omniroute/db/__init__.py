"""Database package for Omniroute.

SQLAlchemy is optional — imported lazily on first use.

Usage::

    from omniroute.db.session import get_db, create_engine_from_url, test_connection
    from omniroute.db.repository import Repository
    from omniroute.db.migrations import run_migrations
"""
