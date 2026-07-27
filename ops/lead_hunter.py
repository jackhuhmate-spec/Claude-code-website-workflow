#!/usr/bin/env python3
"""
lead_hunter.py — automated lead sourcing (Agent 1).

Pulls London businesses from OpenStreetMap's Overpass API (free, no key, no signup),
then AUDITS every candidate site before keeping it. Never invents data.

    python3 ops/lead_hunter.py                  # dry run
    python3 ops/lead_hunter.py --write          # append to leads.csv
    python3 ops/lead_hunter.py --write --tile 3 # a different part of London

Two kinds of lead are kept:
  Group B — no website at all  (strongest pitch: they're invisible)
  Group A — has a site that fails the audit (dead, insecure, not mobile, stale)

Everything else is discarded. A lead with no email is still kept if it has a phone,
so the contact-form/phone list stays useful.
"""
import argparse, csv, json, re, ssl, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
LEADS = HERE / "leads.csv"
SENT = HERE / "sent_log.csv"
DNC = HERE / "do_not_contact.csv"

OVERPASS = ["https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter"]
UA = "leadbot/1.0 (small business web audit)"

# Greater London carved into tiles — Overpass times out on the whole city at once.
TILES = [
    ("Inner East",  "51.50,-0.10,51.58,0.02"),
    ("Inner South", "51.43,-0.15,51.51,0.00"),
    ("Inner West",  "51.47,-0.28,51.55,-0.10"),
    ("North",       "51.55,-0.25,51.65,0.02"),
    ("East",        "51.48,0.00,51.58,0.18"),
    ("South East",  "51.38,-0.10,51.48,0.12"),
    ("South West",  "51.35,-0.30,51.45,-0.08"),
    ("West",        "51.48,-0.45,51.58,-0.25"),
]

# OSM tag -> the trade label used in leads.csv
CRAFTS = {
    "plumber": "Plumber", "electrician": "Electrician", "roofer": "Roofer",
    "carpenter": "Carpenter", "joiner": "Carpenter", "painter": "Painter & Decorator",
    "plasterer": "Plasterer", "tiler": "Tiler", "gardener": "Landscaper",
    "handicraft": "Handyman", "builder": "Builder", "locksmith": "Locksmith",
    "hvac": "Heating Engineer", "upholsterer": "Upholsterer", "stonemason": "Stonemason", "glaziery": "Glazier",
    "scaffolder": "Scaffolder", "floorer": "Flooring Fitter",
}
SHOPS = {
    "hairdresser": "Hair Salon", "beauty": "Beauty Salon", "florist": "Florist",
    "car_repair": "Car Garage", "bakery": "Bakery", "butcher": "Butcher",
    "dry_cleaning": "Dry Cleaner", "laundry": "Launderette", "greengrocer": "Greengrocer",
    "pet_grooming": "Dog Groomer", "shoe_repair": "Shoe Repair", "tattoo": "Tattoo Studio",
    "optician": "Optician", "travel_agency": "Travel Agent",
}
# Outward postcode district -> a borough name a local would recognise.
POSTCODE_AREA = {
    "E1": "Whitechapel", "E2": "Bethnal Green", "E3": "Bow", "E4": "Chingford",
    "E5": "Clapton", "E6": "East Ham", "E7": "Forest Gate", "E8": "Hackney",
    "E9": "Homerton", "E10": "Leyton", "E11": "Leytonstone", "E12": "Manor Park",
    "E13": "Plaistow", "E14": "Poplar", "E15": "Stratford", "E16": "Canning Town",
    "E17": "Walthamstow", "E18": "South Woodford",
    "N1": "Islington", "N4": "Finsbury Park", "N7": "Holloway", "N8": "Crouch End",
    "N15": "Seven Sisters", "N16": "Stoke Newington", "N17": "Tottenham", "N22": "Wood Green",
    "SE1": "Southwark", "SE5": "Camberwell", "SE8": "Deptford", "SE13": "Lewisham",
    "SE14": "New Cross", "SE15": "Peckham", "SE22": "East Dulwich", "SE23": "Forest Hill",
    "SW2": "Brixton", "SW4": "Clapham", "SW9": "Stockwell", "SW11": "Battersea",
    "SW17": "Tooting", "SW18": "Wandsworth", "SW19": "Wimbledon",
    "W3": "Acton", "W5": "Ealing", "W6": "Hammersmith", "W10": "North Kensington",
    "W12": "Shepherds Bush", "NW1": "Camden", "NW5": "Kentish Town", "NW6": "Kilburn",
    "NW10": "Willesden", "CR0": "Croydon", "BR1": "Bromley", "IG1": "Ilford",
    "RM1": "Romford", "HA1": "Harrow", "UB1": "Southall", "TW3": "Hounslow",
}

