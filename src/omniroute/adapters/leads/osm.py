"""
OpenStreetMap lead source adapter.

Discovers businesses using the Overpass API and audits their websites.
Wraps the existing ``ops/lead_hunter.py`` logic through the adapter interface.
"""

from __future__ import annotations

import logging
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from omniroute.adapters.leads.base import LeadResult, LeadSource, LeadSourceResult

log = logging.getLogger("omniroute.adapters.leads.osm")

OVERPASS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
UA = "leadbot/1.0 (small business web audit)"

# Greater London tiles
TILES: list[tuple[str, str]] = [
    ("Inner East", "51.50,-0.10,51.58,0.02"),
    ("Inner South", "51.43,-0.15,51.51,0.00"),
    ("Inner West", "51.47,-0.28,51.55,-0.10"),
    ("North", "51.55,-0.25,51.65,0.02"),
    ("East", "51.48,0.00,51.58,0.18"),
    ("South East", "51.38,-0.10,51.48,0.12"),
    ("South West", "51.35,-0.30,51.45,-0.08"),
    ("West", "51.48,-0.45,51.58,-0.25"),
]

CRAFTS = {
    "plumber": "Plumber",
    "electrician": "Electrician",
    "roofer": "Roofer",
    "carpenter": "Carpenter",
    "joiner": "Carpenter",
    "painter": "Painter & Decorator",
    "plasterer": "Plasterer",
    "tiler": "Tiler",
    "gardener": "Landscaper",
    "handicraft": "Handyman",
    "builder": "Builder",
    "locksmith": "Locksmith",
}

SHOPS = {
    "hairdresser": "Hair Salon",
    "beauty": "Beauty Salon",
    "florist": "Florist",
    "car_repair": "Car Garage",
    "bakery": "Bakery",
    "butcher": "Butcher",
    "dry_cleaning": "Dry Cleaner",
    "pet_grooming": "Dog Groomer",
    "tattoo": "Tattoo Studio",
}

CHAINS = re.compile(
    r"\b(tesco|sainsbury|asda|morrison|aldi|lidl|co-?op|greggs|costa|"
    r"starbucks|pret|subway|mcdonald|kfc|burger king|domino|papa john|"
    r"pizza hut|nando|wagamama|toni ?& ?guy|supercuts|specsavers|"
    r"boots|superdrug|halfords|kwik ?fit|f1 autocentre|national tyres|"
    r"timpson|max spielmann|ismash|o2|ee|vodafone|three|carphone)\b",
    re.I,
)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
BAD_MAIL = re.compile(
    r"(no-?reply|example\.|sentry|wixpress|@2x|\.png|\.jpg|\.gif|"
    r"godaddy|squarespace|wordpress|@sentry|protection)",
    re.I,
)


