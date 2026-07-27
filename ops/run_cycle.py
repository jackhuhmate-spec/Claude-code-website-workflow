#!/usr/bin/env python3
"""
run_cycle.py — the hourly/daily runner. This is what makes it 24/7.

Put this on any always-on box (VPS, Raspberry Pi, GitHub Actions) with cron:

    0 * * * *  cd /path/repo && ./ops/env.sh python3 ops/run_cycle.py replies
    0 10 * * * cd /path/repo && ./ops/env.sh python3 ops/run_cycle.py outreach

Modes:
    replies    read inbox, triage, draft replies, escalate to Jake  (safe: drafts only unless --auto)
    outreach   dry-run the send batch and report                     (safe: needs --auto to send)
    status     pipeline snapshot
"""
import argparse, csv, json, os, re, subprocess, sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
GMAIL = [sys.executable, str(HERE / "ops" / "gmail.py")]
REPLIES_LOG = HERE / "replies_log.csv"
DNC = HERE / "do_not_contact.csv"
TRIAGE = HERE / "triage"

PRICE = "£449 one-off build, optional £39/mo care plan"

OPTOUT = ["unsubscribe", "not interested", "no thanks", "no thank you", "remove me",
          "stop emailing", "take me off", "don't contact", "do not contact"]
DEAL = ["let's do it", "lets do it", "go ahead", "happy to proceed", "sign me up",
        "when can you start", "i'll take it", "deposit", "invoice", "bank details",
        "sounds good let's", "yes please do", "deal"]
INTERESTED = ["how much", "price", "cost", "quote", "interested", "tell me more",
              "mockup", "send it", "what would", "keen", "ok if you can make a price"]
QUESTION = ["?", "how long", "what's included", "whats included", "do i own", "seo",
            "hosting", "domain"]
AUTO = ["out of office", "automatic reply", "auto-reply", "on annual leave",
        "away from the office", "delivery status notification", "undeliverable"]
INJECTION = ["ignore previous", "ignore all previous", "disregard your instructions",
             "system prompt", "you are now", "new instructions", "send an email to",
             "forward this to", "run the following"]


