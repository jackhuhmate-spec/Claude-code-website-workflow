"""
Lead service — business logic for lead management.

Provides deduplication, scoring, enrichment, and lifecycle transitions
for leads. Operates on the database and can sync from CSV.

SQLAlchemy is OPTIONAL — imported lazily per function.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

from omniroute.exceptions import DuplicateLeadError, LeadNotFoundError, LeadValidationError

log = logging.getLogger("omniroute.services.lead")


def _ensure_tables() -> None:
    """Ensure database tables exist (safe to call repeatedly)."""
    from omniroute.db.migrations import run_migrations
    from omniroute.db.session import get_engine

    try:
        run_migrations(engine=get_engine(), verbose=False)
    except Exception as exc:
        log.warning("Database migration failed (%s: %s) — proceeding without DB", type(exc).__name__, exc)


class LeadService:
    """Business logic for lead management."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or Path.cwd()

    # ── CRUD ────────────────────────────────────────────────────────────

    def get_lead(self, lead_id: int) -> Any:
        """Get a lead by ID.

        Args:
            lead_id: Lead primary key.

        Returns:
            The Lead instance.

        Raises:
            LeadNotFoundError: If not found.
        """
        from omniroute.db.session import get_db
        from omniroute.db.repository import Repository
        from omniroute.models.lead import Lead

        with get_db() as db:
            repo = Repository[Lead](db, Lead)  # type: ignore[valid-type]
            lead = repo.get_by_id(lead_id)
        if not lead:
            raise LeadNotFoundError(f"Lead {lead_id} not found")
        return lead

    def get_leads(
        self,
        *,
        status: str | None = None,
        group: str | None = None,
        trade: str | None = None,
        area: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Any]:
        """Search leads with optional filters.

        Args:
            status: Filter by status.
            group: Filter by group (A/B).
            trade: Filter by trade.
            area: Filter by London area.
            limit: Max results.
            offset: Pagination offset.

        Returns:
            List of matching leads.
        """
        from omniroute.db.session import get_db
        from omniroute.models.lead import Lead

        sa = __import__("sqlalchemy", fromlist=["select"])

        with get_db() as db:
            query = sa.select(Lead)
            if status:
                query = query.where(Lead.status == status)
            if group:
                query = query.where(Lead.group == group)
            if trade:
                query = query.where(Lead.trade == trade)
            if area:
                query = query.where(Lead.london_area == area)
            query = query.offset(offset).limit(limit).order_by(Lead.id.desc())
            leads = list(db.execute(query).scalars().all())
        return leads

    def count_leads(self, **filters: Any) -> int:
        """Count leads matching filters.

        Args:
            **filters: Column filters.

        Returns:
            Count of matching leads.
        """
        from omniroute.db.session import get_db
        from omniroute.db.repository import Repository
        from omniroute.models.lead import Lead

        with get_db() as db:
            repo = Repository[Lead](db, Lead)  # type: ignore[valid-type]
            return repo.count(**filters)

    def create_lead(self, **data: Any) -> Any:
        """Create a new lead with validation.

        Args:
            **data: Lead fields.

        Returns:
            The created lead.

        Raises:
            LeadValidationError: If required fields are missing.
            DuplicateLeadError: If lead already exists.
        """
        from omniroute.db.session import get_db
        from omniroute.db.repository import Repository
        from omniroute.models.lead import Lead

        if not data.get("business_name") or not data.get("trade"):
            raise LeadValidationError("business_name and trade are required")

        with get_db() as db:
            email = (data.get("email") or "").strip().lower()
            name = data["business_name"].strip()

            repo = Repository[Lead](db, Lead)  # type: ignore[valid-type]

            if email:
                existing = repo.find_first(email=email)
                if existing:
                    raise DuplicateLeadError(
                        f"Lead with email '{email}' already exists (ID {existing.id})"
                    )

            existing = repo.find_first(business_name=name, trade=data["trade"])
            if existing:
                raise DuplicateLeadError(
                    f"Lead '{name}' ({data['trade']}) already exists (ID {existing.id})"
                )

            lead = repo.create(**data)
        return lead

    def update_lead(self, lead_id: int, **values: Any) -> Any:
        """Update a lead's fields.

        Args:
            lead_id: Lead ID.
            **values: Fields to update.

        Returns:
            Updated lead.
        """
        from omniroute.db.session import get_db
        from omniroute.db.repository import Repository
        from omniroute.models.lead import Lead

        with get_db() as db:
            repo = Repository[Lead](db, Lead)  # type: ignore[valid-type]
            existing = repo.get_by_id(lead_id)
            if not existing:
                raise LeadNotFoundError(f"Lead {lead_id} not found")
            lead = repo.update(lead_id, **values)
        return lead

    def delete_lead(self, lead_id: int) -> bool:
        """Delete a lead.

        Args:
            lead_id: Lead ID.

        Returns:
            True if deleted.
        """
        from omniroute.db.session import get_db
        from omniroute.db.repository import Repository
        from omniroute.models.lead import Lead

        with get_db() as db:
            repo = Repository[Lead](db, Lead)  # type: ignore[valid-type]
            return repo.delete(lead_id)

    # ── CSV Sync ─────────────────────────────────────────────────────────

    def sync_from_csv(self, csv_path: str | Path | None = None) -> dict[str, int]:
        """Sync leads from CSV to the database (idempotent).

        Args:
            csv_path: Path to leads.csv. Defaults to working directory.

        Returns:
            Dict with 'created', 'skipped', 'total' counts.
        """
        _ensure_tables()
        from omniroute.db.session import get_db
        from omniroute.db.repository import Repository
        from omniroute.models.lead import Lead

        path = Path(csv_path) if csv_path else self._data_dir / "leads.csv"
        if not path.exists():
            raise FileNotFoundError(f"CSV not found: {path}")

        created = 0
        skipped = 0
        total = 0

        with path.open(newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            with get_db() as db:
                repo = Repository[Lead](db, Lead)  # type: ignore[valid-type]
                for row in reader:
                    total += 1
                    email = (row.get("Email") or "").strip().lower()
                    if not email:
                        email = None
                    name = row.get("Business Name", "").strip()
                    trade = row.get("Trade", "")

                    if not name or not trade:
                        skipped += 1
                        continue

                    existing = None
                    if email:
                        existing = repo.find_first(email=email)
                    if not existing:
                        existing = repo.find_first(business_name=name, trade=trade)
                    if existing:
                        skipped += 1
                        continue

                    phone = (row.get("Phone") or "").strip() or None
                    website = (row.get("Website") or "").strip() or None

                    repo.create(
                        business_name=name,
                        trade=trade,
                        london_area=row.get("London Area", ""),
                        phone=phone,
                        email=email,
                        website=website,
                        website_score=self._safe_int(row.get("Website Score")),
                        biggest_flaw=row.get("Biggest Flaw", ""),
                        group=row.get("Group", "A"),
                        source="csv_import",
                        status="new",
                    )
                    created += 1

        log.info("CSV sync: %d created, %d skipped (of %d)", created, skipped, total)
        return {"created": created, "skipped": skipped, "total": total}

    def get_pipeline_snapshot(self) -> dict[str, Any]:
        """Get a snapshot of the pipeline state.

        Returns:
            Dict with pipeline counts.
        """
        _ensure_tables()
        from omniroute.db.session import get_db
        from omniroute.db.repository import Repository
        from omniroute.models.lead import Lead

        with get_db() as db:
            repo = Repository[Lead](db, Lead)  # type: ignore[valid-type]
            total = repo.count()
            contacted = repo.count(contacted=True)
            replied = repo.count(replied=True)
            opted = repo.count(opted_out=True)
            new = repo.count(status="new")
            interested = repo.count(status="interested")
            won = repo.count(status="won")

        csv_path = self._data_dir / "leads.csv"
        csv_count = 0
        if csv_path.exists():
            with csv_path.open(newline="", encoding="utf-8") as f:
                csv_count = sum(1 for _ in csv.DictReader(f))

        return {
            "db_leads": total,
            "csv_leads": csv_count,
            "contacted": contacted,
            "replied": replied,
            "opted_out": opted,
            "new": new,
            "interested": interested,
            "won": won,
        }

    @staticmethod
    def _safe_int(val: str | None) -> int | None:
        if val and val.strip():
            try:
                return int(val.strip())
            except ValueError:
                return None
        return None