class OSMLeadSource(LeadSource):
    """Discover leads from OpenStreetMap Overpass API.

    No API key required. Covers Greater London via 8 geographic tiles.
    Audits each candidate site and only keeps businesses with real flaws.
    """

    def __init__(self) -> None:
        self._existing_names: set[str] = set()
        self._existing_domains: set[str] = set()
        self._existing_emails: set[str] = set()
        self._existing_phones: set[str] = set()
        self._tiles = TILES

    def name(self) -> str:
        return "OpenStreetMap"

    def with_existing(
        self,
        names: set[str] | None = None,
        domains: set[str] | None = None,
        emails: set[str] | None = None,
        phones: set[str] | None = None,
    ) -> "OSMLeadSource":
        """Set existing records to avoid duplicates.

        Args:
            names: Existing business names.
            domains: Existing website domains.
            emails: Existing email addresses.
            phones: Existing phone numbers (last 9 digits).

        Returns:
            self for chaining.
        """
        if names:
            self._existing_names = names
        if domains:
            self._existing_domains = domains
        if emails:
            self._existing_emails = emails
        if phones:
            self._existing_phones = phones
        return self

    # ── Overpass queries ────────────────────────────────────────────────

    def _query(self, q: str, timeout: int = 120) -> list[dict[str, Any]]:
        """Execute an Overpass QL query against available mirrors."""
        last_error: str | None = None
        for host in OVERPASS:
            try:
                req = urllib.request.Request(
                    host,
                    data=urllib.parse.urlencode({"data": q}).encode(),
                    headers={"User-Agent": UA, "Accept": "application/json"},
                )
                r = urllib.request.urlopen(req, timeout=timeout)
                return r.json().get("elements", [])
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                time.sleep(3)
        log.warning("Overpass unavailable (%s)", last_error)
        return []

    def _overpass_batch(self, bbox: str, timeout: int = 120) -> list[dict[str, Any]]:
        """Two small queries to avoid Overpass 504s on long regexes."""
        out: list[dict[str, Any]] = []
        out += self._query(
            f'[out:json][timeout:60];node["craft"]({bbox});out tags 400;',
            timeout,
        )
        time.sleep(2)
        shop_keys = "|".join(SHOPS.keys())
        out += self._query(
            f'[out:json][timeout:60];node["shop"~"^({shop_keys})$"]({bbox});out tags 400;',
            timeout,
        )
        return out

    # ── Website audit ───────────────────────────────────────────────────

    def _fetch(
        self, url: str, timeout: int = 15
    ) -> tuple[int | None, str, str]:
        """Fetch a URL and return (status_code, html, final_url)."""
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            r = urllib.request.urlopen(
                urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; site-audit/1.0)"},
                ),
                timeout=timeout,
                context=ctx,
            )
            return r.status, r.read(300_000).decode("utf-8", "replace"), r.geturl()
        except urllib.error.HTTPError as e:
            return e.code, "", url
        except Exception:
            return None, "", url

    def _audit(self, url: str) -> tuple[int | None, str]:
        """Score a website 1-10.

        Returns (score, flaw) or (None, None) if the site is fine.
        """
        status, html, final = self._fetch(url)
        if status is None:
            return 1, "The website address does not load at all."
        if status >= 500:
            return 1, f"The website returns a server error (HTTP {status})."
        if status == 404:
            return 1, "The website address returns a 404 'page not found' error."

        low = html.lower()

        # Parked / placeholder pages
        for pat, flaw in [
            (
                r"domain (isn.t|is not) connected|reconnect your domain",
                "The domain shows a holding page rather than the business.",
            ),
            (
                r"this domain (is for sale|may be for sale)|buy this domain",
                "The domain is a parking page rather than the business.",
            ),
            (
                r"coming soon|under construction|site is being (built|updated)",
                "The site is a 'coming soon' placeholder rather than a working website.",
            ),
            (
                r"account (suspended|has been suspended)",
                "The hosting account is suspended.",
            ),
        ]:
            if re.search(pat, low):
                return 1, flaw

        if len(html) < 1200:
            return 2, "The homepage is nearly empty — barely any content."

        flaws: list[str] = []
        score = 7

        if final.startswith("http://") and not final.startswith("https://"):
            flaws.append("the site runs on plain http with no SSL certificate")
            score -= 3

        if not re.search(r'<meta[^>]+name=["\']viewport', low):
            flaws.append("there is no mobile viewport tag")
            score -= 3

        yrs = [
            int(y)
            for y in re.findall(
                r"(?:©|&copy;|copyright)[^0-9]{0,20}(20[0-2][0-9])", low
            )
        ]
        if yrs and max(yrs) <= 2023:
            flaws.append(f"the footer copyright is frozen at {max(yrs)}")
            score -= 2

        if re.search(
            r"lorem ipsum|your text here|add your (own )?(text|content)|"
            r"sample (text|page)|placeholder text",
            low,
        ):
            flaws.append("parts of the page still contain placeholder filler text")
            score -= 3

        if not flaws:
            return None, None  # Site is fine
        return max(1, score), (flaws[0][0].upper() + flaws[0][1:] + ".")

    def _find_email(self, base_url: str, html: str = "", name: str = "") -> str:
        """Scrape a contact email from the site."""
        pages = [html] if html else []
        for path in ("contact", "contact-us", "about"):
            url = base_url.rstrip("/") + "/" + path
            st, h, _ = self._fetch(url, timeout=10)
            if st == 200 and h:
                pages.append(h)
                break
        for page in pages:
            for m in EMAIL_RE.findall(page):
                m = m.lower()
                if BAD_MAIL.search(m) or len(m) >= 60:
                    continue
                if self._plausible(m, base_url, name):
                    return m
        return ""

    @staticmethod
    def _plausible(addr: str, base_url: str, name: str) -> bool:
        """Check if a scraped email plausibly belongs to this business."""
        norm = lambda x: re.sub(r"[^a-z0-9]", "", (x or "").lower())
        local, _, dom = addr.lower().partition("@")

        if not base_url or base_url.lower() in ("", "none", "n/a", "-"):
            return True

        site_dom = re.sub(r"^https?://(www\.)?|/.*$", "", base_url.lower())
        site_stem = norm(site_dom.split(".")[0])
        local_flat = norm(local)
        mail_stem = norm(dom.split(".")[0])

        FREEMAIL = {
            "gmail.com", "googlemail.com", "yahoo.co.uk", "yahoo.com",
            "hotmail.com", "hotmail.co.uk", "outlook.com", "live.com",
            "icloud.com", "aol.com", "btinternet.com", "sky.com",
        }
        if dom not in FREEMAIL:
            return bool(site_stem) and (
                site_stem in mail_stem or mail_stem in site_stem
            )
        if local in ("info", "hello", "enquiries", "contact", "bookings", "sales", "admin"):
            return True
        if any(w in local_flat for w in re.findall(r"[a-z]{4,}", name.lower())):
            return True
        return False

    # ── Discovery ───────────────────────────────────────────────────────

    def discover(
        self,
        *,
        max_leads: int = 25,
        tile: int | None = None,
        trades: list[str] | None = None,
        areas: list[str] | None = None,
    ) -> LeadSourceResult:
        """Discover leads from OpenStreetMap.

        Args:
            max_leads: Maximum leads to return.
            tile: Specific tile index (0-7). Rotates through all if None.
            trades: Unused (OSM returns whatever exists in the area).
            areas: Unused (tiles cover all of London).

        Returns:
            LeadSourceResult with discovered leads.
        """
        tiles = [self._tiles[tile % len(self._tiles)]] if tile is not None else self._tiles
        errors: list[str] = []
        leads: list[LeadResult] = []
        audited = 0

        for label, bbox in tiles:
            if len(leads) >= max_leads:
                break
            log.info("Querying OSM tile: %s", label)
            elements = self._overpass_batch(bbox)
            log.info("  %d elements returned", len(elements))

            for el in elements:
                if len(leads) >= max_leads:
                    break
                tags = el.get("tags", {})
                name = (tags.get("name") or "").strip()
                if not name or name.lower() in self._existing_names:
                    continue
                if CHAINS.search(name):
                    continue

                trade = CRAFTS.get(tags.get("craft", "")) or SHOPS.get(
                    tags.get("shop", "")
                )
                if not trade:
                    continue

                email = (tags.get("email") or tags.get("contact:email") or "").strip().lower()
                phone = (tags.get("phone") or tags.get("contact:phone") or "").strip()
                site = (tags.get("website") or tags.get("contact:website") or "").strip()

                if email and ("@" not in email or email in self._existing_emails):
                    continue
                if phone and re.sub(r"\D", "", phone)[-9:] in self._existing_phones:
                    continue
                if not email and not phone:
                    continue

                area = (
                    tags.get("addr:suburb")
                    or tags.get("addr:district")
                    or tags.get("addr:city")
                    or ""
                ).strip()
                if not area or area.lower() in ("", "london", "greater london"):
                    continue

                if not site:
                    leads.append(
                        LeadResult(
                            business_name=name,
                            trade=trade,
                            london_area=area,
                            phone=phone,
                            email=email,
                            website="",
                            website_score=None,
                            biggest_flaw=(
                                "The business has no website at all, so when local customers "
                                "search for this trade nothing of theirs comes up."
                            ),
                            group="B",
                            source="osm",
                        )
                    )
                    continue

                if re.search(
                    r"/franchise|/stores?/|/locations?/|/branch(es)?/|/find-us/",
                    site,
                    re.I,
                ):
                    continue

                audited += 1
                score, flaw = self._audit(site)
                if score is None:
                    continue
                if not email and score >= 2:
                    email = self._find_email(site, "", name)

                leads.append(
                    LeadResult(
                        business_name=name,
                        trade=trade,
                        london_area=area,
                        phone=phone,
                        email=email,
                        website=site,
                        website_score=score,
                        biggest_flaw=flaw or "",
                        group="A",
                        source="osm",
                    )
                )

        return LeadSourceResult(
            leads=leads,
            source=self.name(),
            total_found=audited + len(leads),
            total_kept=len(leads),
            errors=errors,
        )
