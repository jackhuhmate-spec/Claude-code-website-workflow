#!/usr/bin/env python3
"""
run_cycle.py — the hourly/daily runner. This is what makes it 24/7.

Put this on any always-on box (VPS, Raspberry Pi, GitHub Actions) with cron:

    0 * * * *  cd /path/repo && ./ops/env.sh python3 ops/run_cycle.py replies
    0 10 * * * cd /path/repo && ./ops/env.sh python3 ops/run_cycle.py outreach

Modes:
    replies    read inbox, triage, draft replies, escalate to Jack  (safe: drafts only unless --auto)
    outreach   dry-run the send batch and report                     (safe: needs --auto to send)
    status     pipeline snapshot
"""
import argparse, csv, json, re, subprocess, sys
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import brain
except Exception:
    brain = None
try:
    import quota
except Exception:
    quota = None
GMAIL = [sys.executable, str(HERE / "ops" / "gmail.py")]
REPLIES_LOG = HERE / "replies_log.csv"
DNC = HERE / "do_not_contact.csv"
BOUNCED = HERE / "bounced_emails.csv"
TRIAGE = HERE / "triage"

# Patterns for the recipient of a Gmail delivery-failure notification.
_BOUNCE_RECIP = re.compile(
    r"(?:Final-Recipient|X-Failed-Recipients|Original-Recipient)[:\s]*rfc822;\s*(\S+@\S+)",
    re.I,
)
_BOUNCE_BODY = re.compile(r"[<\[](\S+@\S+\.\S{2,})[>\]]")


def _bounced() -> set[str]:
    """Addresses Gmail told us are undeliverable — never send to them again."""
    if not BOUNCED.exists():
        return set()
    return {line.split(",")[0].strip().lower() for line in
            BOUNCED.read_text(encoding="utf-8").splitlines()
            if line.strip() and line.strip() != "email"}


def _log_bounced(addr: str) -> None:
    addr = (addr or "").strip().lower()
    if not addr or "@" not in addr:
        return
    if addr in _bounced():
        return
    with BOUNCED.open("a", newline="", encoding="utf-8") as f:
        f.write(f"{addr},{date.today()},bounce\n")

PRICE = "£449 one-off build, optional £39/mo care plan"

OPTOUT = ["unsubscribe", "not interested", "no thanks", "no thank you", "remove me",
          "stop emailing", "take me off", "don't contact", "do not contact"]
DEAL = ["let's do it", "lets do it", "go ahead", "happy to proceed", "sign me up",
        "when can you start", "i'll take it", "deposit", "invoice", "bank details",
        "sounds good let's", "yes please do"]
# "deal" as a bare substring also matches "we already have a deal with our current
# guy" — a brush-off that must never get the "glad to be working with you" reply.
# It is matched in categorise() as a whole word with a negation instead.
INTERESTED = ["how much", "price", "cost", "quote", "interested", "tell me more",
              "mockup", "send it", "what would", "keen", "ok if you can make a price"]
QUESTION = ["?", "how long", "what's included", "whats included", "do i own", "seo",
            "hosting", "domain"]
AUTO = ["out of office", "automatic reply", "auto-reply", "on annual leave",
        "away from the office", "delivery status notification", "undeliverable"]
INJECTION = ["ignore previous", "ignore all previous", "disregard your instructions",
             "system prompt", "you are now", "new instructions", "send an email to",
             "forward this to", "run the following"]
OBJECTION = ["too expensive", "too much", "out of my budget", "don't have the budget",
             "can't afford", "overpriced", "a bit steep",
             "already have someone", "already have a guy",
             "happy with my current", "not right now", "not at this time",
             "maybe later", "some other time", "not interested at this time",
             "bit busy", "not a priority"]


def sh(args, timeout=900):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout}s: {' '.join(str(x) for x in args[-3:])}"


