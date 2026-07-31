"""
Email Writer agent — wraps ``ops/write_emails.py``.

Generates personalised cold email copy for new leads using the LLM.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from omniroute.agents.base import AgentContext, AgentResult, BaseAgent

HERE = Path(__file__).resolve().parent.parent.parent.parent
WRITE_EMAILS = [
    sys.executable,
    str(HERE / "ops" / "write_emails.py"),
]


class EmailWriterAgent(BaseAgent):
    """Write personalised cold emails for new leads.

    Delegates to ``ops/write_emails.py`` which uses the Groq LLM.
    """

    @property
    def agent_name(self) -> str:
        return "email_writer"

    def validate(self) -> bool:
        return True  # runs fine without LLM (exits cleanly)

    def execute(self) -> AgentResult:
        """Generate email copy for leads without it.

        Returns:
            AgentResult with count of emails written.
        """
        limit = self.context.config.get("limit", 40)
        cmd = WRITE_EMAILS + ["--write", "--limit", str(limit)]

        self.log.info("Writing emails...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        output = result.stdout.strip()
        err = result.stderr.strip()

        # Parse result for reporting
        written = 0
        rejected = 0
        for line in output.splitlines():
            if "Wrote" in line and "emails" in line:
                parts = line.split()
                try:
                    written = int(parts[1])
                except (ValueError, IndexError):
                    pass
            if "rejected" in line:
                try:
                    rejected = int(parts[1]) if "Wrote" in line else 0
                except (ValueError, IndexError):
                    pass

        return AgentResult(
            success=result.returncode == 0,
            agent_name=self.agent_name,
            summary=output[-500:] or err[:200],
            data={
                "written": written,
                "rejected": rejected,
                "output": output[-800:],
            },
            error=err[:300] if result.returncode != 0 else None,
        )
