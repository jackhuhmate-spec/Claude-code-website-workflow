#!/usr/bin/env python3
"""
followups.py — multi-touch follow-up sequence over Gmail SMTP.

Replaces the root-level followups.py, which still called Brevo. Brevo is dead, nothing
invoked it, and so 96 businesses were cold-emailed exactly once and never touched
again. Most replies to cold outreach come from touch 2 and 3, so this is the single
largest reply lever available without raising the daily cap.

For every lead we emailed who has not replied and is not opted out, sends the next due
touch: day 3, day 7, then a day-14 breakup, measured from the original send date.
At most one touch per lead per run. Idempotent via followups_log.csv.

    python3 ops/followups.py                    # dry run — shows what is due
    python3 ops/followups.py --send             # send, sharing the 30/day cap
    python3 ops/followups.py --send --limit 10  # send at most 10

Credentials: GMAIL_USER, GMAIL_APP_PASSWORD, SIGN_NAME.
"""
import argparse, csv, os, re, smtplib, ssl, sys, time
from datetime import date, datetime
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import quota

HERE = Path(__file__).resolve().parent.parent
LEADS = HERE / "leads.csv"
SENT_LOG = HERE / "sent_log.csv"
REPLIES_LOG = HERE / "replies_log.csv"
FU_LOG = HERE / "followups_log.csv"
DNC = HERE / "do_not_contact.csv"
PAUSED = HERE / "PAUSED"

USER = os.environ.get("GMAIL_USER", "")
PW = (os.environ.get("GMAIL_APP_PASSWORD", "") or "").replace(" ", "")
SIGN = os.environ.get("SIGN_NAME", "Jake")

# (min_days_since_original, touch_number, body)  — {b}=business, {a}=London area.
# No price is quoted at any touch: £449 stays a reply-stage conversation.
TOUCHES = [
    (3, 1, "Just circling back on my note about {b}'s website. Happy to put a quick "
           "free example together so you can see exactly what I mean — worth a look?"),
    (7, 2, "I know things get busy running {b}. If pulling in more {a} customers "
           "through your website would be useful, I can have a clean, mobile-friendly "
           "one live within a few days. Want me to send an example?"),
    (14, 3, "I'll leave it here after this one so I'm not cluttering your inbox. If "
            "you ever want a website that actually brings {a} customers your way, "
            "just reply and I'll sort it."),
]

SIGNOFF = ("\n\nBest,\n{name}\n\n"
           "(If you'd rather I didn't follow up, just reply \"no thanks\" and I won't email again.)")

FU_FIELDS = ["business", "email", "touch", "date"]


def load(p):
    if not p.exists():
        return []
    with p.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def opted_out():
    out = set()
    if DNC.exists():
        for line in DNC.read_text(encoding="utf-8").splitlines():
            a = line.split(",")[0].strip().lower()
            if a and "@" in a:
                out.add(a)
    return out


def replied():
    """Anyone who has answered us, by any route, must drop out of the sequence.

    Chasing someone who already replied is the fastest way to look like a bot and get
    reported as spam.
    """
    out = set()
    for r in load(REPLIES_LOG):
        for v in r.values():
            for m in re.findall(r"[^\s,<>]+@[^\s,<>]+", v or ""):
                out.add(m.strip().lower())
    return out


def touches_done():
    """Highest touch number already sent per address."""
    done = {}
    for r in load(FU_LOG):
        a = (r.get("email") or "").strip().lower()
        if not a:
            continue
        try:
            n = int(r.get("touch") or 0)
        except ValueError:
            continue
        done[a] = max(done.get(a, 0), n)
    return done


def first_sent():
    """Earliest genuine send date per address, with the business name and subject.

    Uses the earliest date so the day 3/7/14 clock is measured from first contact,
    not from a later log row for the same lead.
    """
    out = {}
    for r in load(SENT_LOG):
        if not (r.get("Status") or "").startswith("Sent"):
            continue
        a = (r.get("Email") or "").strip().lower()
        if not a or "@" not in a:
            continue
        try:
            d = datetime.fromisoformat((r.get("Date Sent") or "").strip()).date()
        except ValueError:
            continue
        prev = out.get(a)
        if prev is None or d < prev["date"]:
            out[a] = {"date": d, "business": (r.get("Business Name") or "").strip(),
                      "subject": (r.get("Email Subject") or "").strip()}
    return out