def categorise_ai(m):
    """LLM classification. Returns (category, meta) or (None, None) to fall back."""
    if not (brain and brain.available()):
        return None, None
    try:
        d = brain.classify(m.get("subject", ""), m.get("body", ""), m.get("from", ""))
        if not d:
            return None, None
        cat = d["category"]
        # The model sometimes emits confidence as a string ("85"); a raw < comparison
        # then raises TypeError and kills the whole cycle. Coerce defensively.
        try:
            conf = int(d.get("confidence", 0) or 0)
        except (TypeError, ValueError):
            conf = 0
        # A request to stop contact is honoured regardless of confidence — never risk
        # a PECR breach because the model was unsure about a "take me off your list".
        if cat == "OPTOUT":
            return "OPTOUT", d
        # Low confidence must never auto-send. Push it to a human.
        if conf < 70 and cat in ("DEAL", "INTERESTED", "QUESTION", "OBJECTION"):
            return "REVIEW", d
        return cat, d
    except Exception:
        # One malformed LLM response must degrade to keywords, not abort the cycle.
        return None, None


def categorise(m):
    body = (m.get("body") or "").lower()
    subj = (m.get("subject") or "").lower()
    t = subj + " " + body
    if any(k in t for k in INJECTION):
        return "SUSPICIOUS"
    if any(k in t for k in AUTO):
        return "AUTO"
    has_question = "?" in t
    # An opt-out phrase WITH a question ("no thanks, but how much?") is a live
    # prospect, not a stop-contact — auto-DNCing it kills a real lead. Only treat
    # as OPTOUT when there is no question mark, so those fall through to
    # INTERESTED/QUESTION below.
    if any(k in t for k in OPTOUT) and not has_question:
        return "OPTOUT"
    # "deal" must be a whole word and not "already have a deal" (a brush-off).
    deal_word = bool(re.search(r"\bdeal\b", t)) and "already have" not in t
    if any(k in t for k in DEAL) or deal_word:
        return "DEAL"
    if any(k in t for k in INTERESTED):
        return "INTERESTED"
    if any(k in t for k in OBJECTION):
        return "OBJECTION"
    if any(k in t for k in QUESTION) or has_question:
        return "QUESTION"
    return "REVIEW"


