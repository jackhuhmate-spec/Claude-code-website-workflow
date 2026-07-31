"""
Lead Hunter agent — wraps the existing ``ops/lead_hunter.py`` script.

Finds London businesses with weak or missing websites via OpenStreetMap
and live site audits. Persists leads to ``leads.csv`` and the database.
"""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path
from typing import Any

from omniroute.agents.base import AgentContext, AgentResult, BaseAgent

HERE = Path(__file__).resolve().parent.parent.parent.parent
LEADS_CSV = HERE / "leads.csv"
LEAD_HUNTER = [
    sys.executable,
    str(HERE / "ops" / "lead_hunter.py"),
]


class LeadHunterAgent(BaseAgent):
    """Discover, audit, and persist new business leads.

    Delegates to the existing ``ops/lead_hunter.py`` script.
    """

    @property
    def agent_name(self) -> str:
        return "lead_hunter"

    def validate(self) -> bool:
        return True  # lead_hunter needs no credentials

    def execute(self) -> AgentResult:
        """Run the lead hunter and persist results.

        Returns:
            AgentResult with lead counts.
        """
        tile = self.context.config.get("tile")
        max_leads = self.context.config.get("max_leads", 25)

        cmd = LEAD_HUNTER + ["--write", "--max", str(max_leads)]
        if tile is not None:
            cmd += ["--tile", str(tile)]

        self.log.info("Running lead hunter: %s", " ".join(str(c) for c in cmd[-4:]))

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )

        if result.returncode == 124:
            self.log.warning("Lead hunter timed out — partial results may exist.")

        # Try to persist to database if possible
        db_count = 0
        if LEADS_CSV.exists():
            try:
                new_leads = []
                with LEADS_CSV.open(newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        new_leads.append(row)

                if new_leads and not self.is_dry_run:
                    try:
                        db_count = self._persist_to_db(new_leads)
                    except Exception as exc:
                        self.log.warning("DB sync failed (CSV write succeeded): %s", exc)

                self.log.info("Leads in CSV: %d, synced to DB: %d", len(new_leads), db_count)
            except Exception as exc:
                self.log.warning("Failed to read leads.csv: %s", exc)

        return AgentResult(
            success=result.returncode in (0, 124),
            agent_name=self.agent_name,
            summary=result.stdout.strip()[-500:] or result.stderr.strip()[:300],
            data={
                "returncode": result.returncode,
                "stdout": result.stdout[-1000:],
                "stderr": result.stderr[:500],
                "db_synced": db_count,
            },
            error=result.stderr[:500] if result.returncode not in (0, 124) else None,
        )

    def _persist_to_db(self, rows: list[dict[str, str]]) -> int:
        """Sync CSV leads to the database (idempotent).

        Args:
            rows: List of lead dicts from CSV.

        Returns:
            Number of new leads inserted.
        """
        from omniroute.db.session import get_db
        from omniroute.models.lead import Lead

        sa = __import__("sqlalchemy", fromlist=["select"])

        count = 0
        with get_db() as db:
            for row in rows:
                email = (row.get("Email") or "").strip().lower()
                name = row.get("Business Name", "").strip()

                if email:
                    existing = db.execute(
                        sa.select(Lead).where(Lead.email == email)
                    ).scalar_one_or_none()
                else:
                    existing = db.execute(
                        sa.select(Lead).where(
                            Lead.business_name == name,
                            Lead.trade == row.get("Trade", ""),
                        )
                    ).scalar_one_or_none()

                if existing:
                    continue

                lead = Lead(
                    business_name=name,
                    trade=row.get("Trade", ""),
                    london_area=row.get("London Area", ""),
                    phone=row.get("Phone", ""),
                    email=email,
                    website=row.get("Website", ""),
                    website_score=self._safe_int(row.get("Website Score")),
                    biggest_flaw=row.get("Biggest Flaw", ""),
                    group=row.get("Group", "A"),
                    source="osm",
                    status="new",
                )
                db.add(lead)
                count += 1

        return count

    @staticmethod
    def _safe_int(val: str | None) -> int | None:
        if val and val.strip():
            try:
                return int(val.strip())
            except ValueError:
                return None
        return None
