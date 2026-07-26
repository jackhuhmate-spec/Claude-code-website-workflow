#!/usr/bin/env python3
"""
selftest.py — one-command health check for the whole machine.
Run: BREVO_API_KEY=.. BRIDGE_URL=.. BRIDGE_SECRET=.. NETLIFY_TOKEN=.. python3 selftest.py
Any env var you omit → that live check is skipped (marked SKIP), not failed.
Exit code 0 if nothing FAILED.
"""
import json
import os
import ssl
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CA = os.environ.get("SSL_CERT_FILE") or "/root/.ccr/ca-bundle.crt"
SCRIPTS = ["brevo_send.py", "followups.py", "suppress_bounces.py", "reply_bridge.py",
           "build_site.py", "deploy_preview.py", "stats.py"]
DATA = ["leads.csv", "emails.json", "sent_log.csv", "do_not_contact.csv", "run_history.csv"]
results = []


def ok(name, passed, detail=""):
    results.append((name, passed, detail))
    tag = {True: "PASS", False: "FAIL", None: "SKIP"}[passed]
    print(f"[{tag}] {name}" + (f" — {detail}" if detail else ""))


def opener():
    ctx = ssl.create_default_context(cafile=CA if os.path.exists(CA) else None)
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                       urllib.request.ProxyHandler())


# 1. scripts compile
r = subprocess.run([sys.executable, "-m", "py_compile", *[str(HERE / s) for s in SCRIPTS]],
                   capture_output=True, text=True)
ok("scripts compile", r.returncode == 0, r.stderr.strip()[:150] or f"{len(SCRIPTS)} scripts")

# 2. data files present
missing = [f for f in DATA if not (HERE / f).exists()]
ok("core data files", not missing, "missing: " + ", ".join(missing) if missing else "all present")

# 3. emails.json valid + every lead-with-email has a draft
try:
    import csv
    emails = json.loads((HERE / "emails.json").read_text())
    leads = list(csv.DictReader(open(HERE / "leads.csv", newline="", encoding="utf-8")))
    no_draft = [r["Business Name"] for r in leads
                if (r.get("Email") or "").strip() and r["Business Name"] not in emails]
    ok("every emailable lead has a draft", not no_draft,
       f"{len(no_draft)} missing" if no_draft else f"{len(leads)} leads OK")
except Exception as e:  # noqa: BLE001
    ok("emails.json / leads.csv parse", False, str(e)[:120])

# 4. bridge reachable
if os.environ.get("BRIDGE_URL") and os.environ.get("BRIDGE_SECRET"):
    try:
        import urllib.parse
        u = f"{os.environ['BRIDGE_URL']}?token={urllib.parse.quote(os.environ['BRIDGE_SECRET'])}&days=1"
        d = json.loads(opener().open(u, timeout=45).read().decode())
        ok("Gmail bridge", "messages" in d and "error" not in d, d.get("error", "reachable, auth OK"))
    except Exception as e:  # noqa: BLE001
        ok("Gmail bridge", False, str(e)[:120])
else:
    ok("Gmail bridge", None, "BRIDGE_URL/SECRET not set")

# 5. Brevo key valid
if os.environ.get("BREVO_API_KEY"):
    try:
        req = urllib.request.Request("https://api.brevo.com/v3/account",
                                     headers={"api-key": os.environ["BREVO_API_KEY"], "accept": "application/json"})
        d = json.loads(opener().open(req, timeout=30).read().decode())
        ok("Brevo API key", bool(d.get("email")), f"account {d.get('email','?')}")
    except Exception as e:  # noqa: BLE001
        ok("Brevo API key", False, str(e)[:120])
else:
    ok("Brevo API key", None, "BREVO_API_KEY not set")

# 6. Netlify token valid
if os.environ.get("NETLIFY_TOKEN"):
    try:
        req = urllib.request.Request("https://api.netlify.com/api/v1/user",
                                     headers={"Authorization": f"Bearer {os.environ['NETLIFY_TOKEN']}"})
        d = json.loads(opener().open(req, timeout=30).read().decode())
        ok("Netlify token", bool(d.get("id")), f"user {d.get('email', d.get('id','?'))}")
    except Exception as e:  # noqa: BLE001
        ok("Netlify token", False, str(e)[:120])
else:
    ok("Netlify token", None, "NETLIFY_TOKEN not set")

failed = [n for n, p, _ in results if p is False]
print("\n" + ("✅ ALL GOOD" if not failed else f"❌ {len(failed)} FAILED: " + ", ".join(failed)))
sys.exit(1 if failed else 0)
