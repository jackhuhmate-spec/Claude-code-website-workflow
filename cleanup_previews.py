#!/usr/bin/env python3
"""
cleanup_previews.py — delete old Netlify PREVIEW sites (name starts with 'preview-')
older than N days. NEVER touches paid client sites (deployed with --final, no prefix).

Usage:
    NETLIFY_TOKEN=nfp_... python3 cleanup_previews.py [--days 14] [--apply]
    (dry-run by default; add --apply to actually delete)
"""
import argparse
import json
import os
import ssl
import urllib.request
from datetime import datetime, timezone

API = "https://api.netlify.com/api/v1"
CA = os.environ.get("SSL_CERT_FILE") or "/root/.ccr/ca-bundle.crt"


def _opener():
    ctx = ssl.create_default_context(cafile=CA if os.path.exists(CA) else None)
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                       urllib.request.ProxyHandler())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--token", default=os.environ.get("NETLIFY_TOKEN", ""))
    a = ap.parse_args()
    if not a.token:
        raise SystemExit("ERROR: set NETLIFY_TOKEN.")
    op = _opener()
    hdr = {"Authorization": f"Bearer {a.token}"}

    sites = []
    page = 1
    while True:
        req = urllib.request.Request(f"{API}/sites?per_page=100&page={page}", headers=hdr)
        batch = json.loads(op.open(req, timeout=30).read().decode())
        if not batch:
            break
        sites.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    now = datetime.now(timezone.utc)
    old_previews = []
    for s in sites:
        name = s.get("name", "")
        if not name.startswith("preview-"):
            continue  # SAFETY: only preview sites, never client sites
        try:
            created = datetime.fromisoformat(s["created_at"].replace("Z", "+00:00"))
        except Exception:
            continue
        if (now - created).days >= a.days:
            old_previews.append(s)

    print(f"{len(sites)} sites total; {len(old_previews)} preview sites older than {a.days} days.")
    for s in old_previews:
        if a.apply:
            try:
                req = urllib.request.Request(f"{API}/sites/{s['id']}", headers=hdr, method="DELETE")
                op.open(req, timeout=30)
                print(f"DELETED {s['name']}")
            except Exception as e:  # noqa: BLE001
                print(f"FAILED  {s['name']}: {e}")
        else:
            print(f"would delete {s['name']} (created {s.get('created_at','')[:10]})")
    if not a.apply and old_previews:
        print("\n(dry-run — add --apply to delete)")


if __name__ == "__main__":
    main()