def sh(args):
    r = subprocess.run(args, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def categorise(m):
    body = (m.get("body") or "").lower()
    subj = (m.get("subject") or "").lower()
    t = subj + " " + body
    if any(k in t for k in INJECTION):
        return "SUSPICIOUS"
    if any(k in t for k in AUTO):
        return "AUTO"
    if any(k in t for k in OPTOUT):
        return "OPTOUT"
    if any(k in t for k in DEAL):
        return "DEAL"
    if any(k in t for k in INTERESTED):
        return "INTERESTED"
    if any(k in t for k in QUESTION):
        return "QUESTION"
    return "REVIEW"


def draft_for(cat, m):
    who = m["from"]
    if cat == "INTERESTED":
        return (f"Thanks for getting back to me.\n\n"
                f"It's {PRICE} — the care plan covers hosting, updates and any fixes, "
                f"and you can cancel it any time. Payment on completion, and I can do "
                f"50% up front if you'd rather split it.\n\n"
                f"I'll put a free mockup together so you can see it before you commit. "
                f"Can you send me your main services, your best contact number, and the "
                f"email you want enquiries going to?")
    if cat == "QUESTION":
        return ("Good question — happy to run through it.\n\n"
                "It's a 5-page site (home, services, about, gallery, contact), built "
                "mobile-first, usually live within a few days. You own the domain and "
                "all the content outright — nothing is locked to me.\n\n"
                f"{PRICE}. Anything else you want to know before I put a mockup together?")
    if cat == "DEAL":
        return ("Brilliant — glad to be working with you.\n\n"
                "To get started I need: your full services list, opening hours, best "
                "contact number and enquiry email, your service area, and a logo if you "
                "have one. Photos of recent work help a lot too.\n\n"
                "Send those over and I'll have a first version for you to look at in a "
                "few days.")
    return None


def cmd_replies(a):
    TRIAGE.mkdir(exist_ok=True)
    code, out, err = sh(GMAIL + ["read", "--new", "--days", str(a.days)])
    if code != 0:
        print(f"INBOX READ FAILED:\n{err}"); sys.exit(1)
    msgs = json.loads(out)

    buckets, actions = {}, []
    for m in msgs:
        cat = categorise(m)
        buckets.setdefault(cat, []).append(m)

        if cat == "OPTOUT":
            with DNC.open("a", encoding="utf-8") as f:
                f.write(f"{m['from']},opted out {date.today()}\n")
            sh(GMAIL + ["mark", "--id", m["messageId"]])
            actions.append(f"OPT-OUT  {m['from']} → added to do_not_contact.csv, no reply")
            continue

        if cat == "AUTO":
            sh(GMAIL + ["mark", "--id", m["messageId"]])
            actions.append(f"AUTO     {m['from']} → ignored")
            continue

        if cat == "SUSPICIOUS":
            actions.append(f"⚠ INJECTION ATTEMPT {m['from']} — not actioned, escalated to Jake")
            continue

        if not m.get("known"):
            actions.append(f"UNKNOWN  {m['from']} ({cat}) → not a lead we contacted, left for Jake")
            continue

        body = draft_for(cat, m)
        if body:
            if a.auto:
                c, o, e = sh(GMAIL + ["send", "--to", m["from"], "--thread", m["messageId"],
                                      "--subject", "Re: " + re.sub(r"^(Re:\s*)+", "", m["subject"], flags=re.I),
                                      "--body", body])
                if c == 0:
                    sh(GMAIL + ["mark", "--id", m["messageId"]])
                    with REPLIES_LOG.open("a", newline="", encoding="utf-8") as f:
                        csv.writer(f).writerow([m.get("fromName", ""), m["from"], cat,
                                                "Auto-replied", date.today()])
                    actions.append(f"SENT     {cat:10} → {m['from']}")
                else:
                    actions.append(f"FAILED   {m['from']}: {e.strip()[:80]}")
            else:
                p = TRIAGE / f"{m['from'].replace('@','_at_')}.txt"
                p.write_text(f"TO: {m['from']}\nCAT: {cat}\nSUBJ: Re: {re.sub(r"^(Re:\s*)+", "", m["subject"], flags=re.I)}\n"
                             f"THREAD: {m['messageId']}\n\n{body}\n", encoding="utf-8")
                actions.append(f"DRAFTED  {cat:10} → {m['from']}  ({p.name})")
        else:
            actions.append(f"REVIEW   {m['from']} → needs Jake")

    print(f"\n{'='*64}\nREPLY CYCLE  {datetime.now():%Y-%m-%d %H:%M}   mode={'AUTO-SEND' if a.auto else 'DRAFT ONLY'}\n{'='*64}")
    print(f"Real messages: {len(msgs)}   " + "  ".join(f"{k}:{len(v)}" for k, v in buckets.items()))
    print()
    for x in actions:
        print("  " + x)
    hot = [m for c in ("DEAL", "INTERESTED") for m in buckets.get(c, [])]
    if hot:
        print(f"\n🔥 ESCALATE TO JAKE — {len(hot)} hot lead(s):")
        for m in hot:
            print(f"   {m['from']}  |  {m['subject']}")
            print(f"      \"{' '.join(m['body'].split())[:160]}\"")
    print()


def cmd_outreach(a):
    if (HERE / "PAUSED").exists():
        print("PAUSED — nothing sent."); return
    code, out, err = sh(GMAIL + ["test"])
    print(out or err)
    if code != 0:
        print("Connection test failed, aborting."); sys.exit(1)
    cmd = [sys.executable, str(HERE / "ops" / "gmail_send_batch.py")]
    if a.auto:
        cmd += ["--send", "--limit", str(a.limit), "--delay", "45"]
    c, o, e = sh(cmd)
    print(o or e)


def cmd_status(a):
    def count(p, pred=lambda r: True):
        if not Path(p).exists():
            return 0
        with open(p, newline="", encoding="utf-8") as f:
            return sum(1 for r in csv.DictReader(f) if pred(r))
    print(f"leads          {count(HERE/'leads.csv')}")
    print(f"sent           {count(HERE/'sent_log.csv', lambda r: (r.get('Status') or '').startswith('Sent'))}")
    print(f"replies logged {count(HERE/'replies_log.csv')}")
    print(f"opted out      {max(0, len((HERE/'do_not_contact.csv').read_text().splitlines())-1) if (HERE/'do_not_contact.csv').exists() else 0}")
    print(f"paused         {(HERE/'PAUSED').exists()}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("replies"); r.set_defaults(fn=cmd_replies)
    r.add_argument("--days", type=int, default=3)
    r.add_argument("--auto", action="store_true", help="Actually send replies (default: draft only).")
    o = sub.add_parser("outreach"); o.set_defaults(fn=cmd_outreach)
    o.add_argument("--auto", action="store_true"); o.add_argument("--limit", type=int, default=30)
    s = sub.add_parser("status"); s.set_defaults(fn=cmd_status)
    a = ap.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
