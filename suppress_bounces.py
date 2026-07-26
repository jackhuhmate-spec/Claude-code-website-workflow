#!/usr/bin/env python3
"""
suppress_bounces.py — auto list-hygiene.

Queries the Brevo transactional email events for hard bounces, blocked, invalid and
spam-complaint addresses, and adds them to do_not_contact.csv so they're never emailed
again. Run daily before sending. Safe to run repeatedly (dedupes).

Usage:
    BREVO_API_KEY=... python3 suppress_bounces.py [--days 30]
"""
import argparse, csv, json, os, ssl, urllib.parse, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DNC = HERE / "do_not_contact.csv"
CA = os.environ.get("SSL_CERT_FILE") or "/root/.ccr/ca-bundle.crt"
EVENTS = ["hardBounces", "blocked", "invalid", "spam"]


def _opener():
    ctx = ssl.create_default_context(cafile=CA if os.path.exists(CA) else None)
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx), urllib.request.ProxyHandler())


def existing():
    out = set()
    if DNC.exists():
        for r in csv.reader(open(DNC, newline="", encoding="utf-8")):
            if r and "@" in r[0]:
                out.add(r[0].strip().lower())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-key", default=os.environ.get("BREVO_API_KEY", ""))
    ap.add_argument("--days", type=int, default=30)
    a = ap.parse_args()
    if not a.api_key:
        raise SystemExit("ERROR: set BREVO_API_KEY.")

    op = _opener()
    have = existing()
    found = set()
    for ev in EVENTS:
        q = urllib.parse.urlencode({"event": ev, "days": a.days, "limit": 500})
        url = f"https://api.brevo.com/v3/smtp/statistics/events?{q}"
        req = urllib.request.Request(url, headers={"api-key": a.api_key, "accept": "application/json"})
        try:
            with op.open(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8", "ignore"))
            for e in data.get("events", []):
                em = (e.get("email") or "").strip().lower()
                if em and em not in have:
                    found.add(em)
        except Exception as exc:  # noqa: BLE001
            print(f"  ({ev}: {exc})")

    if found:
        write_header = not DNC.exists()
        with open(DNC, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if write_header:
                w.writerow(["email"])
            for em in sorted(found):
                w.writerow([em])
                print(f"SUPPRESS {em}")
    print(f"\nAdded {len(found)} bounced/blocked address(es) to do_not_contact.csv.")


if __name__ == "__main__":
    main()
