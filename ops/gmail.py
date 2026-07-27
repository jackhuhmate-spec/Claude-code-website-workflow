#!/usr/bin/env python3
"""
gmail.py — Gmail send/read over SMTP+IMAP with an app password.

Replaces the Brevo API + Apps Script bridge. Pure stdlib.

Credentials (env, never committed):
    GMAIL_USER            jackhuhmate@gmail.com
    GMAIL_APP_PASSWORD    16-char app password
    SIGN_NAME             Jake

Commands:
    python3 ops/gmail.py send --to X --subject S --body B [--thread <Message-ID>] [--force]
    python3 ops/gmail.py read [--new] [--days 4] [--all]
    python3 ops/gmail.py mark --id <message-id>
    python3 ops/gmail.py test
"""
import argparse, csv, email, imaplib, json, os, re, smtplib, ssl, sys
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import make_msgid, parseaddr
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
SENT_LOG = HERE / "sent_log.csv"
HANDLED = HERE / "handled_messages.txt"
DNC = HERE / "do_not_contact.csv"

USER = os.environ.get("GMAIL_USER", "")
PW = (os.environ.get("GMAIL_APP_PASSWORD", "") or "").replace(" ", "")
SIGN = os.environ.get("SIGN_NAME", "Jake")

SIGNOFF = "\n\nBest,\n{name}\n\n(If you'd rather not hear from me, just reply \"no thanks\" and I won't email again.)"


def _need_creds():
    if not USER or not PW:
        sys.exit("ERROR: set GMAIL_USER and GMAIL_APP_PASSWORD.")


def known_recipients():
    """Addresses we have already cold-emailed — the reply guard."""
    out = set()
    if SENT_LOG.exists():
        with SENT_LOG.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                a = (row.get("Email") or "").strip().lower()
                if a and "@" in a:
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


def recently_replied(days=45):
    """Addresses we have already replied to from Sent Mail — prevents double-replies
    even if the reply was sent by hand, by Claude Code, or on another machine."""
    out = {}
    try:
        M = imaplib.IMAP4_SSL("imap.gmail.com", 993, ssl_context=ssl.create_default_context())
        M.login(USER, PW)
        for box in ('"[Gmail]/Sent Mail"', '"[Google Mail]/Sent Mail"', "Sent"):
            try:
                typ, _ = M.select(box, readonly=True)
                if typ != "OK":
                    continue
            except Exception:
                continue
            since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%d-%b-%Y")
            typ, data = M.search(None, f'(SINCE "{since}")')
            if typ != "OK":
                continue
            ids = data[0].split()[-500:]
            if not ids:
                break
            # One batched FETCH instead of one round-trip per message.
            typ, d = M.fetch(b",".join(ids).decode(), "(BODY.PEEK[HEADER.FIELDS (TO DATE)])")
            if typ == "OK":
                for part in d:
                    if not isinstance(part, tuple) or len(part) < 2:
                        continue
                    hdr = email.message_from_bytes(part[1])
                    addr = parseaddr(hdr.get("To", ""))[1].lower()
                    if addr:
                        out[addr] = hdr.get("Date", "")
            break
        M.logout()
    except Exception as e:
        print(f"WARN: sent-mail check failed ({type(e).__name__}) — falling back to handled_messages.txt only", file=sys.stderr)
    return out


def handled_ids():
    if HANDLED.exists():
        return {l.strip() for l in HANDLED.read_text(encoding="utf-8").splitlines() if l.strip()}
    return set()


def cmd_send(a):
    _need_creds()
    to = a.to.strip().lower()
    if to in opted_out():
        sys.exit(f"BLOCKED: {to} is on do_not_contact.csv.")
    if not a.force and to not in known_recipients():
        sys.exit(f"BLOCKED: {to} is not in sent_log.csv (reply guard). Use --force only for a deliberately verified new recipient.")

    msg = EmailMessage()
    msg["From"] = f"{SIGN} <{USER}>"
    msg["To"] = a.to
    msg["Subject"] = a.subject
    msg["Message-ID"] = make_msgid(domain="gmail.com")
    if a.thread:
        msg["In-Reply-To"] = a.thread
        msg["References"] = a.thread
    body = a.body
    if not a.no_signoff:
        body += SIGNOFF.format(name=SIGN)
    msg.set_content(body)

    ctx = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as s:
        s.starttls(context=ctx)
        s.login(USER, PW)
        s.send_message(msg)
    print(json.dumps({"ok": True, "to": a.to, "subject": a.subject, "message_id": msg["Message-ID"]}))


def _decode(v):
    try:
        return str(make_header(decode_header(v or "")))
    except Exception:
        return v or ""


NOISE_PAT = re.compile(
    r"(no-?reply|do-?not-?reply|notifications?@|@notifications\.|mailer-daemon|postmaster|"
    r"@accounts\.google|@mail\.anthropic|@t\.brevo|@email\.neon|@render\.com|@mtasv\.net|"
    r"@github\.com|@netlify\.com|@sendgrid|@customer\.io|newsletter|@e\.|@em\.|@mail\.)",
    re.I)


