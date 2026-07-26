#!/usr/bin/env python3
"""
build_site.py — Job 6 website builder.

Generates a complete, modern, mobile-first 5-page website (Home, Services, About,
Gallery, Contact) for a closed client, writes it to a folder named after the
business, runs a self quality-check, and is ready to deploy to Netlify.

Copy is written from the business name, trade and London area throughout so the
site has a real chance of ranking for local searches from day one. The contact
page uses a Netlify Forms-enabled form (works automatically once deployed to
Netlify — no backend needed).

Usage:
    python3 build_site.py client.json
    # then: cd "<Business Name>" && netlify deploy --prod

client.json shape:
{
  "business_name": "Smith & Sons Plumbing",
  "trade": "Plumber",
  "area": "Hackney",
  "phone": "020 1234 5678",
  "email": "info@example.co.uk",
  "services": ["Emergency plumbing", "Boiler repair", "Bathroom installation"],
  "has_logo": false,
  "accent": "#1a6fb5"
}
"""
import html
import json
import re
import sys
from pathlib import Path

PAGES = ["index", "services", "about", "gallery", "contact"]
NAV = [("index", "Home"), ("services", "Services"), ("about", "About"),
       ("gallery", "Gallery"), ("contact", "Contact")]


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def css(accent):
    return f""":root{{--accent:{accent};--dark:#12212e;--muted:#5a6b78;--bg:#f7f9fb;}}
*{{margin:0;padding:0;box-sizing:border-box;}}
html{{scroll-behavior:smooth;}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
color:var(--dark);line-height:1.6;background:#fff;}}
a{{color:var(--accent);text-decoration:none;}}
.container{{max-width:1080px;margin:0 auto;padding:0 20px;}}
header{{position:sticky;top:0;z-index:50;background:#fff;box-shadow:0 1px 8px rgba(0,0,0,.06);}}
.bar{{display:flex;align-items:center;justify-content:space-between;padding:14px 20px;max-width:1080px;margin:0 auto;}}
.logo{{font-weight:800;font-size:1.25rem;color:var(--dark);}}
.logo span{{color:var(--accent);}}
nav ul{{list-style:none;display:flex;gap:22px;align-items:center;}}
nav a{{color:var(--dark);font-weight:600;font-size:.95rem;}}
nav a:hover{{color:var(--accent);}}
.call-btn{{background:var(--accent);color:#fff!important;padding:10px 18px;border-radius:8px;font-weight:700;}}
.menu-toggle{{display:none;background:none;border:0;font-size:1.6rem;cursor:pointer;color:var(--dark);}}
.hero{{background:linear-gradient(135deg,var(--dark),var(--accent));color:#fff;padding:88px 20px;text-align:center;}}
.hero h1{{font-size:2.6rem;line-height:1.15;margin-bottom:16px;}}
.hero p{{font-size:1.2rem;max-width:640px;margin:0 auto 28px;opacity:.95;}}
.btn{{display:inline-block;background:#fff;color:var(--accent);padding:14px 30px;border-radius:8px;font-weight:700;font-size:1.05rem;}}
.btn.alt{{background:var(--accent);color:#fff;border:2px solid #fff;}}
section{{padding:64px 0;}}
section:nth-child(even){{background:var(--bg);}}
h2{{font-size:2rem;text-align:center;margin-bottom:12px;}}
.lead{{text-align:center;color:var(--muted);max-width:640px;margin:0 auto 40px;}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:24px;}}
.card{{background:#fff;border:1px solid #e6ecf1;border-radius:12px;padding:28px;box-shadow:0 2px 12px rgba(0,0,0,.04);}}
.card h3{{color:var(--accent);margin-bottom:8px;}}
.gallery-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:16px;}}
.gallery-grid div{{aspect-ratio:4/3;border-radius:10px;background:linear-gradient(135deg,#cfd9e1,#eef2f5);
display:flex;align-items:center;justify-content:center;color:var(--muted);font-weight:600;text-align:center;padding:12px;}}
form{{max-width:560px;margin:0 auto;display:grid;gap:16px;}}
label{{font-weight:600;font-size:.95rem;}}
input,textarea{{width:100%;padding:12px;border:1px solid #cdd7df;border-radius:8px;font-size:1rem;font-family:inherit;}}
button[type=submit]{{background:var(--accent);color:#fff;border:0;padding:14px;border-radius:8px;font-weight:700;font-size:1.05rem;cursor:pointer;}}
.contact-info{{text-align:center;margin-bottom:32px;font-size:1.1rem;}}
.contact-info a{{font-weight:700;}}
footer{{background:var(--dark);color:#cdd7df;text-align:center;padding:32px 20px;font-size:.9rem;}}
footer a{{color:#fff;}}
.float-call{{position:fixed;bottom:18px;right:18px;background:var(--accent);color:#fff;padding:14px 20px;
border-radius:50px;font-weight:700;box-shadow:0 4px 16px rgba(0,0,0,.25);z-index:60;}}
@media(max-width:760px){{
nav ul{{display:none;position:absolute;top:100%;left:0;right:0;background:#fff;flex-direction:column;
gap:0;padding:8px 0;box-shadow:0 6px 12px rgba(0,0,0,.08);}}
nav ul.open{{display:flex;}}
nav li{{width:100%;text-align:center;padding:10px 0;}}
.menu-toggle{{display:block;}}
.hero h1{{font-size:1.9rem;}}
.hero p{{font-size:1.05rem;}}
}}"""


