"""
Reply Handler agent — wraps ``ops/run_cycle.py replies``.

Reads the inbox, classifies replies, auto-answers, and escalates
deals/concerns to Jake.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from omniroute.agents.base import AgentContext, AgentResult, BaseAgent

HERE = Path(__file__).resolve().parent.parent.parent.parent
RUN_CYCLE = [
    sys.executable,
    str(HERE / "ops" / "run_cycle.py"),
]


class ReplyHandlerAgent(BaseAgent):
    """Check inbox replies, classify, and auto-reply.

    Delegates to ``ops/run_cycle.py replies``.
    """

    @property
    def agent_name(self) -> str:
        return "reply_handler"

    def execute(self) -> AgentResult:
        """Run the reply cycle.

        Returns:
            AgentResult with classification counts.
        """
        days = self.context.config.get("days", 3)
        cmd = RUN_CYCLE + ["replies", "--days", str(days)]

        if not self.is_dry_run:
            cmd.append("--auto")
        if self.context.force:
            cmd.append("--force")

        self.log.info(
            "Running reply handler (dry_run=%s, days=%d)",
            self.is_dry_run,
            days,
        )

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        output = result.stdout.strip()
        err = result.stderr.strip()

        # Parse bucket counts from output
        buckets: dict[str, int] = {}
        for line in output.splitlines():
            for cat in (
                "DEAL",
                "INTERESTED",
                "QUESTION",
                "OBJECTION",
                "OPTOUT",
                "AUTO",
                "SUSPICIOUS",
                "REVIEW",
            ):
                if f"{cat}:" in line:
                    try:
                        val = int(line.split(f"{cat}:")[1].strip())
                        buckets[cat] = val
                    except (ValueError, IndexError):
                        pass

        has_escalations = "ESCALATE TO JAKE" in output
        has_deal = "DEAL" in output

        return AgentResult(
            success=result.returncode == 0,
            agent_name=self.agent_name,
            summary=output[-600:] or err[:300],
            data={
                "buckets": buckets,
                "has_escalations": has_escalations,
                "has_deal": has_deal,
                "output": output[-1000:],
            },
            error=err[:300] if result.returncode != 0 else None,
        )
