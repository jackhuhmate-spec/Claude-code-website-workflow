#!/usr/bin/env python3
"""weekly_digest.py — print a plain-English summary of the last 7 days + all-time totals.
Reads the logs; no network. The weekly routine runs this and posts the output to Jack."""
import csv
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent


def rows(name):
    p = HERE / name
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def within(datestr, days):
    try:
        return (date.today() - datetime.fromisoformat((datestr or "")[:10]).date()).days < days
    except Exception:
        return False


leads = rows("leads.csv")
sent = rows("sent_log.csv")
replies = rows("replies_log.csv")
follow = rows("followups_log.csv")
pays = rows("payments.csv")
dnc = rows("do_not_contact.csv")

sent_ok = [r for r in sent if r.get("Status") == "Sent"]
new_sent = [r for r in sent_ok if within(r.get("Date Sent"), 7)]
new_replies = [r for r in replies if within(r.get("date"), 7)]
new_follow = [r for r in follow if within(r.get("date"), 7)]
paid = [r for r in pays if r.get("status", "").lower() in ("paid", "complete", "completed")]

def money(rs):
    tot = 0.0
    for r in rs:
        try:
            tot += float(str(r.get("amount_gbp", "")).replace("£", "").strip() or 0)
        except ValueError:
            pass
    return tot

print("=" * 52)
print(f"  SWIFTSITE — WEEKLY DIGEST ({date.today():%d %b %Y})")
print("=" * 52)
print("  THIS WEEK")
print(f"    New emails sent .......... {len(new_sent)}")
print(f"    New replies .............. {len(new_replies)}")
print(f"    Follow-ups sent .......... {len(new_follow)}")
if new_replies:
    for cat, n in Counter(r.get("category", "?") for r in new_replies).most_common():
        print(f"        {cat:<16} {n}")
print("-" * 52)
print("  ALL TIME")
print(f"    Leads in system .......... {len(leads)}")
print(f"    Emails delivered ......... {len(sent_ok)}")
print(f"    Total replies ............ {len(replies)}")
print(f"    Opted out (suppressed) ... {len(dnc)}")
print(f"    Deals paid ............... {len(paid)}   (£{money(paid):.0f})")
print("-" * 52)
interested = [r for r in replies if r.get("category") == "Interested"]
if interested:
    print("  OPEN / INTERESTED LEADS (chase these):")
    for r in interested[-10:]:
        print(f"    • {r.get('business','?')}  <{r.get('email','')}>")
print("=" * 52)
