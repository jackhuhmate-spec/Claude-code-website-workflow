#!/usr/bin/env python3
"""
deploy_preview.py — build a real 5-page site for a lead and deploy it live to Netlify,
returning the public URL. Used to send prospects an instant preview of their new site.

Config: NETLIFY_TOKEN env var (or --token). Never commit the token.

Usage:
    # from a lead already in leads.csv:
    NETLIFY_TOKEN=nfp_... python3 deploy_preview.py --business "KFM Roofing"

    # or fully manual:
    NETLIFY_TOKEN=nfp_... python3 deploy_preview.py --name "KFM Roofing" \
        --trade Roofer --area Stratford --phone "07708 570709" --email info@kfmroofing.co.uk
"""
import argparse, csv, io, json, os, re, shutil, ssl, sys, tempfile, time
import urllib.error, urllib.request, zipfile
from pathlib import Path

import build_site  # reuse the site generator

API = "https://api.netlify.com/api/v1"
CA = os.environ.get("SSL_CERT_FILE") or "/root/.ccr/ca-bundle.crt"
HERE = Path(__file__).resolve().parent


def _opener():
    ctx = ssl.create_default_context(cafile=CA if os.path.exists(CA) else None)
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                       urllib.request.ProxyHandler())


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:30] or "site"


def default_services(trade):
    t = (trade or "").lower()
    table = {
        "roofer": ["Roof repairs", "New roofs & re-roofing", "Flat roofs", "Guttering", "Chimney work", "Emergency call-outs"],
        "plumber": ["Emergency plumbing", "Boiler repair & servicing", "Bathroom installation", "Leak detection", "Blocked drains", "Radiators & heating"],
        "electrician": ["Rewiring", "Fuse board upgrades", "EICR & safety checks", "Lighting", "Sockets & fault-finding", "Emergency call-outs"],
    }
    return table.get(t, ["Free quotes", "Expert workmanship", "Reliable local service", "Emergency call-outs"])


def _call(op, req, timeout=60, tries=4):
    """Open a Netlify API request with retry/backoff on 429/5xx; always closes the response."""
    for i in range(tries):
        try:
            with op.open(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "ignore") or "{}")
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(2 ** i)
                continue
            raise


def build_zip(cfg):
    tmp = Path(tempfile.mkdtemp(prefix="swiftsite_preview_"))  # unique per call, outside the repo
    try:
        (tmp / "style.css").write_text(build_site.css(cfg.get("accent", "#1a6fb5")), encoding="utf-8")
        for page, builder in build_site.BUILDERS.items():
            (tmp / f"{page}.html").write_text(builder(cfg), encoding="utf-8")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for f in tmp.iterdir():
                z.write(f, f.name)
        return buf.getvalue()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def deploy(cfg, token, final=False):
    op = _opener()
    # Previews are prefixed 'preview-' so cleanup_previews.py can retire them safely.
    # Final (paid client) sites get a clean name and are never auto-deleted.
    prefix = "" if final else "preview-"
    name = f"{prefix}{slug(cfg['business_name'])}-{os.urandom(3).hex()}"
    # 1. create the site
    req = urllib.request.Request(f"{API}/sites", data=json.dumps({"name": name}).encode(),
                                 method="POST", headers={"Authorization": f"Bearer {token}",
                                 "Content-Type": "application/json"})
    site = _call(op, req, timeout=60)
    site_id, url = site["id"], site.get("ssl_url") or site.get("url")
    # 2. deploy the zip
    zip_bytes = build_zip(cfg)
    req = urllib.request.Request(f"{API}/sites/{site_id}/deploys", data=zip_bytes, method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/zip"})
    dep = _call(op, req, timeout=120)
    # 3. poll until ready
    for _ in range(30):
        req = urllib.request.Request(f"{API}/deploys/{dep['id']}",
                                     headers={"Authorization": f"Bearer {token}"})
        dep = _call(op, req, timeout=30)
        if dep.get("state") in ("ready", "error"):
            break
        time.sleep(2)
    return url, dep.get("state")


def lead_cfg(business):
    with open(HERE / "leads.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["Business Name"].lower() == business.lower():
                return {"business_name": r["Business Name"], "trade": r["Trade"],
                        "area": r["London Area"], "phone": r["Phone"],
                        "email": r.get("Email", ""), "services": default_services(r["Trade"]),
                        "accent": "#1a6fb5"}
    sys.exit(f"Lead not found: {business}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--business", help="Build from a lead in leads.csv by name")
    ap.add_argument("--name"); ap.add_argument("--trade"); ap.add_argument("--area")
    ap.add_argument("--phone", default=""); ap.add_argument("--email", default="")
    ap.add_argument("--services", default="")
    ap.add_argument("--token", default=os.environ.get("NETLIFY_TOKEN", ""))
    ap.add_argument("--final", action="store_true", help="Paid client site: clean name, never auto-cleaned.")
    a = ap.parse_args()
    if not a.token:
        sys.exit("ERROR: set NETLIFY_TOKEN (or --token).")

    if a.business:
        cfg = lead_cfg(a.business)
    else:
        if not (a.name and a.trade and a.area):
            sys.exit("ERROR: need --business, or --name/--trade/--area.")
        cfg = {"business_name": a.name, "trade": a.trade, "area": a.area, "phone": a.phone,
               "email": a.email, "accent": "#1a6fb5",
               "services": [s.strip() for s in a.services.split(",") if s.strip()] or default_services(a.trade)}

    url, state = deploy(cfg, a.token, a.final)
    print(f"{'SITE' if a.final else 'PREVIEW'} LIVE: {url}  (deploy state: {state})")
    print(url)


if __name__ == "__main__":
    main()
