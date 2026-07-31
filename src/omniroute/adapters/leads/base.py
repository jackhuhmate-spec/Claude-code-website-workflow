"""
Lead source abstraction.

Defines the interface for discovering new business leads from various
sources (OSM, Google Places, local directories, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LeadResult:
    """A discovered lead candidate."""

    business_name: str
    trade: str
    london_area: str
    phone: str = ""
    email: str = ""
    website: str = ""
    website_score: int | None = None
    biggest_flaw: str = ""
    group: str = "A"  # A = bad site, B = no site
    source: str = "unknown"
    source_id: str = ""
    google_business_profile: str = ""
    social_media: str = ""
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class LeadSourceResult:
    """Result of a lead sourcing run."""

    leads: list[LeadResult]
    source: str
    total_found: int
    total_kept: int
    errors: list[str] = field(default_factory=list)


class LeadSource(ABC):
    """Abstract interface for discovering business leads."""

    @abstractmethod
    def discover(
        self,
        *,
        max_leads: int = 25,
        tile: int | None = None,
        trades: list[str] | None = None,
        areas: list[str] | None = None,
    ) -> LeadSourceResult:
        """Discover new business leads.

        Args:
            max_leads: Maximum leads to return.
            tile: Geographic tile/area index (0-7 for London).
            trades: Filter by specific trades.
            areas: Filter by specific areas.

        Returns:
            LeadSourceResult with discovered leads.
        """
        ...

    @abstractmethod
    def name(self) -> str:
        """Return the source name for logging/identification.

        Returns:
            Source name string.
        """
        ...
