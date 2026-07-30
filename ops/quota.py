#!/usr/bin/env python3
"""
quota.py — the single source of truth for the daily Gmail send budget.

Two senders now draw on the same account: the cold batch (gmail_send_batch.py) and
the follow-up sequence (followups.py). If each counted only its own log they would
happily send 30 emails apiece and put the account at 60/day, which is exactly the
kind of thing that gets a personal Gmail rate-limited or suspended — and that address
is where the deals arrive.

The count is derived from what was actually written to the logs today, never from an
in-process counter, so it survives repeated runs, concurrent runners and crashes.

    python3 ops/quota.py        # show today's budget
"""
import csv
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SENT_LOG = HERE / "sent_log.csv"
FU_LOG = HERE / "followups_log.csv"

# Gmail's free tier allows ~500/day in total, but cold outreach is judged on
# deliverability, not headroom. 30 is the deliberate ceiling.
DAILY_CAP = 30


def cold_sent_today(today=None):
    """Cold emails recorded as actually sent today."""
    today = (today or date.today()).isoformat()
    if not SENT_LOG.exists():
        return 0
    n = 0
    with SENT_LOG.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (r.get("Date Sent") or "").strip() == today and \
               (r.get("Status") or "").startswith("Sent"):
                n += 1
    return n


def followups_sent_today(today=None):
    """Follow-up touches recorded as actually sent today."""
    today = (today or date.today()).isoformat()
    if not FU_LOG.exists():
        return 0
    n = 0
    with FU_LOG.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (r.get("date") or "").strip() == today:
                n += 1
    return n


def sent_today(today=None):
    """Every email this system put on the wire today, from either sender."""
    return cold_sent_today(today) + followups_sent_today(today)


def remaining(today=None):
    """How many more may be sent today. Never negative."""
    return max(0, DAILY_CAP - sent_today(today))


if __name__ == "__main__":
    print(f"cap          {DAILY_CAP}")
    print(f"cold sent    {cold_sent_today()}")
    print(f"follow-ups   {followups_sent_today()}")
    print(f"remaining    {remaining()}")