# Chains and franchises we never contact.
CHAINS = re.compile(r"\b(tesco|sainsbury|asda|morrison|aldi|lidl|co-?op|greggs|costa|"
                    r"starbucks|pret|subway|mcdonald|kfc|burger king|domino|papa john|"
                    r"pizza hut|nando|wagamama|toni ?& ?guy|supercuts|specsavers|vision express|"
                    r"boots|superdrug|halfords|kwik ?fit|f1 autocentre|national tyres|"
                    r"timpson|max spielmann|ismash|o2|ee|vodafone|three|carphone)\b", re.I)


def _query(q, timeout=120):
    last = None
    for host in OVERPASS:
        try:
            r = urllib.request.urlopen(urllib.request.Request(
                host, data=urllib.parse.urlencode({"data": q}).encode(),
                headers={"User-Agent": UA, "Accept": "application/json"}), timeout=timeout)
            return json.loads(r.read()).get("elements", [])
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
            time.sleep(3)
    print(f"  Overpass unavailable ({last})", file=sys.stderr)
    return []


def overpass(bbox, timeout=120):
    """Two small queries beat one big one — Overpass 504s on long regexes."""
    out = []
    out += _query(f'[out:json][timeout:60];node["craft"]({bbox});out tags 400;', timeout)
    time.sleep(2)
    shops = "|".join(list(SHOPS)[:8])
    out += _query(f'[out:json][timeout:60];node["shop"~"^({shops})$"]({bbox});out tags 400;', timeout)
    time.sleep(2)
    shops2 = "|".join(list(SHOPS)[8:])
    if shops2:
        out += _query(f'[out:json][timeout:60];node["shop"~"^({shops2})$"]({bbox});out tags 400;', timeout)
    return out