def _strip_html(h):
    h = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</tr>", "\n", h)
    h = re.sub(r"(?s)<!--.*?-->", " ", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    import html as _h
    h = _h.unescape(h)
    h = re.sub(r"[\u200b-\u200f\ufeff\u00a0]", " ", h)
    h = re.sub(r"[ \t]+", " ", h)
    h = re.sub(r"\n\s*\n\s*\n+", "\n\n", h)
    return h.strip()


def _body_of(m):
    if m.is_multipart():
        for part in m.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                try:
                    return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                except Exception:
                    continue
        for part in m.walk():
            if part.get_content_type() == "text/html":
                try:
                    return _strip_html(part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", "replace"))
                except Exception:
                    continue
        return ""
    try:
        raw = m.get_payload(decode=True).decode(m.get_content_charset() or "utf-8", "replace")
    except Exception:
        raw = str(m.get_payload())
    return _strip_html(raw) if "<" in raw and ">" in raw else raw


def cmd_read(a):
    _need_creds()
    ctx = ssl.create_default_context()
    M = imaplib.IMAP4_SSL("imap.gmail.com", 993, ssl_context=ctx)
    M.login(USER, PW)
    M.select("INBOX")
    since = (datetime.now(timezone.utc) - timedelta(days=a.days)).strftime("%d-%b-%Y")
    crit = "ALL" if a.all else f'(SINCE "{since}")'
    typ, data = M.search(None, crit)
    ids = data[0].split()
    done = handled_ids()
    replied = {} if a.no_sent_check else recently_replied()
    out = []
    for i in reversed(ids[-200:]):
        typ, d = M.fetch(i, "(RFC822)")
        if typ != "OK" or not d or not d[0]:
            continue
        m = email.message_from_bytes(d[0][1])
        mid = (m.get("Message-ID") or "").strip()
        if a.new and mid in done:
            continue
        frm = parseaddr(m.get("From", ""))[1].lower()
        if frm == USER.lower():
            continue
        known = frm in known_recipients()
        already = frm in replied
        machine = bool(NOISE_PAT.search(frm))
        if machine and not known and not a.noise:
            continue
        out.append({
            "messageId": mid,
            "from": frm,
            "fromName": _decode(m.get("From", "")),
            "subject": _decode(m.get("Subject", "")),
            "date": m.get("Date", ""),
            "known": known,
            "machine": machine,
            "alreadyReplied": already,
            "lastReplyDate": replied.get(frm, ""),
            "body": _body_of(m).strip()[:4000],
        })
    M.logout()
    print(json.dumps(out, indent=1))


def cmd_mark(a):
    """Append-only + O_APPEND is atomic for small writes, so two concurrent runs
    can't clobber each other's handled IDs (a read-modify-write would)."""
    cur = handled_ids()
    new = [x.strip() for x in a.id if x.strip() and x.strip() not in cur]
    if new:
        with HANDLED.open("a", encoding="utf-8") as f:
            f.write("\n".join(new) + "\n")
    print(json.dumps({"ok": True, "added": len(new), "handled_total": len(cur) + len(new)}))


def cmd_test(a):
    _need_creds()
    ctx = ssl.create_default_context()
    ok = {}
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as s:
            s.starttls(context=ctx); s.login(USER, PW)
        ok["smtp"] = "OK"
    except Exception as e:
        ok["smtp"] = f"FAIL {type(e).__name__}: {e}"
    try:
        M = imaplib.IMAP4_SSL("imap.gmail.com", 993, ssl_context=ctx)
        M.login(USER, PW); M.select("INBOX"); M.logout()
        ok["imap"] = "OK"
    except Exception as e:
        ok["imap"] = f"FAIL {type(e).__name__}: {e}"
    ok["user"] = USER
    ok["known_recipients"] = len(known_recipients())
    ok["opted_out"] = len(opted_out())
    print(json.dumps(ok, indent=1))
    sys.exit(0 if ok["smtp"] == "OK" and ok["imap"] == "OK" else 1)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("send"); s.set_defaults(fn=cmd_send)
    s.add_argument("--to", required=True); s.add_argument("--subject", required=True)
    s.add_argument("--body", required=True); s.add_argument("--thread", default="")
    s.add_argument("--force", action="store_true"); s.add_argument("--no-signoff", action="store_true")

    r = sub.add_parser("read"); r.set_defaults(fn=cmd_read)
    r.add_argument("--days", type=int, default=4); r.add_argument("--all", action="store_true")
    r.add_argument("--new", action="store_true")
    r.add_argument("--noise", action="store_true", help="Include machine/notification mail.")
    r.add_argument("--no-sent-check", action="store_true", help="Skip the Sent Mail double-reply guard.")

    m = sub.add_parser("mark"); m.set_defaults(fn=cmd_mark)
    m.add_argument("--id", action="append", default=[], required=True)

    t = sub.add_parser("test"); t.set_defaults(fn=cmd_test)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