def due(today=None):
    """Follow-ups due right now, oldest original send first."""
    today = today or date.today()
    areas = {(r.get("Business Name") or "").strip(): (r.get("London Area") or "").strip()
             for r in load(LEADS)}
    skip = opted_out() | replied()
    done = touches_done()

    out = []
    for addr, info in first_sent().items():
        if addr in skip:
            continue
        days = (today - info["date"]).days
        have = done.get(addr, 0)
        for min_days, touch, tmpl in TOUCHES:
            if touch == have + 1 and days >= min_days:
                area = areas.get(info["business"]) or "local"
                subject = re.sub(r"^(Re:\s*)+", "", info["subject"], flags=re.I).strip()
                out.append({
                    "business": info["business"] or addr,
                    "email": addr,
                    "touch": touch,
                    "subject": "Re: " + (subject or "your website"),
                    "body": tmpl.format(b=info["business"] or "your business", a=area),
                    "days": days,
                })
                break
    out.sort(key=lambda x: (-x["days"], x["business"]))
    return out


def log_sent(rows):
    new = not FU_LOG.exists() or FU_LOG.stat().st_size == 0
    with FU_LOG.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FU_FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="Actually send (default: dry run).")
    ap.add_argument("--limit", type=int, default=quota.DAILY_CAP)
    ap.add_argument("--delay", type=int, default=45, help="Seconds between sends.")
    a = ap.parse_args()

    if PAUSED.exists():
        print("PAUSED file present — refusing to send follow-ups. Delete it to resume.")
        return

    pending = due()
    if not pending:
        print("No follow-ups due.")
        return

    left = quota.remaining()
    if left == 0:
        print(f"DAILY CAP REACHED ({quota.DAILY_CAP} incl. cold sends). "
              f"{len(pending)} follow-up(s) due — they will go out tomorrow.")
        return

    batch = pending[: max(0, min(a.limit, left))]
    print(f"{'SEND' if a.send else 'DRY RUN'}: {len(batch)} of {len(pending)} due "
          f"follow-up(s); {left} left under the {quota.DAILY_CAP}/day cap "
          f"({quota.cold_sent_today()} cold + {quota.followups_sent_today()} follow-ups sent today)")
    for r in batch:
        print(f"  -> touch{r['touch']}  {r['business']} <{r['email']}>  "
              f"(day {r['days']}) | {r['subject']}")
    if not a.send:
        print("\nDry run — pass --send to actually send.")
        return

    if not USER or not PW:
        sys.exit("ERROR: set GMAIL_USER and GMAIL_APP_PASSWORD.")

    logged, ok, fail = [], 0, 0
    ctx = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as s:
        s.starttls(context=ctx)
        s.login(USER, PW)
        for i, r in enumerate(batch):
            msg = EmailMessage()
            msg["From"] = f"{SIGN} <{USER}>"
            msg["To"] = r["email"]
            msg["Subject"] = r["subject"]
            msg["Message-ID"] = make_msgid(domain="gmail.com")
            msg.set_content(r["body"] + SIGNOFF.format(name=SIGN))
            try:
                s.send_message(msg)
                ok += 1
                # Log immediately per send, not in one batch at the end: a crash or an
                # SMTP disconnect halfway through must not cause a re-send tomorrow.
                row = {"business": r["business"], "email": r["email"],
                       "touch": r["touch"], "date": date.today().isoformat()}
                log_sent([row])
                logged.append(row)
                print(f"  SENT touch{r['touch']}  {r['business']} -> {r['email']}")
            except Exception as e:
                fail += 1
                print(f"  !! {r['email']}: {type(e).__name__}: {e}")
            if i < len(batch) - 1:
                time.sleep(a.delay)

    print(f"\nSent {ok}, failed {fail}. Logged to followups_log.csv")


if __name__ == "__main__":
    main()