def header(cfg, active):
    name = html.escape(cfg["business_name"])
    tel = re.sub(r"[^0-9+]", "", cfg["phone"])
    links = ""
    for page, lbl in NAV:
        href = f"{page}.html"
        cur = ' aria-current="page"' if page == active else ""
        links += f'<li><a href="{href}"{cur}>{html.escape(lbl)}</a></li>'
    return f"""<header>
<div class="bar">
<a class="logo" href="index.html">{name}</a>
<button class="menu-toggle" aria-label="Menu" onclick="document.getElementById('nav').classList.toggle('open')">&#9776;</button>
<nav><ul id="nav">{links}<li><a class="call-btn" href="tel:{tel}">Call {html.escape(cfg['phone'])}</a></li></ul></nav>
</div>
</header>"""


def footer(cfg):
    name = html.escape(cfg["business_name"])
    area = html.escape(cfg["area"])
    trade = html.escape(cfg["trade"].lower())
    tel = re.sub(r"[^0-9+]", "", cfg["phone"])
    return f"""<a class="float-call" href="tel:{tel}">&#128222; Call now</a>
<footer>
<p><strong>{name}</strong> — trusted {trade} serving {area} and surrounding areas.</p>
<p>Call <a href="tel:{tel}">{html.escape(cfg['phone'])}</a>{" · " + html.escape(cfg['email']) if cfg.get('email') else ""}</p>
<p style="margin-top:10px;opacity:.7;">&copy; 2026 {name}. All rights reserved.</p>
</footer>"""


def shell(cfg, active, title, body):
    desc = f"{cfg['trade']} in {cfg['area']}, London. {cfg['business_name']} — call {cfg['phone']}."
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc)}">
<link rel="stylesheet" href="style.css">
</head>
<body>
{header(cfg, active)}
{body}
{footer(cfg)}
</body>
</html>"""


def page_index(cfg):
    name, trade, area = cfg["business_name"], cfg["trade"], cfg["area"]
    tl = trade.lower()
    tel = re.sub(r"[^0-9+]", "", cfg["phone"])
    cards = "".join(
        f'<div class="card"><h3>{html.escape(s)}</h3><p>Professional {html.escape(s.lower())} '
        f'for homes and businesses across {html.escape(area)}.</p></div>'
        for s in cfg["services"][:6])
    body = f"""<section class="hero">
