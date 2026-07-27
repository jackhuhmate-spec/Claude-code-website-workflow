#!/usr/bin/env python3
"""
gmail_send_batch.py — cold-email sender over Gmail SMTP (replaces brevo_send.py).

Idempotent: never re-emails an address already in sent_log.csv.
Honours do_not_contact.csv and the PAUSED kill switch. Dry-run by default.

    python3 ops/gmail_send_batch.py              # dry run
    python3 ops/gmail_send_batch.py --send --limit 20 --delay 45
"""
import argparse, csv, json, os, smtplib, ssl, sys, time
from datetime import date
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
LEADS = HERE / "leads.csv"
EMAILS = HERE / "emails.json"
SENT_LOG = HERE / "sent_log.csv"
DNC = HERE / "do_not_contact.csv"
PAUSED = HERE / "PAUSED"

USER = os.environ.get("GMAIL_USER", "")
PW = (os.environ.get("GMAIL_APP_PASSWORD", "") or "").replace(" ", "")
SIGN = os.environ.get("SIGN_NAME", "Jake")
DAILY_CAP = 30  # Gmail free tier is ~500/day total; stay conservative for deliverability

SIGNOFF = "\n\nBest,\n{name}\n\n(If you'd rather not hear from me, just reply \"no thanks\" and I won't email again.)"

FIELDS = ["Business Name", "Trade", "London Area", "Phone", "Email", "Website",
          "Biggest Flaw", "Email Subject", "Date Sent", "Status"]


def sent_today():
    """How many we have already sent today - the cap must survive repeated runs."""
    if not SENT_LOG.exists():
        return 0
    today = date.today().isoformat()
    n = 0
    with SENT_LOG.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (r.get("Date Sent") or "").strip() == today and (r.get("Status") or "").startswith("Sent"):
                n += 1
    return n


def already_sent():
    out = set()
    if SENT_LOG.exists():
        with SENT_LOG.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                a = (row.get("Email") or "").strip().lower()
                if a and "@" in a and (row.get("Status") or "").startswith("Sent"):
                    out.add(a)
    return out


def opted_out():
    out = set()
    if DNC.exists():
        for line in DNC.read_text(encoding="utf-8").splitlines():
            a = line.split(",")[0].strip().lower()
            if a and "@" in a:
                out.add(a)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--limit", type=int, default=DAILY_CAP)
    ap.add_argument("--delay", type=int, default=45)
    a = ap.parse_args()

    if PAUSED.exists():
        sys.exit("PAUSED file present — refusing to send. Delete it to resume.")

    leads = list(csv.DictReader(LEADS.open(newline="", encoding="utf-8")))
    copy = json.loads(EMAILS.read_text(encoding="utf-8")) if EMAILS.exists() else {}
    sent_before, dnc = already_sent(), opted_out()

    queue, skipped = [], []
    for lead in leads:
        name = lead["Business Name"].strip()
        meta = copy.get(name, {})
        addr = ((lead.get("Email") or meta.get("email") or "").strip().lower())
        if not addr or "@" not in addr:
            skipped.append((lead, "Skipped - No Email Found")); continue
        if addr in dnc:
            skipped.append((lead, "Opted Out")); continue
        if addr in sent_before:
            continue  # already contacted, silently skip
        if not meta.get("subject") or not meta.get("body"):
            skipped.append((lead, "Skipped - No Copy Written")); continue
        queue.append((lead, addr, meta))

    done_today = sent_today()
    remaining = max(0, DAILY_CAP - done_today)
    if done_today:
        print(f"Already sent {done_today} today; {remaining} left under the {DAILY_CAP}/day cap.")
    if remaining == 0:
        print(f"DAILY CAP REACHED ({DAILY_CAP}). Nothing sent — protects the Gmail account.")
        return
    queue = queue[: max(0, min(a.limit, remaining))]
    print(f"{'SEND' if a.send else 'DRY RUN'}: {len(queue)} to send, {len(skipped)} skipped")
    for lead, addr, meta in queue:
        print(f"  -> {lead['Business Name']} <{addr}> | {meta['subject']}")
    if not a.send:
        return

    if not USER or not PW:
        sys.exit("ERROR: set GMAIL_USER and GMAIL_APP_PASSWORD.")

    rows, ok, fail = [], 0, 0
    ctx = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as s:
        s.starttls(context=ctx)
        s.login(USER, PW)
        for i, (lead, addr, meta) in enumerate(queue):
            msg = EmailMessage()
            msg["From"] = f"{SIGN} <{USER}>"
            msg["To"] = addr
            msg["Subject"] = meta["subject"]
            msg["Message-ID"] = make_msgid(domain="gmail.com")
            msg.set_content(meta["body"] + SIGNOFF.format(name=SIGN))
            try:
                s.send_message(msg); status = "Sent"; ok += 1
            except Exception as e:
                status = f"Failed - {type(e).__name__}"; fail += 1
                print(f"  !! {addr}: {e}")
            rows.append({**{k: lead.get(k, "") for k in FIELDS if k in lead},
                         "Email": addr, "Email Subject": meta["subject"],
                         "Date Sent": date.today().isoformat(), "Status": status})
            if i < len(queue) - 1:
                time.sleep(a.delay)

    for lead, status in skipped:
        rows.append({**{k: lead.get(k, "") for k in FIELDS if k in lead},
                     "Email Subject": copy.get(lead["Business Name"], {}).get("subject", ""),
                     "Date Sent": date.today().isoformat(), "Status": status})

    new = not SENT_LOG.exists() or SENT_LOG.stat().st_size == 0
    with SENT_LOG.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"\nSent {ok}, failed {fail}, skipped {len(skipped)}. Logged to sent_log.csv")


if __name__ == "__main__":
    main()
