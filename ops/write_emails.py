#!/usr/bin/env python3
"""
write_emails.py — AI copywriter (Agent 2).

Writes a personalised cold email for every lead in leads.csv that has an address,
hasn't been contacted, and has no copy in emails.json yet.

    python3 ops/write_emails.py            # dry run, prints what it would write
    python3 ops/write_emails.py --write    # save to emails.json + emails.md

Needs GROQ_API_KEY. Without it, exits cleanly and changes nothing.
"""
import argparse, csv, json, sys
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import brain

LEADS = HERE / "leads.csv"
EMAILS = HERE / "emails.json"
EMAILS_MD = HERE / "emails.md"
SENT_LOG = HERE / "sent_log.csv"


def already_sent():
    out = set()
    if SENT_LOG.exists():
        with SENT_LOG.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                a = (r.get("Email") or "").strip().lower()
                if a and (r.get("Status") or "").startswith("Sent"):
                    out.add(a)
    return out


def too_similar(new, existing, threshold=0.72):
    """Reject copy that reads like something we've already written."""
    for old in existing:
        if SequenceMatcher(None, new.lower(), old.lower()).ratio() > threshold:
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--limit", type=int, default=40)
    a = ap.parse_args()

    if not brain.available():
        print("GROQ_API_KEY not set — cannot write copy. Nothing changed.")
        sys.exit(0)

    leads = list(csv.DictReader(LEADS.open(newline="", encoding="utf-8")))
    copy = json.loads(EMAILS.read_text(encoding="utf-8")) if EMAILS.exists() else {}
    sent = already_sent()

    todo = [l for l in leads
            if (l.get("Email") or "").strip()
            and (l["Email"] or "").strip().lower() not in sent
            and l["Business Name"].strip() not in copy][: a.limit]

    if not todo:
        print("No leads need copy. Run the lead hunter to find more businesses.")
        return

    print(f"{'WRITING' if a.write else 'DRY RUN'}: {len(todo)} lead(s) need copy\n")
    recent = [v.get("body", "") for v in list(copy.values())[-12:]]
    written, rejected = 0, 0

    for l in todo:
        name = l["Business Name"].strip()
        e = None
        for attempt in range(3):
            cand = brain.write_cold_email(name, l.get("Trade", ""), l.get("London Area", ""),
                                          l.get("Biggest Flaw", ""), l.get("Group", "A"))
            if not cand:
                continue
            if too_similar(cand["body"], recent):
                rejected += 1
                continue
            e = cand
            break

        if not e:
            print(f"  SKIP  {name} — could not produce distinct copy")
            continue

        copy[name] = {"email": l["Email"].strip(), "subject": e["subject"], "body": e["body"]}
        recent.append(e["body"])
        written += 1
        print(f"  [{written}] {name} ({l.get('London Area','')})")
        print(f"      SUBJ: {e['subject']}")
        print(f"      {e['body'][:150]}...")

    if not a.write:
        print(f"\nDry run. {written} would be written, {rejected} rejected as too similar.")
        return

    EMAILS.write_text(json.dumps(copy, indent=1, ensure_ascii=False), encoding="utf-8")
    with EMAILS_MD.open("a", encoding="utf-8") as f:
        for l in todo:
            n = l["Business Name"].strip()
            if n in copy:
                f.write(f"\n---\n\n## {n} — {l.get('Trade','')}, {l.get('London Area','')} "
                        f"{'✅' if l.get('Email') else '❌'} {l.get('Email','')}\n"
                        f"**Subject:** {copy[n]['subject']}\n\n{copy[n]['body']}\n")
    print(f"\nWrote {written} emails to emails.json ({rejected} rejected as too similar).")


if __name__ == "__main__":
    main()