def fetch(url, timeout=15):
    """Return (status, html, final_url) — status None means unreachable."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # we're auditing, a bad cert is itself a finding
    try:
        r = urllib.request.urlopen(urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (compatible; site-audit/1.0)"}),
            timeout=timeout, context=ctx)
        return r.status, r.read(300_000).decode("utf-8", "replace"), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, "", url
    except Exception:
        return None, "", url


def audit(url, want_html=None):
    """Return (score 1-10, flaw) or (None, None) if the site is fine / unjudgeable."""
    status, html, final = fetch(url)
    if want_html is not None:
        want_html.append(html)

    if status is None:
        return 1, ("The website address published for the business does not load at all — the "
                   "request fails outright, so anyone clicking the link from a search result or "
                   "directory listing reaches nothing.")
    if status >= 500:
        return 1, (f"The website returns a server error (HTTP {status}) instead of a page, so "
                   f"customers clicking through from Google see an error message rather than the business.")
    if status == 404:
        return 1, "The website address returns a 404 'page not found' error rather than a homepage."

    low = html.lower()

    # Parked / placeholder / builder holding pages
    for pat, flaw in [
        (r"domain (isn.t|is not) connected|reconnect your domain",
         "The domain no longer serves a website — it shows a website-builder holding page telling the owner to reconnect the domain, so customers who click through find nothing."),
        (r"this domain (is for sale|may be for sale)|buy this domain",
         "The domain now shows a 'this domain is for sale' parking page rather than the business, so the web address on their listings leads customers nowhere."),
        (r"coming soon|under construction|site is being (built|updated)",
         "The site is still a 'coming soon' placeholder rather than a working website, so anyone searching for the business finds no information, no services and no way to judge them."),
        (r"account (suspended|has been suspended)",
         "The hosting account is suspended and the site shows a suspension notice instead of the business's pages."),
        (r"index of /|<title>\s*403",
         "The web address shows a bare server directory listing instead of a designed homepage."),
    ]:
        if re.search(pat, low):
            return 1, flaw

    if len(html) < 1200:
        return 2, ("The homepage is nearly empty — it returns barely any content at all, so there "
                   "is nothing for a customer to read and nothing for Google to index.")

    flaws, score = [], 7

    if final.startswith("http://") and not final.startswith("https://"):
        flaws.append("the site still runs on plain http with no SSL certificate, so Chrome shows "
                     "visitors a 'Not secure' warning in the address bar")
        score -= 3

    if not re.search(r'<meta[^>]+name=["\']viewport', low):
        flaws.append("there is no mobile viewport tag, so the page renders at desktop width on a "
                     "phone and visitors have to pinch and zoom to read anything")
        score -= 3

    yrs = [int(y) for y in re.findall(r"(?:©|&copy;|copyright)[^0-9]{0,20}(20[0-2][0-9])", low)]
    if yrs and max(yrs) <= 2023:
        flaws.append(f"the footer copyright is frozen at {max(yrs)}, which makes an active business "
                     f"look abandoned to anyone checking whether they're still trading")
        score -= 2

    if re.search(r"lorem ipsum|your text here|add your (own )?(text|content)|"
                 r"sample (text|page)|placeholder text", low):
        flaws.append("parts of the page still contain the template's placeholder filler text that "
                     "was never replaced with real content")
        score -= 3

    if re.search(r"wix\.com|wixsite\.com|weebly|godaddysites|business\.site", low) and len(html) < 30_000:
        flaws.append("it's a bare website-builder template with very little of its own content, so "
                     "it reads as generic rather than as an established local business")
        score -= 2

    if not re.search(r"tel:|\b0[12378][0-9\s\-()]{8,}", html):
        flaws.append("there is no clickable phone number anywhere on the homepage, so a customer "
                     "ready to call has to hunt for a way to get in touch")
        score -= 2

    if not flaws:
        return None, None
    return max(1, score), (flaws[0][0].upper() + flaws[0][1:] + ".") if len(flaws) == 1 else \
        (flaws[0][0].upper() + flaws[0][1:] + ", and " + flaws[1] + ".")


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
BAD_MAIL = re.compile(r"(no-?reply|example\.|sentry|wixpress|@2x|\.png|\.jpg|\.gif|"
                      r"godaddy|squarespace|wordpress|@sentry|protection)", re.I)


FREEMAIL = ("gmail.com", "googlemail.com", "yahoo.co.uk", "yahoo.com", "ymail.com",
            "hotmail.com", "hotmail.co.uk", "outlook.com", "outlook.co.uk",
            "live.com", "live.co.uk", "msn.com", "icloud.com", "me.com", "mac.com",
            "aol.com", "aol.co.uk", "btinternet.com", "sky.com", "virginmedia.com",
            "talktalk.net", "protonmail.com", "proton.me", "gmx.com", "mail.com")


def _plausible(addr, base_url, name):
    """A scraped address must plausibly belong to THIS business - not a webmaster,
    not a person merely named on the page, not another company's contact."""
    norm = lambda x: re.sub(r"[^a-z0-9]", "", (x or "").lower())
    local, _, dom = addr.lower().partition("@")
    base_url = (base_url or "").strip().lower()

    if base_url in ("", "none", "n/a", "-"):
        return True                       # no site to contradict it

    site_dom = re.sub(r"^https?://(www\.)?|/.*$", "", base_url)
    site_stem = norm(site_dom.split(".")[0])
    mail_stem = norm(dom.split(".")[0])
    local_flat = norm(local)

    if dom not in FREEMAIL:
        # A company domain must relate to the site's domain, else it's someone else's.
        return bool(site_stem) and (site_stem in mail_stem or mail_stem in site_stem)

    # Freemail: only if it's a role address, echoes the name, or echoes the domain.
    if local in ("info", "hello", "enquiries", "contact", "bookings", "sales", "admin"):
        return True
    if any(w in local_flat for w in re.findall(r"[a-z]{4,}", name.lower())):
        return True
    return bool(site_stem) and (site_stem in local_flat or local_flat in site_stem)


def find_email(base_url, html="", name=""):
    """Look for a published address on the homepage, then the contact page."""
    pages = [html] if html else []
    for path in ("contact", "contact-us", "about"):
        u = base_url.rstrip("/") + "/" + path
        st, h, _ = fetch(u, timeout=10)
        if st == 200 and h:
            pages.append(h)
            break
    for page in pages:
        for m in EMAIL_RE.findall(page):
            m = m.lower()
            if BAD_MAIL.search(m) or len(m) >= 60:
                continue
            if _plausible(m, base_url, name):
                return m
    return ""