<h1>{html.escape(area)}'s Trusted {html.escape(trade)}</h1>
<p>{html.escape(name)} provides reliable, professional {html.escape(tl)} services across {html.escape(area)} and nearby areas — fast response, fair prices, quality work.</p>
<a class="btn" href="tel:{tel}">Call {html.escape(cfg['phone'])}</a>
<a class="btn alt" href="contact.html">Get a Free Quote</a>
</section>
<section>
<div class="container">
<h2>Why {html.escape(area)} Chooses Us</h2>
<p class="lead">Local, reliable and fully experienced — the {html.escape(tl)} {html.escape(area)} residents recommend.</p>
<div class="grid">
<div class="card"><h3>Local & Reliable</h3><p>Based near {html.escape(area)}, we turn up on time and do the job properly, first time.</p></div>
<div class="card"><h3>Fair, Upfront Pricing</h3><p>Clear quotes with no hidden extras — you know the price before we start.</p></div>
<div class="card"><h3>Fully Qualified</h3><p>Experienced, insured and trusted by homeowners and businesses throughout {html.escape(area)}.</p></div>
</div>
</div>
</section>
<section>
<div class="container">
<h2>Our {html.escape(trade)} Services</h2>
<p class="lead">Whatever you need in {html.escape(area)}, we can help.</p>
<div class="grid">{cards}</div>
</div>
</section>"""
    return shell(cfg, "index", f"{trade} in {area} | {name}", body)


def page_services(cfg):
    name, trade, area = cfg["business_name"], cfg["trade"], cfg["area"]
    cards = "".join(
        f'<div class="card"><h3>{html.escape(s)}</h3><p>{html.escape(name)} delivers expert '
        f'{html.escape(s.lower())} throughout {html.escape(area)} — reliable work, tidy finish, fair price.</p></div>'
        for s in cfg["services"])
    body = f"""<section class="hero" style="padding:60px 20px;">
<h1>Our Services</h1>
<p>Full {html.escape(trade.lower())} services across {html.escape(area)} and the surrounding area.</p>
</section>
<section>
<div class="container">
<div class="grid">{cards}</div>
</div>
</section>"""
    return shell(cfg, "services", f"Services | {name} — {trade} in {area}", body)


def page_about(cfg):
    name, trade, area = cfg["business_name"], cfg["trade"], cfg["area"]
    tl = trade.lower()
    body = f"""<section class="hero" style="padding:60px 20px;">
<h1>About {html.escape(name)}</h1>
<p>Your local {html.escape(tl)} in {html.escape(area)}.</p>
</section>
<section>
<div class="container" style="max-width:760px;">
<p style="font-size:1.1rem;margin-bottom:18px;">{html.escape(name)} is a local {html.escape(tl)} business serving {html.escape(area)} and the surrounding London areas. We've built our reputation on honest advice, reliable workmanship and treating every customer's home as if it were our own.</p>
<p style="font-size:1.1rem;margin-bottom:18px;">From small repairs to larger installations, we take on every job with the same care and attention. Because we're local to {html.escape(area)}, we can respond quickly — and because so much of our work comes from word of mouth, doing right by our customers matters more to us than anything.</p>
<p style="font-size:1.1rem;">Give us a call today and find out why {html.escape(area)} homeowners trust {html.escape(name)}.</p>
<p style="text-align:center;margin-top:32px;"><a class="btn alt" href="contact.html">Get in Touch</a></p>
</div>
</section>"""
    return shell(cfg, "about", f"About | {name} — {trade} in {area}", body)


def page_gallery(cfg):
    name, area = cfg["business_name"], cfg["area"]
    tiles = "".join(
        f'<div>Recent work in {html.escape(area)} — photo {i}</div>' for i in range(1, 9))
    body = f"""<section class="hero" style="padding:60px 20px;">
