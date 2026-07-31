"""
Generic repository pattern for Omniroute ORM models.

Provides CRUD operations with type safety through generics.
SQLAlchemy is OPTIONAL — imported lazily.
"""

from __future__ import annotations

import logging
from typing import Any, Generic, TypeVar

from omniroute.models.base import _SA_AVAILABLE

log = logging.getLogger("omniroute.db.repository")

T = TypeVar("T")


class Repository(Generic[T]):
    """Generic CRUD repository for SQLAlchemy models.

    Usage::

        repo = Repository(db_session, Lead)
        lead = repo.get_by_id(1)
        new_lead = repo.create(business_name="...")
    """

    def __init__(self, session: Any, model_cls: type[T]) -> None:
        if not _SA_AVAILABLE:
            raise ImportError(
                "SQLAlchemy is required for repository features. "
                "Install with: pip install sqlalchemy"
            )
        self._session = session
        self._model = model_cls

    # ── Read ────────────────────────────────────────────────────────────

    def get_by_id(self, record_id: int) -> T | None:
        """Get a record by primary key ID."""
        return self._session.get(self._model, record_id)

    def get_all(self) -> list[T]:
        """Get all records of this type."""
        from sqlalchemy import select
        return list(self._session.execute(select(self._model)).scalars().all())

    def find(self, **filters: Any) -> list[T]:
        """Find records matching keyword filter conditions."""
        from sqlalchemy import select
        stmt = select(self._model).filter_by(**filters)
        return list(self._session.execute(stmt).scalars().all())

    def find_first(self, **filters: Any) -> T | None:
        """Find the first record matching the filter conditions."""
        from sqlalchemy import select
        stmt = select(self._model).filter_by(**filters).limit(1)
        return self._session.execute(stmt).scalar_one_or_none()

    def count(self, **filters: Any) -> int:
        """Count records matching the filter conditions."""
        from sqlalchemy import func, select
        stmt = select(func.count()).select_from(self._model).filter_by(**filters)
        result = self._session.execute(stmt).scalar()
        return result or 0

    # ── Create ──────────────────────────────────────────────────────────

    def create(self, **kwargs: Any) -> T:
        """Create and persist a new record.

        Returns:
            The newly created model instance.

        Raises:
            Exception: If the database constraint is violated.
        """
        instance = self._model(**kwargs)
        self._session.add(instance)
        self._session.flush()
        log.debug("Created %s: %s", self._model.__name__, instance)
        return instance

    def bulk_create(self, records: list[dict[str, Any]]) -> list[T]:
        """Create multiple records in bulk."""
        instances = [self._model(**r) for r in records]
        self._session.add_all(instances)
        self._session.flush()
        log.debug("Bulk-created %d %s records", len(instances), self._model.__name__)
        return instances

    # ── Update ──────────────────────────────────────────────────────────

    def update(self, record_id: int, **values: Any) -> T | None:
        """Update a record by primary key.

        Returns:
            The updated model instance, or ``None`` if not found.
        """
        from sqlalchemy import update as sa_update
        stmt = (
            sa_update(self._model)
            .where(self._model.id == record_id)  # type: ignore[attr-defined]
            .values(**values)
            .returning(self._model)
        )
        result = self._session.execute(stmt).scalar_one_or_none()
        self._session.flush()
        if result:
            log.debug("Updated %s %d", self._model.__name__, record_id)
        return result

    def upsert(self, filters: dict[str, Any], **values: Any) -> T:
        """Find existing record or create a new one.

        Returns:
            The existing or newly created model instance.
        """
        existing = self.find_first(**filters)
        if existing:
            for key, val in values.items():
                setattr(existing, key, val)
            self._session.flush()
            log.debug("Upsert (update) %s: %s", self._model.__name__, existing)
            return existing
        merged = {**filters, **values}
        return self.create(**merged)

    # ── Delete ──────────────────────────────────────────────────────────

    def delete(self, record_id: int) -> bool:
        """Delete a record by primary key.

        Returns:
            ``True`` if a record was deleted, ``False`` otherwise.
        """
        from sqlalchemy import delete as sa_delete
        stmt = sa_delete(self._model).where(
            self._model.id == record_id  # type: ignore[attr-defined]
        )
        result = self._session.execute(stmt)
        self._session.flush()
        deleted = result.rowcount > 0
        if deleted:
            log.debug("Deleted %s %d", self._model.__name__, record_id)
        return deleted
