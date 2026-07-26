#!/usr/bin/env python3
"""
reply_bridge.py — read inbound replies and send responses via the Gmail Apps Script
bridge (HTTPS). Works where IMAP/SMTP are blocked.

Config (env vars):
    BRIDGE_URL     the Apps Script /exec web-app URL
    BRIDGE_SECRET  the shared secret token

Commands:
    read [--days 4] [--all] [--new]
        Print JSON of inbound emails. Default: only senders we emailed (sent_log.csv).
        --all    every inbound message.
        --new    exclude messages already recorded in handled_messages.txt
                 (so an hourly poll never replies to the same message twice).

    mark --id <messageId> [--id <messageId> ...]
        Record message id(s) as handled so --new skips them next run.

    send --to addr --subject "..." --body "..." [--thread ID]
        Send a reply from the user's real Gmail (threaded when --thread given).
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
HANDLED = HERE / "handled_messages.txt"
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


def load_handled():
    if not HANDLED.exists():
        return set()
    return {ln.strip() for ln in HANDLED.read_text(encoding="utf-8").splitlines() if ln.strip()}


def mark_handled(ids):
    with open(HANDLED, "a", encoding="utf-8") as f:
        for mid in ids:
            if mid:
                f.write(mid + "\n")


def read(days, show_all, only_new):
    if not URL or not SECRET:
        sys.exit("ERROR: set BRIDGE_URL and BRIDGE_SECRET.")
    u = f"{URL}?token={urllib.parse.quote(SECRET)}&days={days}"
    with _opener().open(u, timeout=45) as r:
        data = json.loads(r.read().decode("utf-8", "ignore"))
    if "error" in data:
        sys.exit(f"BRIDGE ERROR: {data['error']}")
    msgs = data.get("messages", [])
    known = sent_emails()
    handled = load_handled() if only_new else set()
    rows = []
    for m in msgs:
        frm = _addr(m.get("from", ""))
        if not show_all and frm not in known:
            continue
        if only_new and m.get("messageId") in handled:
            continue
        m["from_email"] = frm
        m["matched_business"] = known.get(frm, "")
        rows.append(m)
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    label = "all inbound" if show_all else "from businesses we emailed"
    if only_new:
        label += ", new only"
    print(f"\n# {len(rows)} message(s) ({label}).", file=sys.stderr)


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
    rd.add_argument("--new", action="store_true")
    mk = sub.add_parser("mark")
    mk.add_argument("--id", action="append", default=[], required=True)
    sd = sub.add_parser("send")
    sd.add_argument("--to", required=True)
    sd.add_argument("--subject", default="Re:")
    sd.add_argument("--body", required=True)
    sd.add_argument("--thread", default="")
    a = ap.parse_args()
    if a.cmd == "read":
        read(a.days, a.all, a.new)
    elif a.cmd == "mark":
        mark_handled(a.id)
        print(f"marked {len(a.id)} message(s) handled")
    else:
        send(a.to, a.subject, a.body, a.thread)


if __name__ == "__main__":
    main()