<h1>Our Work</h1>
<p>A look at recent {html.escape(cfg['trade'].lower())} jobs around {html.escape(area)}.</p>
</section>
<section>
<div class="container">
<p class="lead">Replace these placeholders with real photos of your completed jobs — they're the single biggest trust-builder on the site.</p>
<div class="gallery-grid">{tiles}</div>
</div>
</section>"""
    return shell(cfg, "gallery", f"Gallery | {name} — {area}", body)


def page_contact(cfg):
    name, trade, area = cfg["business_name"], cfg["trade"], cfg["area"]
    tel = re.sub(r"[^0-9+]", "", cfg["phone"])
    email_line = (f' · <a href="mailto:{html.escape(cfg["email"])}">{html.escape(cfg["email"])}</a>'
                  if cfg.get("email") else "")
    body = f"""<section class="hero" style="padding:60px 20px;">
<h1>Contact {html.escape(name)}</h1>
<p>Get a free, no-obligation quote for your {html.escape(trade.lower())} job in {html.escape(area)}.</p>
</section>
<section>
<div class="container">
<div class="contact-info">
Call us on <a href="tel:{tel}">{html.escape(cfg['phone'])}</a>{email_line}
</div>
<form name="contact" method="POST" data-netlify="true" netlify-honeypot="bot-field">
<input type="hidden" name="form-name" value="contact">
<p style="display:none;"><label>Don't fill this in: <input name="bot-field"></label></p>
<div><label for="name">Your name</label><input id="name" name="name" required></div>
<div><label for="phone">Phone number</label><input id="phone" name="phone" required></div>
<div><label for="email">Email</label><input id="email" type="email" name="email"></div>
<div><label for="message">How can we help?</label><textarea id="message" name="message" rows="5" required></textarea></div>
<button type="submit">Send Enquiry</button>
</form>
</div>
</section>"""
    return shell(cfg, "contact", f"Contact | {name} — {trade} in {area}", body)


BUILDERS = {"index": page_index, "services": page_services, "about": page_about,
            "gallery": page_gallery, "contact": page_contact}


def quality_check(outdir, cfg):
    issues = []
    for page in PAGES:
        fp = outdir / f"{page}.html"
        if not fp.exists():
            issues.append(f"missing {page}.html")
            continue
        text = fp.read_text(encoding="utf-8")
        if "viewport" not in text:
            issues.append(f"{page}.html missing mobile viewport")
        if cfg["area"] not in text:
            issues.append(f"{page}.html missing area '{cfg['area']}' (local SEO)")
        for other in PAGES:
            if f'{other}.html' not in text:
                issues.append(f"{page}.html missing nav link to {other}.html")
                break
    if not (outdir / "style.css").exists():
        issues.append("missing style.css")
    return issues


def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: python3 build_site.py client.json")
    cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    cfg.setdefault("accent", "#1a6fb5")
    cfg.setdefault("email", "")
    cfg.setdefault("services", ["General repairs", "Installations", "Maintenance", "Emergency call-outs"])

    outdir = Path(cfg["business_name"])
    outdir.mkdir(exist_ok=True)
    (outdir / "style.css").write_text(css(cfg["accent"]), encoding="utf-8")
    for page, builder in BUILDERS.items():
        (outdir / f"{page}.html").write_text(builder(cfg), encoding="utf-8")
    # Netlify config so forms + deploy work out of the box
    (outdir / "netlify.toml").write_text('[build]\n  publish = "."\n', encoding="utf-8")

    issues = quality_check(outdir, cfg)
    print(f"Built 5-page site -> {outdir}/")
    if issues:
        print("QUALITY CHECK found issues:")
        for i in issues:
            print(f"  ✗ {i}")
        sys.exit(1)
    print("QUALITY CHECK passed: all pages present, mobile viewport set, local SEO copy in place, nav links resolve.")
    print(f"\nDeploy:  cd \"{outdir}\" && netlify deploy --prod")


if __name__ == "__main__":
    main()
