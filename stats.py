#!/usr/bin/env python3
"""stats.py — quick dashboard of the outreach pipeline. Run any time: python3 stats.py"""
import csv
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name):
    p = HERE / name
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


leads = load("leads.csv")
sent = load("sent_log.csv")
replies = load("replies_log.csv")
dnc = load("do_not_contact.csv")

groupA = sum(1 for r in leads if r.get("Group") == "A")
groupB = sum(1 for r in leads if r.get("Group") == "B")
with_email = sum(1 for r in leads if (r.get("Email") or "").strip())
sent_ok = sum(1 for r in sent if r.get("Status") == "Sent")
skipped = sum(1 for r in sent if str(r.get("Status", "")).startswith("Skipped"))

print("=" * 46)
print("  LONDON TRADESMAN OUTREACH — DASHBOARD")
print("=" * 46)
print(f"  Leads total ............ {len(leads)}")
print(f"    Group A (bad site) ... {groupA}")
print(f"    Group B (no site) .... {groupB}")
print(f"    With an email ........ {with_email}")
print(f"  Emails sent ............ {sent_ok}")
print(f"  Skipped (no email/opt) . {skipped}")
print(f"  Replies handled ........ {len(replies)}")
print(f"  Opted out (do-not-mail)  {len(dnc)}")
print("-" * 46)
print("  Leads by area:")
for area, n in Counter(r.get("London Area", "?") for r in leads).most_common():
    print(f"    {area:<20} {n}")
print("-" * 46)
print("  Leads by trade:")
for trade, n in Counter(r.get("Trade", "?") for r in leads).most_common():
    print(f"    {trade:<20} {n}")
if replies:
    print("-" * 46)
    print("  Replies by category:")
    for cat, n in Counter(r.get("category", r.get("Category", "?")) for r in replies).most_common():
        print(f"    {cat:<20} {n}")
print("=" * 46)
