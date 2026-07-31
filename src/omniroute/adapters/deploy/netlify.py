"""
Netlify deployment adapter.

Builds a static site from configuration and deploys it to Netlify via
the Netlify API. Wraps the existing ``deploy_preview.py`` logic.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import shutil
import ssl
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from omniroute.adapters.deploy.base import DeployConfig, DeployProvider, DeployResult
from omniroute.config import settings
from omniroute.exceptions import AdapterNotConfigured, NetlifyError

log = logging.getLogger("omniroute.adapters.deploy.netlify")

API = "https://api.netlify.com/api/v1"
CA = os.environ.get("SSL_CERT_FILE") or "/root/.ccr/ca-bundle.crt"

# Reuse the existing site builder module
HERE = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(HERE))
import build_site  # type: ignore  # noqa: E402


def _opener() -> urllib.request.OpenerDirector:
    """Create an opener with optional custom CA bundle."""
    ctx = ssl.create_default_context(cafile=CA if os.path.exists(CA) else None)
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ctx),
        urllib.request.ProxyHandler(),
    )


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:30] or "site"


def _call(
    op: urllib.request.OpenerDirector | None,
    req: urllib.request.Request,
    timeout: int = 60,
    tries: int = 4,
) -> dict[str, Any]:
    """Make an API call with retry and backoff.

    Args:
        op: URL opener.
        req: The request object.
        timeout: Request timeout in seconds.
        tries: Number of retry attempts.

    Returns:
        Parsed JSON response.
    """
    if op is None:
        op = _opener()
    for i in range(tries):
        try:
            with op.open(req, timeout=timeout) as r:
                raw = r.read().decode("utf-8", "ignore")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(2**i)
                continue
            raise NetlifyError(f"Netlify API error {e.code}: {e.reason}") from e


def _default_services(trade: str) -> list[str]:
    """Get default service list for a trade."""
    t = (trade or "").lower()
    table = {
        "roofer": [
            "Roof repairs",
            "New roofs & re-roofing",
            "Flat roofs",
            "Guttering",
            "Chimney work",
            "Emergency call-outs",
        ],
        "plumber": [
            "Emergency plumbing",
            "Boiler repair & servicing",
            "Bathroom installation",
            "Leak detection",
            "Blocked drains",
            "Radiators & heating",
        ],
        "electrician": [
            "Rewiring",
            "Fuse board upgrades",
            "EICR & safety checks",
            "Lighting",
            "Sockets & fault-finding",
            "Emergency call-outs",
        ],
    }
    return table.get(
        t,
        ["Free quotes", "Expert workmanship", "Reliable local service", "Emergency call-outs"],
    )


def _build_zip(cfg: dict[str, Any]) -> bytes:
    """Build a 5-page site and return it as a ZIP bytes object.

    Args:
        cfg: Site configuration dict.

    Returns:
        ZIP file bytes.
    """
    tmp = Path(tempfile.mkdtemp(prefix="swiftsite_"))
    try:
        (tmp / "style.css").write_text(
            build_site.css(cfg.get("accent", "#1a6fb5")), encoding="utf-8"
        )
        for page, builder in build_site.BUILDERS.items():
            (tmp / f"{page}.html").write_text(builder(cfg), encoding="utf-8")
        (tmp / "netlify.toml").write_text('[build]\n  publish = "."\n', encoding="utf-8")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for f in tmp.iterdir():
                z.write(f, f.name)
        return buf.getvalue()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class NetlifyAdapter(DeployProvider):
    """Deploy websites to Netlify.

    Requires ``NETLIFY_TOKEN`` to be set in the environment or settings.
    """

    def __init__(self, token: str | None = None) -> None:
        self._token = token or settings.netlify_token
        self._op = _opener()

    def _check_token(self) -> None:
        if not self._token:
            raise AdapterNotConfigured(
                "NETLIFY_TOKEN not set — cannot deploy.",
            )

    def _make_cfg(self, config: DeployConfig) -> dict[str, Any]:
        # Guard the accent colour: it is interpolated into :root{--accent:...;} on
        # every page, so a non-hex value (e.g. `red;}body{display:none}{`) would be
        # injected into the stylesheet verbatim. Same rule build_site.main() applies.
        accent = (config.accent_colour or "#1a6fb5").strip()
        if not re.match(r"^#[0-9a-fA-F]{3,8}$", accent):
            accent = "#1a6fb5"
        return {
            "business_name": config.business_name,
            "trade": config.trade,
            "area": config.area,
            "phone": config.phone,
            "email": config.email,
            "services": config.services or _default_services(config.trade),
            "accent": accent,
        }

    def deploy(self, config: DeployConfig) -> DeployResult:
        """Build and deploy a site to Netlify.

        Args:
            config: Deployment configuration.

        Returns:
            DeployResult with live URL.
        """
        self._check_token()
        cfg = self._make_cfg(config)
        prefix = "" if config.is_final else "preview-"
        name = f"{prefix}{_slug(config.business_name)}-{os.urandom(3).hex()}"

        try:
            # 1. Create the site
            req = urllib.request.Request(
                f"{API}/sites",
                data=json.dumps({"name": name}).encode(),
                method="POST",
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
            )
            site = _call(self._op, req, timeout=60)
            site_id = site["id"]
            url = site.get("ssl_url") or site.get("url")
            log.info("Netlify site created: %s -> %s", site_id, url)

            # 2. Deploy the ZIP
            zip_bytes = _build_zip(cfg)
            req = urllib.request.Request(
                f"{API}/sites/{site_id}/deploys",
                data=zip_bytes,
                method="POST",
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/zip",
                },
            )
            dep = _call(self._op, req, timeout=120)
            deploy_id = dep["id"]

            # 3. Poll until ready
            state = None
            for _ in range(30):
                req = urllib.request.Request(
                    f"{API}/deploys/{deploy_id}",
                    headers={"Authorization": f"Bearer {self._token}"},
                )
                dep = _call(self._op, req, timeout=30)
                state = dep.get("state")
                if state in ("ready", "error"):
                    break
                time.sleep(2)

            log.info("Deploy complete: %s (state=%s)", url, state)
            return DeployResult(
                success=state == "ready",
                url=url,
                site_id=site_id,
                deploy_id=deploy_id,
                state=state,
            )
        except NetlifyError:
            raise
        except Exception as exc:
            log.exception("Deploy failed: %s", exc)
            return DeployResult(
                success=False,
                error=str(exc),
            )

    def delete_site(self, site_id: str) -> bool:
        """Delete a site from Netlify.

        Args:
            site_id: The Netlify site ID.

        Returns:
            True if deleted.
        """
        self._check_token()
        try:
            req = urllib.request.Request(
                f"{API}/sites/{site_id}",
                headers={"Authorization": f"Bearer {self._token}"},
                method="DELETE",
            )
            _call(self._op, req, timeout=30)
            return True
        except Exception as exc:
            log.error("Failed to delete site %s: %s", site_id, exc)
            return False

    def list_sites(self) -> list[dict[str, Any]]:
        """List all sites on the Netlify account.

        Returns:
            List of site metadata dicts.
        """
        self._check_token()
        sites: list[dict[str, Any]] = []
        page = 1
        while True:
            req = urllib.request.Request(
                f"{API}/sites?per_page=100&page={page}",
                headers={"Authorization": f"Bearer {self._token}"},
            )
            batch = _call(self._op, req, timeout=30)
            if not batch:
                break
            sites.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return sites

    def test_connection(self) -> dict[str, Any]:
        """Test the Netlify API connection.

        Returns:
            Dict with connection status.
        """
        if not self._token:
            return {"status": "SKIP", "detail": "NETLIFY_TOKEN not set"}
        try:
            req = urllib.request.Request(
                f"{API}/user",
                headers={"Authorization": f"Bearer {self._token}"},
            )
            data = _call(self._op, req, timeout=30)
            return {
                "status": "OK",
                "email": data.get("email", "?"),
                "id": data.get("id", "?"),
            }
        except Exception as exc:
            return {"status": "FAIL", "error": str(exc)}
