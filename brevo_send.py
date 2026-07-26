#!/usr/bin/env python3
"""
brevo_send.py — Job 4 sender over HTTPS (works in sandboxed/proxied environments
where raw SMTP is blocked).

Sends each personalised email via the Brevo transactional email API
(https://api.brevo.com/v3/smtp/email) using only the Python standard library.
The "From" is your own Gmail (once verified as a sender in Brevo) and Reply-To is
set to the same address, so replies land back in your inbox.

Safety: defaults to --dry-run. Sends nothing until you pass --send.

Usage:
    BREVO_API_KEY="xkeysib-..." python3 brevo_send.py --send \
        --sign "Jake" --from-email jackhuhmate@gmail.com --delay 5
"""
import argparse
import csv
import json
import os
import ssl
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEADS = HERE / "leads.csv"
EMAILS = HERE / "emails.json"
SENT_LOG = HERE / "sent_log.csv"
API_URL = "https://api.brevo.com/v3/smtp/email"
DEFAULT_CA = os.environ.get("SSL_CERT_FILE") or "/root/.ccr/ca-bundle.crt"

SIGNOFF = ("\n\nBest,\n{name}\n"
           "Freelance web designer — websites for London tradesmen\n"
           "(If you'd rather I didn't follow up, just reply and let me know.)\n")


def _opener():
    ca = DEFAULT_CA if os.path.exists(DEFAULT_CA) else None
    ctx = ssl.create_default_context(cafile=ca)
    handlers = [urllib.request.HTTPSHandler(context=ctx),
                urllib.request.ProxyHandler()]  # reads HTTPS_PROXY from env
    return urllib.request.build_opener(*handlers)


def send_one(opener, api_key, sender_name, from_email, to_email, subject, text):
    payload = {
        "sender": {"name": sender_name, "email": from_email},
        "to": [{"email": to_email}],
        "replyTo": {"email": from_email, "name": sender_name},
        "subject": subject,
        "textContent": text,
    }
    req = urllib.request.Request(
        API_URL, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"api-key": api_key, "content-type": "application/json",
                 "accept": "application/json"})
    with opener.open(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", "ignore")
        return resp.status, body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="Actually send (default: dry-run).")
    ap.add_argument("--sign", default=os.environ.get("SIGN_NAME", ""))
    ap.add_argument("--from-email", default=os.environ.get("FROM_EMAIL", ""))
    ap.add_argument("--api-key", default=os.environ.get("BREVO_API_KEY", ""))
    ap.add_argument("--delay", type=int, default=5)
    args = ap.parse_args()

    live = args.send
    if live and (not args.api_key or not args.from_email or not args.sign):
        sys.exit("ERROR: --send needs --api-key, --from-email and --sign "
                 "(or BREVO_API_KEY / FROM_EMAIL / SIGN_NAME env vars).")

    with open(LEADS, newline="", encoding="utf-8") as f:
        leads = list(csv.DictReader(f))
    with open(EMAILS, encoding="utf-8") as f:
        emails = json.load(f)

    # Idempotency: never re-send to a business already logged as Sent.
    prior = {}
    if SENT_LOG.exists():
        with open(SENT_LOG, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                prior[r["Business Name"]] = r

    # Respect opt-outs: never email anyone on the do-not-contact list.
    dnc = set()
    dnc_path = HERE / "do_not_contact.csv"
    if dnc_path.exists():
        with open(dnc_path, newline="", encoding="utf-8") as f:
            for r in csv.reader(f):
                if r:
                    dnc.add(r[0].strip().lower())

    opener = _opener() if live else None
    sign = args.sign or "[YOUR NAME]"
    rows, sent, skipped, already = [], 0, 0, 0

    for lead in leads:
        name = lead["Business Name"]
        if prior.get(name, {}).get("Status", "").startswith("Sent"):
            rows.append(prior[name])  # preserve original send record, do not resend
            already += 1
            print(f"KEPT  {name} (already sent {prior[name].get('Date Sent','')})")
            continue
        meta = emails.get(name, {})
        to_addr = (lead.get("Email") or meta.get("email") or "").strip()
        subject = meta.get("subject", "")
        text = meta.get("body", "") + SIGNOFF.format(name=sign)

        base = {
            "Business Name": name, "Trade": lead.get("Trade", ""),
            "London Area": lead.get("London Area", ""), "Phone": lead.get("Phone", ""),
            "Email": to_addr, "Website": lead.get("Website", ""),
            "Biggest Flaw": lead.get("Biggest Flaw", ""), "Email Subject": subject,
            "Date Sent": date.today().isoformat(),
        }

        if not to_addr:
            base["Status"] = "Skipped - No Email Found"
            skipped += 1
            print(f"SKIP  {name} (no email)")
            rows.append(base)
            continue

        if to_addr.lower() in dnc:
            base["Status"] = "Skipped - Opted Out"
            skipped += 1
            print(f"SKIP  {name} (opted out)")
            rows.append(base)
            continue

        if live:
            try:
                status, body = send_one(opener, args.api_key, sign, args.from_email,
                                        to_addr, subject, text)
                if status in (200, 201):
                    base["Status"] = "Sent"
                    sent += 1
                    print(f"SENT  {name} -> {to_addr}")
                else:
                    base["Status"] = f"Failed - HTTP {status}: {body[:120]}"
                    print(f"FAIL  {name} -> {to_addr}: HTTP {status} {body[:120]}")
            except Exception as exc:  # noqa: BLE001
                detail = getattr(exc, "read", lambda: b"")()
                base["Status"] = f"Failed - {exc} {detail[:120]}"
                print(f"FAIL  {name} -> {to_addr}: {exc} {detail[:120]}")
            rows.append(base)
            time.sleep(args.delay)
        else:
            base["Status"] = "DRY-RUN - would send"
            print(f"DRAFT {name} -> {to_addr} | {subject}")
            rows.append(base)

    with open(SENT_LOG, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["Business Name", "Trade", "London Area", "Phone", "Email",
                      "Website", "Biggest Flaw", "Email Subject", "Date Sent", "Status"]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"\n{'LIVE SEND' if live else 'DRY-RUN (nothing sent)'}: {sent} sent, "
          f"{skipped} skipped. Log -> {SENT_LOG.name}")


if __name__ == "__main__":
    main()
