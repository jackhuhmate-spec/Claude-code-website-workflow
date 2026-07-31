"""
Deployment provider abstraction.

Defines the interface for deploying static websites to hosting providers
(Netlify, Vercel, Cloudflare Pages, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DeployConfig:
    """Configuration for a deployment."""

    business_name: str
    trade: str
    area: str
    phone: str
    email: str = ""
    services: list[str] = field(default_factory=list)
    accent_colour: str = "#1a6fb5"
    is_final: bool = False


@dataclass
class DeployResult:
    """Result of a deployment."""

    success: bool
    url: str | None = None
    site_id: str | None = None
    deploy_id: str | None = None
    state: str | None = None
    error: str | None = None


class DeployProvider(ABC):
    """Abstract interface for website deployment."""

    @abstractmethod
    def deploy(self, config: DeployConfig) -> DeployResult:
        """Build and deploy a website.

        Args:
            config: Deployment configuration.

        Returns:
            DeployResult with the live URL.
        """
        ...

    @abstractmethod
    def delete_site(self, site_id: str) -> bool:
        """Delete a deployed site.

        Args:
            site_id: The provider's site ID.

        Returns:
            True if deleted successfully.
        """
        ...

    @abstractmethod
    def list_sites(self) -> list[dict[str, Any]]:
        """List all deployed sites.

        Returns:
            List of site metadata dicts.
        """
        ...

    @abstractmethod
    def test_connection(self) -> dict[str, Any]:
        """Test the provider API connection.

        Returns:
            Dict with status information.
        """
        ...