def draft_for(cat, m):
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
    ai_used = 0
    for m in msgs:
        cat, meta = categorise_ai(m)
        if cat:
            ai_used += 1
            m["_ai"] = meta
        else:
            cat = categorise(m)
        # Keyword injection check always runs as a second opinion, even when AI is used.
        if categorise(m) == "SUSPICIOUS":
            cat = "SUSPICIOUS"
        buckets.setdefault(cat, []).append(m)

        if cat == "OPTOUT":
            # Dedup: only append if not already in DNC
            if DNC.exists():
                existing = {line.split(",")[0].strip().lower() for line in
                            DNC.read_text(encoding="utf-8").splitlines() if line.strip() and line.strip() != "email"}
            else:
                existing = set()
            if m["from"].strip().lower() not in existing:
                with DNC.open("a", encoding="utf-8") as f:
                    f.write(f"{m['from']},opted out {date.today()}\n")
            sh(GMAIL + ["mark", "--id", m["messageId"]])
            actions.append(f"OPT-OUT  {m['from']} → added to do_not_contact.csv, no reply")
            continue

        if cat == "AUTO":
            # A delivery-failure notice means one of our emails bounced — record the
            # address so no sender ever tries it again (cold batch, follow-ups, hunter).
            subj = (m.get("subject") or "").lower()
            body = (m.get("body") or "")
            if ("delivery status" in subj or "undeliverable" in subj or "failed" in subj
                    or "final-recipient" in body.lower()):
                mo = _BOUNCE_RECIP.search(body) or _BOUNCE_BODY.search(body)
                if mo:
                    _log_bounced(mo.group(1))
                    actions.append(f"BOUNCE   {mo.group(1)} → added to bounced_emails.csv, never resent")
            sh(GMAIL + ["mark", "--id", m["messageId"]])
            actions.append(f"AUTO     {m['from']} → ignored")
            continue

        if cat == "SUSPICIOUS":
            sh(GMAIL + ["mark", "--id", m["messageId"]])
            with REPLIES_LOG.open("a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([m.get("fromName", ""), m["from"], "SUSPICIOUS",
                                        "Not actioned - escalated", date.today()])
            actions.append(f"⚠ INJECTION ATTEMPT {m['from']} — not actioned, escalated to Jack")
            continue

        if m.get("alreadyReplied") and not a.force:
            sh(GMAIL + ["mark", "--id", m["messageId"]])
            actions.append(f"SKIP     {m['from']} → already replied {m.get('lastReplyDate','')[:16]}, not re-answering")
            continue

        if not m.get("known"):
            actions.append(f"UNKNOWN  {m['from']} ({cat}) → not a lead we contacted, left for Jack")
            continue

        body = None
        if brain and brain.available() and cat in ("INTERESTED", "QUESTION", "DEAL", "OBJECTION"):
            body = brain.write_reply(cat, m.get("subject", ""), m.get("body", ""),
                                     m.get("fromName", ""), m.get("from", ""))
            if body and len(body.split()) > 160:
                body = None  # too long, model rambled - use the safe template
            if body and re.search(r"I can'?t assist|as an AI|I am an AI|I'm sorry,? but I|"
                                  r"cannot help with that|language model", body, re.I):
                body = None  # model refused - never send a refusal to a customer
        if not body:
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
            sh(GMAIL + ["mark", "--id", m["messageId"]])
            p = TRIAGE / f"REVIEW-{m['from'].replace('@','_at_')}.txt"
            TRIAGE.mkdir(exist_ok=True)
            p.write_text(f"NEEDS JACK\nFROM: {m['from']}\nCAT: {cat}\n"
                         f"SUBJ: {m['subject']}\n\n{m['body'][:1500]}\n", encoding="utf-8")
            actions.append(f"REVIEW   {m['from']} → needs Jack ({p.name})")

    print(f"\n{'='*64}\nREPLY CYCLE  {datetime.now():%Y-%m-%d %H:%M}   mode={'AUTO-SEND' if a.auto else 'DRAFT ONLY'}\n{'='*64}")
    engine = f"AI ({brain.MODEL})" if ai_used else "keywords"
    print(f"Real messages: {len(msgs)}   engine={engine} ({ai_used} AI-classified)   "
          + "  ".join(f"{k}:{len(v)}" for k, v in buckets.items()))
    print()
    for x in actions:
        print("  " + x)
    urgent = [(c, m) for c in ("SUSPICIOUS", "REVIEW") for m in buckets.get(c, [])]
    if urgent:
        print(f"\n⚠ ESCALATE TO JACK — {len(urgent)} message(s) needing a human:")
        for c, m in urgent:
            print(f"   [{c}] {m['from']}  |  {m['subject']}")
            if m.get("_ai"):
                print(f"      {m['_ai'].get('reason','')}")

    hot = [m for c in ("DEAL", "INTERESTED") for m in buckets.get(c, [])]
    if hot:
        print(f"\n🔥 ESCALATE TO JACK — {len(hot)} hot lead(s):")
        for m in hot:
            print(f"   {m['from']}  |  {m['subject']}")
            if m.get("_ai"):
                print(f"      summary: {m['_ai'].get('summary','')}")
            print(f"      \"{' '.join(m['body'].split())[:160]}\"")
        # The money only counts when it's on the ledger — remind Jack how to log it.
        print("\n   When payment lands, log it with:  python3 ops/record_payment.py "
              "'Business Name' --amount 449 --status paid")
    print()


