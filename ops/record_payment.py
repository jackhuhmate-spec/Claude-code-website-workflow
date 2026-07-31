#!/usr/bin/env python3
"""
record_payment.py — log a payment to payments.csv (the revenue ledger).

The system never invents a payment; Jack records it when money actually
changes hands. weekly_digest.py reads this file for the revenue summary.

Examples:
    python3 ops/record_payment.py "Bromley Roofer" --amount 449 --type build --status paid
    python3 ops/record_payment.py "ACME" --amount 449 --type build --status deposit --notes "50% up front"
    python3 ops/record_payment.py "ACME" --amount 39 --type care --status paid --notes "monthly care plan"
"""
import argparse
import csv
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
PAYMENTS = HERE / "payments.csv"
HEADER = ["date", "business", "amount_gbp", "type", "status", "notes"]

TYPES = ("build", "care")
STATUSES = ("paid", "deposit", "quoted", "overdue", "refunded")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("business", help="Business name (match leads.csv if possible)")
    ap.add_argument("--amount", type=float, required=True, help="Amount in GBP, e.g. 449")
    ap.add_argument("--type", choices=TYPES, default="build")
    ap.add_argument("--status", choices=STATUSES, default="paid")
    ap.add_argument("--notes", default="")
    ap.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD (default today)")
    a = ap.parse_args()

    if a.amount <= 0:
        sys.exit(f"ERROR: amount must be positive (got {a.amount}).")

    new_file = not PAYMENTS.exists() or PAYMENTS.stat().st_size == 0
    with PAYMENTS.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(HEADER)
        w.writerow([a.date, a.business.strip(), f"{a.amount:.2f}", a.type, a.status, a.notes.strip()])
    print(f"Logged {a.type} {a.status}: £{a.amount:.2f} from {a.business} on {a.date}")


if __name__ == "__main__":
    main()
