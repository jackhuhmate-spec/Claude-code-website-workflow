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
import argparse, csv, json, os, re, ssl, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
LEADS = HERE / "leads.csv"
SENT = HERE / "sent_log.csv"
DNC = HERE / "do_not_contact.csv"

OVERPASS = ["https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter"]
UA = "leadbot/1.0 (small business web audit)"

# Second lead source: Google Places (the data behind Google Maps). Requires
# GOOGLE_PLACES_API_KEY (free tier: $200/mo credit, plenty for ~60 calls/day).
# Without the key the hunter silently runs OpenStreetMap-only.
GOOGLE_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "")
GOOGLE_TS = "https://maps.googleapis.com/maps/api/place/textsearch/json"
GOOGLE_DETAILS = "https://maps.googleapis.com/maps/api/place/details/json"
# Areas to search when running the Google source, rotated by day like TILES.
GOOGLE_AREAS = ["Croydon", "Bromley", "Ilford", "Romford", "Ealing", "Wembley",
                "Enfield", "Barnet", "Woolwich", "Lewisham", "Harrow", "Uxbridge",
                "Kingston upon Thames", "Sutton", "Hounslow", "Walthamstow"]
# (trade label in leads.csv, Google query term) — the trades we pitch, in Google language.
GOOGLE_QUERIES = [
    ("Plumber", "plumber"), ("Electrician", "electrician"), ("Roofer", "roofer"),
    ("Heating Engineer", "heating engineer boiler repair"), ("Carpenter", "carpenter joiner"),
    ("Painter & Decorator", "painter decorator"), ("Tiler", "tiler"),
    ("Hair Salon", "hairdresser barber"), ("Landscape Gardener", "landscape gardener"),
    ("Window Fitter", "window installer glazier"),
]

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
    # East London (E)
    "E1": "Whitechapel", "E2": "Bethnal Green", "E3": "Bow", "E4": "Chingford",
    "E5": "Clapton", "E6": "East Ham", "E7": "Forest Gate", "E8": "Hackney",
    "E9": "Homerton", "E10": "Leyton", "E11": "Leytonstone", "E12": "Manor Park",
    "E13": "Plaistow", "E14": "Poplar", "E15": "Stratford", "E16": "Canning Town",
    "E17": "Walthamstow", "E18": "South Woodford", "E20": "Olympic Park",
    # North London (N)
    "N1": "Islington", "N2": "East Finchley", "N3": "Finchley", "N4": "Finsbury Park",
    "N5": "Highbury", "N6": "Highgate", "N7": "Holloway", "N8": "Crouch End",
    "N9": "Lower Edmonton", "N10": "Muswell Hill", "N11": "New Southgate",
    "N12": "North Finchley", "N13": "Palmers Green", "N14": "Southgate",
    "N15": "Seven Sisters", "N16": "Stoke Newington", "N17": "Tottenham",
    "N18": "Upper Edmonton", "N19": "Archway", "N20": "Totteridge",
    "N21": "Winchmore Hill", "N22": "Wood Green",
    # South East London (SE)
    "SE1": "Southwark", "SE2": "Abbey Wood", "SE3": "Blackheath",
    "SE4": "Brockley", "SE5": "Camberwell", "SE6": "Catford", "SE7": "Charlton",
    "SE8": "Deptford", "SE9": "Eltham", "SE10": "Greenwich", "SE11": "Lambeth",
    "SE12": "Lee", "SE13": "Lewisham", "SE14": "New Cross", "SE15": "Peckham",
    "SE16": "Rotherhithe", "SE17": "Walworth", "SE18": "Woolwich",
    "SE19": "Upper Norwood", "SE20": "Penge", "SE21": "Dulwich",
    "SE22": "East Dulwich", "SE23": "Forest Hill", "SE24": "Herne Hill",
    "SE25": "South Norwood", "SE26": "Sydenham", "SE27": "West Norwood",
    "SE28": "Thamesmead",
    # South West London (SW)
    "SW1": "Westminster", "SW2": "Brixton", "SW3": "Chelsea", "SW4": "Clapham",
    "SW5": "Earls Court", "SW6": "Fulham", "SW7": "South Kensington",
    "SW8": "Nine Elms", "SW9": "Stockwell", "SW10": "West Brompton",
    "SW11": "Battersea", "SW12": "Balham", "SW13": "Barnes", "SW14": "Mortlake",
    "SW15": "Putney", "SW16": "Streatham", "SW17": "Tooting",
    "SW18": "Wandsworth", "SW19": "Wimbledon", "SW20": "Raynes Park",
    # West London (W)
    "W1": "Mayfair", "W2": "Paddington", "W3": "Acton", "W4": "Chiswick",
    "W5": "Ealing", "W6": "Hammersmith", "W7": "Hanwell", "W8": "Kensington",
    "W9": "Maida Vale", "W10": "North Kensington", "W11": "Notting Hill",
    "W12": "Shepherds Bush", "W13": "West Ealing", "W14": "West Kensington",
    # North West London (NW)
    "NW1": "Camden", "NW2": "Cricklewood", "NW3": "Hampstead",
    "NW4": "Hendon", "NW5": "Kentish Town", "NW6": "Kilburn",
    "NW7": "Mill Hill", "NW8": "St Johns Wood", "NW9": "Colindale",
    "NW10": "Willesden", "NW11": "Golders Green",
    # Outer London boroughs
    "BR1": "Bromley", "BR2": "Bromley", "CR0": "Croydon", "CR2": "Croydon",
    "DA1": "Dartford", "DA5": "Bexley", "DA6": "Bexleyheath", "DA7": "Erith",
    "EN1": "Enfield", "EN2": "Enfield", "EN3": "Enfield", "EN4": "Barnet",
    "EN5": "Barnet", "HA0": "Wembley", "HA1": "Harrow", "HA2": "Harrow",
    "HA3": "Harrow", "HA4": "Ruislip", "HA5": "Harrow", "HA7": "Stanmore",
    "HA8": "Edgware", "IG1": "Ilford", "IG2": "Ilford", "IG3": "Ilford",
    "IG6": "Ilford", "KT1": "Kingston", "KT2": "Kingston", "KT3": "New Malden",
    "KT4": "Worcester Park", "KT5": "Surbiton", "KT6": "Surbiton",
    "RM1": "Romford", "RM2": "Romford", "RM3": "Romford", "RM6": "Chadwell Heath",
    "RM7": "Romford", "SM1": "Sutton", "SM2": "Sutton", "SM3": "Sutton",
    "SM4": "Morden", "SM5": "Carshalton", "SM6": "Wallington",
    "TW1": "Twickenham", "TW2": "Twickenham", "TW3": "Hounslow",
    "TW4": "Hounslow", "TW5": "Hounslow", "TW6": "Heathrow",
    "TW7": "Isleworth", "TW8": "Brentford", "TW9": "Richmond",
    "TW10": "Richmond", "TW11": "Teddington", "TW12": "Hampton",
    "TW13": "Feltham", "TW14": "Feltham",
    "UB1": "Southall", "UB2": "Southall", "UB3": "Hayes",
    "UB4": "Hayes", "UB5": "Northolt", "UB6": "Greenford",
    "UB7": "West Drayton", "UB8": "Uxbridge", "UB9": "Uxbridge",
    "WD1": "Watford", "WD3": "Rickmansworth", "WD6": "Borehamwood",
    "WD17": "Watford",
}

