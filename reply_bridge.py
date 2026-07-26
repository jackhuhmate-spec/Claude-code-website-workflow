#!/usr/bin/env python3
"""
reply_bridge.py — read inbound replies and send responses via the Gmail Apps Script
bridge (HTTPS), for the autonomous reply routine. Works where IMAP/SMTP are blocked.

Config (env vars, set by the reply routine — never hard-coded/committed):
    BRIDGE_URL     the Apps Script /exec web-app URL
    BRIDGE_SECRET  the shared secret token

Usage:
    python3 reply_bridge.py read [--days 4] [--all]
        Prints JSON of inbound emails. By default only those whose sender matches an
        address we actually emailed (sent_log.csv). --all shows every inbound message.

    python3 reply_bridge.py send --to addr --subject "..." --body "..." [--thread ID]
        Sends a reply from the user's real Gmail (in-thread if --thread given).
"""
import argparse
import csv
import json
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SENT_LOG = HERE / "sent_log.csv"
CA = os.environ.get("SSL_CERT_FILE") or "/root/.ccr/ca-bundle.crt"
URL = os.environ.get("BRIDGE_URL", "")
SECRET = os.environ.get("BRIDGE_SECRET", "")


def _opener():
    ctx = ssl.create_default_context(cafile=CA if os.path.exists(CA) else None)
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ctx), urllib.request.ProxyHandler())


def _addr(s):
    m = re.search(r"[\w.+-]+@[\w.-]+", s or "")
    return m.group(0).lower() if m else ""


def sent_emails():
    if not SENT_LOG.exists():
        return {}
    out = {}
    with open(SENT_LOG, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            e = (r.get("Email") or "").lower().strip()
            if e:
                out[e] = r.get("Business Name", "")
    return out


def read(days, show_all):
    if not URL or not SECRET:
        sys.exit("ERROR: set BRIDGE_URL and BRIDGE_SECRET.")
    u = f"{URL}?token={urllib.parse.quote(SECRET)}&days={days}"
    with _opener().open(u, timeout=45) as r:
        data = json.loads(r.read().decode("utf-8", "ignore"))
    if "error" in data:
        sys.exit(f"BRIDGE ERROR: {data['error']}")
    msgs = data.get("messages", [])
    known = sent_emails()
    rows = []
    for m in msgs:
        frm = _addr(m.get("from", ""))
        if not show_all and frm not in known:
            continue
        m["from_email"] = frm
        m["matched_business"] = known.get(frm, "")
        rows.append(m)
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    print(f"\n# {len(rows)} relevant inbound message(s)"
          f"{' (all inbound shown)' if show_all else ' from businesses we emailed'}.",
          file=sys.stderr)


def send(to, subject, body, thread):
    if not URL or not SECRET:
        sys.exit("ERROR: set BRIDGE_URL and BRIDGE_SECRET.")
    payload = {"token": SECRET, "to": to, "subject": subject, "body": body}
    if thread:
        payload["threadId"] = thread
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
                                 method="POST", headers={"content-type": "application/json"})
    with _opener().open(req, timeout=45) as r:
        print(r.read().decode("utf-8", "ignore"))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    rd = sub.add_parser("read")
    rd.add_argument("--days", type=int, default=4)
    rd.add_argument("--all", action="store_true")
    sd = sub.add_parser("send")
    sd.add_argument("--to", required=True)
    sd.add_argument("--subject", default="Re:")
    sd.add_argument("--body", required=True)
    sd.add_argument("--thread", default="")
    a = ap.parse_args()
    if a.cmd == "read":
        read(a.days, a.all)
    else:
        send(a.to, a.subject, a.body, a.thread)


if __name__ == "__main__":
    main()