def _cold_waiting():
    """How many leads are actually queued for a FIRST email right now.

    A cheap peek at the same queue gmail_send_batch builds: an email address, not
    yet contacted, not opted out, with copy written. Used to reserve cap for cold
    outreach so the follow-up backlog can't starve it.
    """
    sent, dnc = set(), set()
    if (HERE / "sent_log.csv").exists():
        with (HERE / "sent_log.csv").open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if (r.get("Status") or "").startswith("Sent"):
                    a = (r.get("Email") or "").strip().lower()
                    if a:
                        sent.add(a)
    if (HERE / "do_not_contact.csv").exists():
        for line in (HERE / "do_not_contact.csv").read_text(encoding="utf-8").splitlines():
            a = line.split(",")[0].strip().lower()
            if "@" in a:
                dnc.add(a)
    with_copy = set()
    if (HERE / "emails.json").exists():
        with_copy = set(json.loads((HERE / "emails.json").read_text(encoding="utf-8")))
    n = 0
    for r in csv.DictReader((HERE / "leads.csv").open(newline="", encoding="utf-8")):
        a = (r.get("Email") or "").strip().lower()
        if (a and a not in sent and a not in dnc
                and r.get("Business Name", "").strip() in with_copy):
            n += 1
    return n


def cmd_outreach(a):
    if (HERE / "PAUSED").exists():
        print("PAUSED — nothing sent."); return

    # Top the funnel up first: hunt fresh leads, rotating London tile by day.
    tile = date.today().toordinal() % 8
    hc, ho, he = sh([sys.executable, str(HERE / "ops" / "lead_hunter.py"),
                     "--write", "--tile", str(tile), "--max", "15"], timeout=600)
    print(ho.strip()[-600:] or he.strip()[:300])
    if hc == 124:
        print("Lead hunter timed out — carrying on with existing leads.")

    # Write copy for any new leads first (no-op without GROQ_API_KEY).
    wc, wo, we = sh([sys.executable, str(HERE / "ops" / "write_emails.py"), "--write"], timeout=600)
    print(wo.strip()[-800:] or we.strip()[:300])
    code, out, err = sh(GMAIL + ["test"])
    print(out or err)
    if code != 0:
        print("Connection test failed, aborting."); sys.exit(1)

    # Follow-ups run BEFORE the cold batch and share the same daily cap. A day-3 touch
    # is due on day 3 or it is late; a lead found this morning loses nothing by being
    # emailed tomorrow. Touch 2 and 3 also convert far better than a first contact.
    # But the follow-up backlog must not starve NEW cold outreach: reserve up to 15
    # sends for leads actually waiting for a first email, and cap follow-ups at the rest.
    waiting = _cold_waiting()
    reserve = min(15, waiting)
    fu_limit = max(0, quota.DAILY_CAP - reserve)
    print(f"\n--- follow-ups (capped at {fu_limit}/{quota.DAILY_CAP}; "
          f"{reserve} reserved for {waiting} waiting cold leads) ---")
    fu = [sys.executable, str(HERE / "ops" / "followups.py")]
    if a.auto:
        fu += ["--send", "--limit", str(fu_limit), "--delay", "45"]
    fc, fo, fe = sh(fu, timeout=1800)
    print(fo.strip() or fe.strip()[:300])

    print("\n--- cold batch ---")
    cmd = [sys.executable, str(HERE / "ops" / "gmail_send_batch.py")]
    if a.auto:
        cmd += ["--send", "--limit", str(a.limit), "--delay", "45"]
    c, o, e = sh(cmd, timeout=1800)
    print(o or e)
    if "0 to send" in (o or ""):
        print("\n*** PIPELINE EMPTY — no leads left to contact. ***")
        print("Run the lead hunter to add businesses to leads.csv, or the machine idles.")


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
    r.add_argument("--force", action="store_true", help="Reply even if Sent Mail shows we already answered.")
    o = sub.add_parser("outreach"); o.set_defaults(fn=cmd_outreach)
    o.add_argument("--auto", action="store_true"); o.add_argument("--limit", type=int, default=30)
    s = sub.add_parser("status"); s.set_defaults(fn=cmd_status)
    a = ap.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