# Chains and franchises we never contact.
CHAINS = re.compile(r"\b(tesco|sainsbury|asda|morrison|aldi|lidl|co-?op|greggs|costa|"
                    r"starbucks|pret|subway|mcdonald|kfc|burger king|domino|papa john|"
                    r"pizza hut|nando|wagamama|toni ?& ?guy|supercuts|specsavers|vision express|"
                    r"boots|superdrug|halfords|kwik ?fit|f1 autocentre|national tyres|"
                    r"timpson|max spielmann|ismash|o2|ee|vodafone|three|carphone)\b", re.I)


def _query(q, timeout=120):
    """Send an Overpass query with retry and exponential backoff on 429."""
    last = None
    for attempt, host in enumerate(OVERPASS):
        try:
            delay = 2 ** attempt  # exponential backoff: 1s, 2s, 4s
            if attempt > 0:
                time.sleep(delay)
            req = urllib.request.Request(
                host, data=urllib.parse.urlencode({"data": q}).encode(),
                headers={"User-Agent": UA, "Accept": "application/json"})
            r = urllib.request.urlopen(req, timeout=timeout)
            return json.loads(r.read()).get("elements", [])
        except urllib.error.HTTPError as e:
            if e.code == 429:
                # Respect Retry-After header, fall back to exponential backoff
                retry_after = e.headers.get("Retry-After")
                wait = int(retry_after) if retry_after and retry_after.isdigit() else delay
                print(f"  Overpass 429 — retrying in {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            last = f"HTTP {e.code}"
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
        time.sleep(3)
    print(f"  Overpass unavailable ({last})", file=sys.stderr)
    return []


def overpass(bbox, timeout=120):
    """Two small queries beat one big one — with 6s gaps for rate limits."""
    out = []
    out += _query(f'[out:json][timeout:60];node["craft"]({bbox});out tags 400;', timeout)
    time.sleep(6)
    shops = "|".join(list(SHOPS)[:8])
    out += _query(f'[out:json][timeout:60];node["shop"~"^({shops})$"]({bbox});out tags 400;', timeout)
    time.sleep(6)
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


def _gjson(url, timeout=20):
    """GET a Google Places URL and return the JSON body, or None on any failure."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def _garea(comp):
    """Best London area name from a Place's address_components (postal_town > locality)."""
    want = {"postal_town", "locality", "administrative_area_level_2"}
    for typ in ("postal_town", "locality", "administrative_area_level_2"):
        for c in comp or []:
            if typ in c.get("types", []) and c.get("long_name"):
                return c["long_name"].replace("London", "").strip() or c["long_name"]
    return ""


def google_places(area, kept, audited, seen, names, domains, mails, phones, max_leads, audit_limit):
    """Second lead source: Google Places text search in one London area.

    Google returns businesses WITH websites (unlike OSM, where the daily email
    yield is structurally low) — each site is then audited and scraped for an
    email exactly like the OSM path. Needs GOOGLE_PLACES_API_KEY; without it the
    hunter just runs OpenStreetMap. Returns (kept, audited).
    """
    if not GOOGLE_KEY:
        print("  (no GOOGLE_PLACES_API_KEY — Google source skipped)")
        return kept, audited
    print(f"[{area}] querying Google Places…")
    for trade, q in GOOGLE_QUERIES:
        if len(kept) >= max_leads or audited >= audit_limit:
            break
        url = (f"{GOOGLE_TS}?query={urllib.parse.quote(f'{q} in {area} London')}"
               f"&key={GOOGLE_KEY}&maxprice=2")
        d = _gjson(url)
        if not d or d.get("status") not in ("OK", "ZERO_RESULTS"):
            if d and d.get("status") == "OVER_QUERY_LIMIT":
                print("  Google rate limit — stopping Google source for today.")
                return kept, audited
            time.sleep(0.3)
            continue
        for res in d.get("results", [])[:3]:  # top 3 per trade keeps API cost bounded
            if len(kept) >= max_leads or audited >= audit_limit:
                break
            name = (res.get("name") or "").strip()
            if not name or name.lower() in names or name.lower() in seen:
                continue
            if CHAINS.search(name):
                continue
            pid = res.get("place_id")
            site = phone = ""
            if pid:
                dd = _gjson(f"{GOOGLE_DETAILS}?place_id={pid}"
                            f"&fields=formatted_phone_number,website&key={GOOGLE_KEY}")
                if dd and dd.get("status") == "OK":
                    site = (dd.get("result", {}).get("website") or "").strip()
                    phone = (dd.get("result", {}).get("formatted_phone_number") or "").strip()
            site = re.sub(r"^www\.", "https://", site)
            garea = _garea(res.get("address_components")) or area
            if phone and re.sub(r"\D", "", phone)[-9:] in phones:
                continue
            email = ""
            if not site:
                kept.append([name, trade, garea, phone, email, "", "",
                             "The business has no website at all, so when local customers search "
                             "for this trade nothing of theirs comes up and the enquiry goes to a "
                             "competitor who does have a page.", "B"])
                seen.add(name.lower())
                print(f"  + [B] {name} ({garea}) {email or phone}")
                continue
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
                if email:
                    if email in mails:
                        continue
                    mails.add(email)
            if not email and not phone:
                continue  # Google gave a site but nothing reachable
            kept.append([name, trade, garea, phone, email, site, str(score), flaw, "A"])
            seen.add(name.lower())
            domains.add(dom)
            print(f"  + [A/{score}] {name} ({garea}) {email or phone}")
            time.sleep(0.2)
    return kept, audited


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

    # Second source: Google Places, one London area rotated by day. The daily hunt
    # calls with a tile; pick the area that matches the tile rotation so all of
    # London is covered over a week without hammering the API every day.
    if a.tile is not None:
        google_area = GOOGLE_AREAS[a.tile % len(GOOGLE_AREAS)]
        kept, audited = google_places(google_area, kept, audited, seen,
                                      names, domains, mails, phones,
                                      a.max, a.audit_limit)

    print(f"\nAudited {audited} sites, kept {len(kept)} leads "
          f"({sum(1 for k in kept if k[4])} with an email).")

    if not kept:
        print("Nothing new found. Try a different --tile.")
        return
    if not a.write:
        print("\nDry run — pass --write to append to leads.csv.")
        return

    # If leads.csv is missing/empty, write the header first — otherwise the first
    # business row becomes the header and every downstream DictReader misreads it
    # (gmail_send_batch then KeyErrors on 'Business Name'). Must match the columns
    # every reader expects.
    HEADER = ["Business Name", "Trade", "London Area", "Phone", "Email",
              "Website", "Website Score", "Biggest Flaw", "Group"]
    new_file = not LEADS.exists() or LEADS.stat().st_size == 0
    with LEADS.open("a", newline="", encoding="utf-8") as f:
        if new_file:
            csv.writer(f).writerow(HEADER)
        csv.writer(f).writerows(kept)
    print(f"Appended {len(kept)} leads to leads.csv")


if __name__ == "__main__":
    main()
