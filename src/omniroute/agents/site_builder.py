"""
Site Builder agent — wraps ``build_site.py`` and ``deploy_preview.py``.

Builds and deploys 5-page websites to Netlify for previews or final delivery.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from omniroute.agents.base import AgentContext, AgentResult, BaseAgent

HERE = Path(__file__).resolve().parent.parent.parent.parent
DEPLOY_PREVIEW = [
    sys.executable,
    str(HERE / "deploy_preview.py"),
]


class SiteBuilderAgent(BaseAgent):
    """Build and deploy websites for leads.

    Delegates to ``deploy_preview.py`` for Netlify deploys and
    ``build_site.py`` for local site generation.
    """

    @property
    def agent_name(self) -> str:
        return "site_builder"

    def execute(self) -> AgentResult:
        """Build and deploy a website.

        Requires business_name in config (from leads.csv).
        Optional: trade, area, phone, email, services overrides.

        Returns:
            AgentResult with the live site URL.
        """
        business = self.context.config.get("business_name")
        if not business:
            return AgentResult(
                success=False,
                agent_name=self.agent_name,
                error="business_name required in config",
            )

        cmd = DEPLOY_PREVIEW + ["--business", business]
        if self.context.config.get("final"):
            cmd.append("--final")
        if self.is_dry_run:
            # Dry-run: just build locally, don't deploy
            from build_site import main as build_main  # type: ignore

            # We need the lead's data — read from CSV
            import csv

            leads_file = HERE / "leads.csv"
            cfg: dict[str, Any] = {}
            if leads_file.exists():
                with leads_file.open(newline="", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        if row["Business Name"].strip() == business:
                            cfg = {
                                "business_name": business,
                                "trade": row.get("Trade", ""),
                                "area": row.get("London Area", ""),
                                "phone": row.get("Phone", ""),
                                "email": row.get("Email", ""),
                                "services": [row.get("Trade", "")],
                                "accent": "#1a6fb5",
                            }
                            break
            if not cfg:
                return AgentResult(
                    success=False,
                    agent_name=self.agent_name,
                    error=f"Lead '{business}' not found in leads.csv",
                )

            import json  # noqa: F811
            import tempfile

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as f:
                json.dump(cfg, f)
                json_path = f.name

            try:
                build_result = subprocess.run(
                    [sys.executable, str(HERE / "build_site.py"), json_path],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                output = build_result.stdout.strip()
                return AgentResult(
                    success=build_result.returncode == 0,
                    agent_name=self.agent_name,
                    summary=output or "Site built (dry run)",
                    data={"dry_run": True, "output": output},
                    error=build_result.stderr[:500] if build_result.returncode != 0 else None,
                )
            finally:
                Path(json_path).unlink(missing_ok=True)

        # Live deploy
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        output = result.stdout.strip()
        url = ""
        for line in output.splitlines():
            if line.startswith("http"):
                url = line.strip()
                break

        return AgentResult(
            success=result.returncode == 0,
            agent_name=self.agent_name,
            summary=url or output[-300:],
            data={
                "url": url,
                "final": self.context.config.get("final", False),
                "output": output,
            },
            error=result.stderr[:500] if result.returncode != 0 else None,
        )
