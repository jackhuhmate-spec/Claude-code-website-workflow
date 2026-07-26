#!/usr/bin/env python3
"""
reply_monitor.py — Job 5 reply manager.

Checks a Gmail inbox (IMAP) for replies from the addresses in sent_log.csv,
categorises each as Interested / Not Interested / Question / Gone Quiet, and
DRAFTS a suggested response for every Interested or Question reply.

It never sends anything. Drafts are written to drafts/ and a summary is printed,
so you approve (and send) each one yourself. Run it daily (e.g. a 9am cron / the
claude-code-remote scheduler).

Usage:
    GMAIL_USER=you@gmail.com GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx" \
        python3 reply_monitor.py --sign "Your Name"

Categorisation is keyword-based as a first pass; anything ambiguous is flagged
"Question" so it lands in your review queue rather than being silently dropped.
"""
import argparse
import csv
import email
import imaplib
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from pathlib import Path

HERE = Path(__file__).resolve().parent
SENT_LOG = HERE / "sent_log.csv"
DRAFTS = HERE / "drafts"

INTERESTED = ["how much", "price", "cost", "quote", "interested", "tell me more",
              "sounds good", "keen", "yes please", "go ahead", "let's do", "call"]
NOT_INTERESTED = ["not interested", "no thanks", "no thank you", "remove", "unsubscribe",
                  "stop emailing", "not for us", "already have"]
QUESTION = ["?", "what", "how", "when", "which", "can you", "do you", "would you"]


def decode(s):
    if not s:
        return ""
    parts = decode_header(s)
    out = ""
    for text, enc in parts:
        out += text.decode(enc or "utf-8", "ignore") if isinstance(text, bytes) else text
    return out


def sender_addr(raw):
    m = re.search(r"[\w.+-]+@[\w.-]+", raw or "")
    return m.group(0).lower() if m else ""


def categorise(body):
    low = body.lower()
    if any(k in low for k in NOT_INTERESTED):
        return "Not Interested"
    if any(k in low for k in INTERESTED):
        return "Interested"
    if any(k in low for k in QUESTION):
        return "Question"
    return "Question"  # default to review queue rather than dropping


def draft_reply(category, business, body, sign):
    low = body.lower()
    if category == "Interested" and any(k in low for k in ["price", "cost", "how much", "quote"]):
        return (f"Hi,\n\nGreat to hear from you. Rather than bury it in an email, I'd love to jump "
                f"on a quick 10-minute call and walk you through exactly what you get and what it "
                f"costs for {business} — no pressure either way.\n\nWould Tuesday or Thursday "
                f"afternoon this week suit you? Happy to work around your jobs.\n\nBest,\n{sign}")
    if "look like" in low or "example" in low or "design" in low or "see" in low:
        return (f"Hi,\n\nAbsolutely. I'll put together two example designs based on {business} and "
                f"send them over within 24 hours, so you can see exactly the kind of site I'd build "
                f"for you.\n\nNothing to commit to — just have a look and tell me what you think.\n\n"
                f"Best,\n{sign}")
    # Generic interested / question
    return (f"Hi,\n\nThanks for getting back to me. Happy to answer that properly — I'd love to "
            f"grab 10 minutes on a call to talk through what would work best for {business}. Would "
            f"a time this week suit you? I can also send over a couple of example designs first if "
            f"you'd rather see something concrete.\n\nBest,\n{sign}")


def gone_quiet_nudge(business, sign):
    return (f"Hi,\n\nJust following up on my note about {business}'s website — did you get a chance "
            f"to take a look? No worries if now's not the right time.\n\nBest,\n{sign}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sign", default=os.environ.get("SIGN_NAME", "[YOUR NAME]"))
    ap.add_argument("--gmail", default=os.environ.get("GMAIL_USER", ""))
    ap.add_argument("--app-password", default=os.environ.get("GMAIL_APP_PASSWORD", ""))
    ap.add_argument("--quiet-days", type=int, default=3, help="Days of silence before a nudge.")
    args = ap.parse_args()

    if not args.gmail or not args.app_password:
        sys.exit("ERROR: set GMAIL_USER and GMAIL_APP_PASSWORD (Gmail App Password).")

    if not SENT_LOG.exists():
        sys.exit("No sent_log.csv yet — run send_emails.py first.")

    with open(SENT_LOG, newline="", encoding="utf-8") as f:
        contacts = {r["Email"].lower(): r for r in csv.DictReader(f)
                    if r.get("Email") and r.get("Status") == "Sent"}

    if not contacts:
        print("No 'Sent' contacts in sent_log.csv yet — nothing to monitor.")
        return

    DRAFTS.mkdir(exist_ok=True)
    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    imap.login(args.gmail, args.app_password)
    imap.select("INBOX")

    replied = set()
    new_replies = interested = questions = 0
    actions = []

    _, data = imap.search(None, "ALL")
    for num in data[0].split():
        _, msg_data = imap.fetch(num, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        frm = sender_addr(msg.get("From"))
        if frm not in contacts:
            continue
        replied.add(frm)
        business = contacts[frm]["Business Name"]

        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body += part.get_payload(decode=True).decode("utf-8", "ignore")
        else:
            body = msg.get_payload(decode=True).decode("utf-8", "ignore")

        cat = categorise(body)
        new_replies += 1
        if cat == "Interested":
            interested += 1
        if cat == "Question":
            questions += 1

        if cat in ("Interested", "Question"):
            draft = draft_reply(cat, business, body, args.sign)
            path = DRAFTS / f"reply_{frm.replace('@', '_at_')}.txt"
            path.write_text(f"TO: {frm}\nRE: {business} — {cat}\n\n{draft}\n", encoding="utf-8")
            actions.append(f"  • {business} ({cat}) — draft ready: {path.name} [needs your approval]")
        elif cat == "Not Interested":
            actions.append(f"  • {business} (Not Interested) — no action, will not contact again")

    # Gone-quiet detection: contacted, no reply, past the quiet window
    for addr, row in contacts.items():
        if addr in replied:
            continue
        try:
            sent_on = datetime.fromisoformat(row["Date Sent"]).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if datetime.now(timezone.utc) - sent_on >= timedelta(days=args.quiet_days):
            business = row["Business Name"]
            draft = gone_quiet_nudge(business, args.sign)
            path = DRAFTS / f"nudge_{addr.replace('@', '_at_')}.txt"
            path.write_text(f"TO: {addr}\nRE: {business} — Gone Quiet nudge\n\n{draft}\n", encoding="utf-8")
            actions.append(f"  • {business} (Gone Quiet) — follow-up nudge drafted: {path.name} [needs your approval]")

    imap.logout()

    print("=" * 60)
    print(f"DAILY REPLY SUMMARY — {datetime.now(timezone.utc):%Y-%m-%d}")
    print("=" * 60)
    print(f"New replies: {new_replies}  |  Interested: {interested}  |  Questions: {questions}")
    print("\nNeeds your action today:")
    print("\n".join(actions) if actions else "  (nothing needs action)")
    print(f"\nDrafts saved to {DRAFTS}/ — review and send the ones you approve. Nothing was sent automatically.")


if __name__ == "__main__":
    main()
