#!/usr/bin/env python3
"""
followups.py — multi-touch follow-up sequence.

For every lead we emailed who has NOT replied and is NOT opted out, sends the next
due follow-up: touch 1 at day 3, touch 2 at day 7, touch 3 (breakup) at day 14,
measured from the original send date. At most one touch per lead per run. Idempotent
via followups_log.csv. Sends via Brevo (From Jake, Reply-To Jake). Dry-run by default.

Usage:
    BREVO_API_KEY=... python3 followups.py --send --sign "Jake" --from-email jake@...
"""
import argparse, csv, json, os, ssl, sys, time, urllib.request
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEADS, SENT_LOG = HERE / "leads.csv", HERE / "sent_log.csv"
REPLIES_LOG, FU_LOG = HERE / "replies_log.csv", HERE / "followups_log.csv"
DNC = HERE / "do_not_contact.csv"
API_URL = "https://api.brevo.com/v3/smtp/email"
CA = os.environ.get("SSL_CERT_FILE") or "/root/.ccr/ca-bundle.crt"

# (min_days_since_original, touch_number, body_template)  — {b}=business, {a}=area
TOUCHES = [
    (3, 1, "Hi — just circling back on my note about {b}'s website. Happy to put together a quick free example so you can see exactly what I mean — worth a look?"),
    (7, 2, "Hi again — I know things get busy running {b}. If pulling in more {a} customers from your website sounds useful, I can have a clean, modern one live within a few days. Want me to send an example?"),
    (14, 3, "Hi — I'll leave it here after this one so I'm not cluttering your inbox. If you ever want a website that actually brings {a} customers your way, just reply and I'll get it sorted."),
]
SIGN_TAIL = "\n\nBest,\n{name}\n(If you'd rather I didn't follow up, just reply and let me know.)\n"


def load(p):
    return list(csv.DictReader(open(p, newline="", encoding="utf-8"))) if p.exists() else []


def emails_in(path, col=0):
    out = set()
    if path.exists():
        for r in csv.reader(open(path, newline="", encoding="utf-8")):
            if len(r) > col and "@" in r[col]:
                out.add(r[col].strip().lower())
    return out


def send_brevo(api_key, sign, frm, to, subject, body):
    ctx = ssl.create_default_context(cafile=CA if os.path.exists(CA) else None)
    op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx), urllib.request.ProxyHandler())
    payload = {"sender": {"name": sign, "email": frm}, "to": [{"email": to}],
               "replyTo": {"email": frm, "name": sign}, "subject": subject,
               "textContent": body + SIGN_TAIL.format(name=sign)}
    req = urllib.request.Request(API_URL, data=json.dumps(payload).encode(), method="POST",
                                 headers={"api-key": api_key, "content-type": "application/json"})
    with op.open(req, timeout=30) as r:
        return r.status


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--sign", default=os.environ.get("SIGN_NAME", "Jake"))
    ap.add_argument("--from-email", default=os.environ.get("FROM_EMAIL", ""))
    ap.add_argument("--api-key", default=os.environ.get("BREVO_API_KEY", ""))
    ap.add_argument("--delay", type=int, default=5)
    a = ap.parse_args()

    leads = {r["Business Name"]: r for r in load(LEADS)}
    sent = [r for r in load(SENT_LOG) if r.get("Status") == "Sent"]
    replied = emails_in(REPLIES_LOG, 1) | {r.get("email", "").lower() for r in load(REPLIES_LOG)}
    optout = emails_in(DNC)
    # count touches already sent per email
    done = {}
    for r in load(FU_LOG):
        done[r["email"].lower()] = max(done.get(r["email"].lower(), 0), int(r.get("touch", 0)))

    today = date.today()
    todo = []
    for r in sent:
        email = (r.get("Email") or "").lower().strip()
        if not email or email in replied or email in optout:
            continue
        try:
            d0 = datetime.fromisoformat(r["Date Sent"]).date()
        except Exception:
            continue
        days = (today - d0).days
        have = done.get(email, 0)
        for min_days, touch, tmpl in TOUCHES:
            if touch == have + 1 and days >= min_days:
                lead = leads.get(r["Business Name"], {})
                area = lead.get("London Area", "local")
                body = tmpl.format(b=r["Business Name"], a=area)
                subj = "Re: " + (r.get("Email Subject", "your website") or "your website")
                todo.append((r["Business Name"], email, touch, subj, body))
                break

    if not todo:
        print("No follow-ups due.")
        return
    live = a.send and a.api_key and a.from_email
    if a.send and not live:
        sys.exit("ERROR: --send needs --api-key and --from-email.")

    log_new = []
    for biz, email, touch, subj, body in todo:
        if live:
            try:
                st = send_brevo(a.api_key, a.sign, a.from_email, email, subj, body)
                ok = st in (200, 201)
                print(f"{'SENT' if ok else 'FAIL'} touch{touch}  {biz} -> {email}")
                if ok:
                    log_new.append([biz, email, touch, today.isoformat()])
                time.sleep(a.delay)
            except Exception as e:
                print(f"FAIL touch{touch} {biz}: {e}")
        else:
            print(f"DUE  touch{touch}  {biz} -> {email}")

    if log_new:
        new = not FU_LOG.exists()
        with open(FU_LOG, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["business", "email", "touch", "date"])
            w.writerows(log_new)
    print(f"\n{'SENT' if live else 'DRY-RUN'}: {len(todo)} follow-up(s) due.")


if __name__ == "__main__":
    main()
