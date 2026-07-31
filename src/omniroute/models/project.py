"""
Project, Deployment, and Website ORM models.

Tracks the lifecycle of a website build from requirements collection
through design, deployment, and ongoing maintenance.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omniroute.models.base import Base, DictMixin, TimestampMixin


class Project(Base, TimestampMixin, DictMixin):
    """A website build project for a customer."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="requirements", nullable=False, index=True
    )
    # requirements → design → review → building → deployed → maintenance

    # Requirements
    services_list: Mapped[Optional[str]] = mapped_column(Text, default=None)
    opening_hours: Mapped[Optional[str]] = mapped_column(String(255), default=None)
    service_area: Mapped[Optional[str]] = mapped_column(String(255), default=None)
    has_logo: Mapped[bool] = mapped_column(Boolean, default=False)
    accent_colour: Mapped[str] = mapped_column(String(16), default="#1a6fb5")
    desired_pages: Mapped[Optional[str]] = mapped_column(Text, default=None)
    inspiration_urls: Mapped[Optional[str]] = mapped_column(Text, default=None)
    special_features: Mapped[Optional[str]] = mapped_column(Text, default=None)

    # Build
    design_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    build_started: Mapped[Optional[date]] = mapped_column(Date, default=None)
    build_completed: Mapped[Optional[date]] = mapped_column(Date, default=None)

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text, default=None)

    # Relationships
    customer: Mapped["Customer"] = relationship(  # type: ignore  # noqa: F821
        "Customer", back_populates="projects"
    )
    deployments: Mapped[list["Deployment"]] = relationship(
        "Deployment", back_populates="project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Project {self.id}: {self.name} ({self.status})>"


class Deployment(Base, TimestampMixin, DictMixin):
    """A deployment of a website to Netlify (or other provider)."""

    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=False, index=True
    )

    environment: Mapped[str] = mapped_column(
        String(16), default="preview", nullable=False
    )  # preview or production
    status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False
    )  # pending, deploying, live, failed, retired
    url: Mapped[Optional[str]] = mapped_column(String(512), default=None)

    netlify_site_id: Mapped[Optional[str]] = mapped_column(String(255), default=None)
    netlify_deploy_id: Mapped[Optional[str]] = mapped_column(String(255), default=None)
    deploy_state: Mapped[Optional[str]] = mapped_column(String(32), default=None)

    version: Mapped[Optional[int]] = mapped_column(default=None)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)

    error_message: Mapped[Optional[str]] = mapped_column(Text, default=None)

    # Relationships
    project: Mapped["Project"] = relationship(
        "Project", back_populates="deployments"
    )

    def __repr__(self) -> str:
        return f"<Deployment {self.id}: {self.environment} — {self.status}>"


class Website(Base, TimestampMixin, DictMixin):
    """A website that has been deployed (production tracking)."""

    __tablename__ = "websites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=False, index=True
    )
    project_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("projects.id"), default=None
    )

    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    custom_domain: Mapped[Optional[str]] = mapped_column(String(255), default=None)

    netlify_site_id: Mapped[Optional[str]] = mapped_column(String(255), default=None)
    ssl_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_deploy_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("deployments.id"), default=None
    )

    uptime_status: Mapped[str] = mapped_column(
        String(32), default="unknown"
    )  # unknown, healthy, degraded, down
    last_checked: Mapped[Optional[date]] = mapped_column(Date, default=None)

    maintenance_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    analytics_id: Mapped[Optional[str]] = mapped_column(String(255), default=None)

    def __repr__(self) -> str:
        return f"<Website {self.id}: {self.domain}>"
