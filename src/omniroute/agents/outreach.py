"""
Outreach Agent — wraps ``ops/gmail_send_batch.py``.

Sends cold emails from the queue with daily cap and safety guards.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from omniroute.agents.base import AgentContext, AgentResult, BaseAgent

HERE = Path(__file__).resolve().parent.parent.parent.parent
SEND_BATCH = [
    sys.executable,
    str(HERE / "ops" / "gmail_send_batch.py"),
]
GMAIL_TEST = [
    sys.executable,
    str(HERE / "ops" / "gmail.py"),
]


class OutreachAgent(BaseAgent):
    """Send cold email outreach to leads.

    Delegates to ``ops/gmail_send_batch.py`` with safety checks:
    - Dry-run by default
    - 30/day hard cap
    - 45-second spacing between sends
    """

    @property
    def agent_name(self) -> str:
        return "outreach"

    def execute(self) -> AgentResult:
        """Run the outreach send.

        Returns:
            AgentResult with send counts.
        """
        limit = self.context.config.get("limit", 30)
        delay = self.context.config.get("delay", 45)

        cmd = SEND_BATCH + ["--limit", str(limit), "--delay", str(delay)]
        if not self.is_dry_run:
            cmd += ["--send"]

        self.log.info("Running outreach (dry_run=%s, limit=%d)", self.is_dry_run, limit)

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        output = result.stdout.strip()
        err = result.stderr.strip()

        # Parse results
        sent = 0
        skipped = 0
        for line in output.splitlines():
            if "Sent" in line and "failed" in line:
                parts = line.split(",")
                for part in parts:
                    if "Sent" in part:
                        try:
                            sent = int(part.split()[-1])
                        except (ValueError, IndexError):
                            pass
                    if "skipped" in part:
                        try:
                            skipped = int(part.split()[-1])
                        except (ValueError, IndexError):
                            pass

        return AgentResult(
            success=result.returncode == 0,
            agent_name=self.agent_name,
            summary=output[-500:] or err[:300],
            data={
                "sent": sent,
                "skipped": skipped,
                "dry_run": self.is_dry_run,
                "output": output[-800:],
            },
            error=err[:300] if result.returncode != 0 else None,
        )
