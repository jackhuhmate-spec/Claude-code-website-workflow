#!/usr/bin/env python3
"""
send_emails.py — Job 4 sender.

Reads leads.csv + emails.json, sends one personalised email per lead that has an
email address via Gmail SMTP, and writes sent_log.csv.

Safety by design:
  * Defaults to --dry-run: it prints exactly what WOULD be sent and writes the log,
    but sends nothing until you pass --send.
  * Credentials are read from environment variables or --gmail/--app-password flags,
    never hard-coded.
  * Leads with no email address are skipped and logged as "Skipped - No Email Found".

Usage:
    # Preview (no email leaves the machine) — this is the default:
    python3 send_emails.py

    # Actually send, after you've reviewed emails.md and approved:
    GMAIL_USER=you@gmail.com GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx" \
        python3 send_emails.py --send --sign "Your Name"

Flags:
    --send                 Actually send (omit for dry-run preview).
    --sign NAME            Name to sign the emails with (required to send).
    --gmail ADDRESS        Gmail address (or set GMAIL_USER).
    --app-password PASS    Gmail App Password (or set GMAIL_APP_PASSWORD).
    --delay SECONDS        Seconds to pause between sends (default 60).
"""
import argparse
import csv
import json
import os
import smtplib
import ssl
import sys
import time
from datetime import date
from email.message import EmailMessage
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEADS = HERE / "leads.csv"
EMAILS = HERE / "emails.json"
SENT_LOG = HERE / "sent_log.csv"

SIGNOFF_TEMPLATE = (
    "\n\nBest,\n{name}\n"
    "Freelance web designer — websites for London tradesmen\n"
)


def load_leads():
    with open(LEADS, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_emails():
    with open(EMAILS, encoding="utf-8") as f:
        return json.load(f)


def build_message(sender_addr, sign_name, to_addr, subject, body):
    msg = EmailMessage()
    msg["From"] = f"{sign_name} <{sender_addr}>"
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body + SIGNOFF_TEMPLATE.format(name=sign_name))
    return msg


def main():
    ap = argparse.ArgumentParser(description="Send personalised cold emails to leads.")
    ap.add_argument("--send", action="store_true", help="Actually send (default: dry-run).")
    ap.add_argument("--sign", default=os.environ.get("SIGN_NAME", ""), help="Name to sign emails with.")
    ap.add_argument("--gmail", default=os.environ.get("GMAIL_USER", ""), help="Gmail address.")
    ap.add_argument("--app-password", default=os.environ.get("GMAIL_APP_PASSWORD", ""), help="Gmail App Password.")
    ap.add_argument("--delay", type=int, default=60, help="Seconds between sends (default 60).")
    args = ap.parse_args()

    leads = load_leads()
    emails = load_emails()

    live = args.send
    if live:
        if not args.gmail or not args.app_password:
            sys.exit("ERROR: --send needs --gmail and --app-password (or GMAIL_USER / GMAIL_APP_PASSWORD env vars).")
        if not args.sign:
            sys.exit("ERROR: --send needs --sign \"Your Name\".")

    sign = args.sign or "[YOUR NAME]"
    server = None
    if live:
        ctx = ssl.create_default_context()
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx)
        server.login(args.gmail, args.app_password)

    rows = []
    sent = skipped = 0
    for lead in leads:
        name = lead["Business Name"]
        meta = emails.get(name, {})
        to_addr = (lead.get("Email") or meta.get("email") or "").strip()
        subject = meta.get("subject", "")
        body = meta.get("body", "")

        base = {
            "Business Name": name,
            "Trade": lead.get("Trade", ""),
            "London Area": lead.get("London Area", ""),
            "Phone": lead.get("Phone", ""),
            "Email": to_addr,
            "Website": lead.get("Website", ""),
            "Biggest Flaw": lead.get("Biggest Flaw", ""),
            "Email Subject": subject,
            "Date Sent": date.today().isoformat(),
        }

        if not to_addr:
            base["Status"] = "Skipped - No Email Found"
            rows.append(base)
            skipped += 1
            print(f"SKIP  {name} (no email)")
            continue

        if live:
            try:
                server.send_message(build_message(args.gmail, sign, to_addr, subject, body))
                base["Status"] = "Sent"
                sent += 1
                print(f"SENT  {name} -> {to_addr}")
            except Exception as exc:  # noqa: BLE001
                base["Status"] = f"Failed - {exc}"
                print(f"FAIL  {name} -> {to_addr}: {exc}")
            rows.append(base)
            time.sleep(args.delay)
        else:
            base["Status"] = "DRY-RUN - would send"
            rows.append(base)
            print(f"DRAFT {name} -> {to_addr} | {subject}")

    if server:
        server.quit()

    with open(SENT_LOG, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["Business Name", "Trade", "London Area", "Phone", "Email",
                      "Website", "Biggest Flaw", "Email Subject", "Date Sent", "Status"]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    mode = "LIVE SEND" if live else "DRY-RUN (nothing sent)"
    print(f"\n{mode}: {sent} sent, {skipped} skipped. Log -> {SENT_LOG.name}")
    if not live:
        print("Review emails.md, then re-run with --send to actually deliver.")


if __name__ == "__main__":
    main()