def existing():
    names, domains, mails, phones = set(), set(), set(), set()
    for p in (LEADS, SENT):
        if not p.exists():
            continue
        with p.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                names.add((r.get("Business Name") or "").strip().lower())
                w = (r.get("Website") or "").strip().lower()
                if w:
                    domains.add(re.sub(r"^https?://(www\.)?|/.*$", "", w))
                m = (r.get("Email") or "").strip().lower()
                if "@" in m:
                    mails.add(m)
                ph = re.sub(r"\D", "", r.get("Phone") or "")
                if len(ph) >= 9:
                    phones.add(ph[-9:])
    if DNC.exists():
        for line in DNC.read_text(encoding="utf-8").splitlines():
            a = line.split(",")[0].strip().lower()
            if "@" in a:
                mails.add(a)
    return names, domains, mails, phones


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--tile", type=int, default=None, help="0-7, which part of London")
    ap.add_argument("--max", type=int, default=25, help="max leads to keep")
    ap.add_argument("--audit-limit", type=int, default=120, help="max sites to fetch")
    a = ap.parse_args()

    tiles = [TILES[a.tile % len(TILES)]] if a.tile is not None else TILES
    names, domains, mails, phones = existing()
    print(f"Known already: {len(names)} businesses, {len(domains)} domains, {len(mails)} emails\n")

    kept, audited, seen = [], 0, set()
    for label, bbox in tiles:
        if len(kept) >= a.max or audited >= a.audit_limit:
            break
        print(f"[{label}] querying OpenStreetMap…")
        els = overpass(bbox)
        print(f"  {len(els)} businesses returned")

        for e in els:
            if len(kept) >= a.max or audited >= a.audit_limit:
                break
            t = e.get("tags", {})
            name = (t.get("name") or "").strip()
            if not name or name.lower() in names or name.lower() in seen:
                continue
            if CHAINS.search(name):
                continue
            trade = CRAFTS.get(t.get("craft", "")) or SHOPS.get(t.get("shop", ""))
            if not trade:
                continue

            email = (t.get("email") or t.get("contact:email") or "").strip().lower()
            phone = (t.get("phone") or t.get("contact:phone") or "").strip()
            site = (t.get("website") or t.get("contact:website") or "").strip()
            if email and ("@" not in email or email in mails):
                continue
            if phone and re.sub(r"\D", "", phone)[-9:] in phones:
                continue
            if not email and not phone:
                continue  # no way to reach them at all

            area = (t.get("addr:suburb") or t.get("addr:district")
                    or t.get("addr:city") or "").strip()
            if area.lower() in ("", "london", "greater london"):
                pc = (t.get("addr:postcode") or "").strip().upper().split()
                area = POSTCODE_AREA.get(pc[0], "") if pc else ""
                if not area:
                    continue  # no usable borough = can't personalise = skip

            if not site:
                kept.append([name, trade, area, phone, email, "", "",
                             "The business has no website at all, so when local customers search "
                             "for this trade nothing of theirs comes up and the enquiry goes to a "
                             "competitor who does have a page.", "B"])
                seen.add(name.lower())
                print(f"  + [B] {name} ({area}) {email or phone}")
                continue

            if re.search(r"/franchise|/stores?/|/locations?/|/branch(es)?/|/find-us/",
                         site, re.I):
                continue  # a page on a national chain's site, not an independent business
            dom = re.sub(r"^https?://(www\.)?|/.*$", "", site.lower())
            if dom in domains or dom in seen:
                continue
            audited += 1
            box = []
            score, flaw = audit(site, want_html=box)
            if score is None:
                continue
            if not email and score >= 2:  # dead sites have no page to scrape
                email = find_email(site, box[0] if box else "", name)
                if email and email in mails:
                    continue
            kept.append([name, trade, area, phone, email, site, str(score), flaw, "A"])
            seen.add(name.lower()); seen.add(dom)
            print(f"  + [A/{score}] {name} ({area}) {email or phone}")

    print(f"\nAudited {audited} sites, kept {len(kept)} leads "
          f"({sum(1 for k in kept if k[4])} with an email).")

    if not kept:
        print("Nothing new found. Try a different --tile.")
        return
    if not a.write:
        print("\nDry run — pass --write to append to leads.csv.")
        return

    with LEADS.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(kept)
    print(f"Appended {len(kept)} leads to leads.csv")


if __name__ == "__main__":
    main()
