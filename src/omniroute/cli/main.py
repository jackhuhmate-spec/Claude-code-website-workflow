"""
Omniroute CLI entrypoint.

Provides a unified interface for pipeline management, lead operations,
and system status.

Usage::

    omniroute status                    Pipeline snapshot
    omniroute leads list                List leads
    omniroute leads import-csv          Sync CSV → DB
    omniroute hunt [--tile N]           Run lead hunter (dry)
    omniroute hunt --write              Run lead hunter (real)
    omniroute outreach                  Dry-run outreach cycle
    omniroute outreach --send           Send outreach
    omniroute replies                   Check replies (draft)
    omniroute replies --auto            Reply automatically
    omniroute deploy --business X       Build & deploy preview
    omniroute db init                   Create DB tables
    omniroute db test                   Test DB connection
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from omniroute.agents.lead_hunter import LeadHunterAgent
from omniroute.agents.base import AgentContext
from omniroute.config import PROJECT_ROOT, settings
from omniroute.logging_setup import configure_logging, get_logger

log = get_logger("omniroute.cli")


def _add_run_cfg(args: argparse.Namespace) -> AgentContext:
    """Build an AgentContext from CLI args.

    Args:
        args: Parsed command-line arguments.

    Returns:
        AgentContext with dry_run/force/auto flags.
    """
    return AgentContext(
        dry_run=not getattr(args, "send", False) and not getattr(args, "auto", False),
        force=getattr(args, "force", False),
        config={
            "tile": getattr(args, "tile", None),
            "max_leads": getattr(args, "max", 25),
            "limit": getattr(args, "limit", 30),
            "days": getattr(args, "days", 3),
            "delay": getattr(args, "delay", 45),
        },
    )


# ── Status command ──────────────────────────────────────────────────────


def cmd_status(_args: argparse.Namespace) -> int:
    """Print pipeline status."""
    has_db = False
    eng = None
    try:
        from omniroute.db.session import get_engine as _ge
        from omniroute.db.migrations import table_exists as _te
        eng = _ge()
        has_db = _te(eng, "leads")
    except ImportError:
        pass
    except Exception:
        pass

    print("=" * 52)
    print("  OMNIROUTE — PIPELINE STATUS")
    print("=" * 52)

    if has_db:
        from omniroute.services.lead_service import LeadService
        svc = LeadService(data_dir=PROJECT_ROOT)
        snap = svc.get_pipeline_snapshot()
        print(f"  DB leads .............. {snap['db_leads']}")
        print(f"  CSV leads ............. {snap['csv_leads']}")
        print(f"  Contacted ............. {snap['contacted']}")
        print(f"  Replied ............... {snap['replied']}")
        print(f"  Opted out ............. {snap['opted_out']}")
        print(f"  New ................... {snap['new']}")
        print(f"  Interested ............ {snap['interested']}")
        print(f"  Won ................... {snap['won']}")
    else:
        # Fallback: read CSV directly
        import csv

        csv_path = PROJECT_ROOT / "leads.csv"
        if csv_path.exists():
            with csv_path.open(newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            with_email = sum(1 for r in rows if (r.get("Email") or "").strip())
            print(f"  CSV leads ............. {len(rows)}")
            print(f"  With email ............ {with_email}")
        else:
            print("  No database or CSV found")

    # Check PAUSED kill switch
    paused_path = PROJECT_ROOT / "PAUSED"
    print(f"  PAUSED ................ {'YES — cold sending halted' if paused_path.exists() else 'No'}")
    print(f"  Dry-run ............... {'Yes (safe)' if not settings.auto_send else 'No (live)'}")

    print("-" * 52)
    print(f"  Version ............... 0.1.0")
    print(f"  Data dir .............. {PROJECT_ROOT}")
    print("=" * 52)
    return 0


# ── Leads commands ─────────────────────────────────────────────────────


def cmd_leads(args: argparse.Namespace) -> int:
    """Handle lead-related commands."""
    if args.subcommand == "list":
        return _leads_list(args)
    if args.subcommand == "import":
        return _leads_import(args)
    return 1


def _leads_list(args: argparse.Namespace) -> int:
    """List leads from the database or CSV."""
    has_db = False
    try:
        from omniroute.db.session import get_engine as _ge
        from omniroute.db.migrations import table_exists as _te
        eng = _ge()
        has_db = _te(eng, "leads")
    except ImportError:
        pass
    except Exception:
        pass

    if has_db:
        from omniroute.services.lead_service import LeadService
        svc = LeadService(data_dir=PROJECT_ROOT)
        leads = svc.get_leads(
            status=args.status,
            trade=args.trade,
            area=args.area,
            limit=args.limit or 20,
        )

        if not leads:
            print("No leads found.")
            return 0

        print(f"{'ID':>3} {'Business':<28} {'Trade':<18} {'Area':<15} {'Score':>2} {'Group':>1} {'Status':<14}")
        print("-" * 90)
        for l in leads:
            score = str(l.website_score or "?")
            print(f"{l.id:>3} {l.business_name:<28} {l.trade:<18} {l.london_area:<15} {score:>2}  {l.group or '?':>1}  {l.status:<14}")
        print(f"\n  {len(leads)} leads shown")
    else:
        # Fallback: CSV
        import csv
        csv_path = PROJECT_ROOT / "leads.csv"
        if not csv_path.exists():
            print("No leads.csv found.")
            return 1
        with csv_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        print(f"{'Business':<28} {'Trade':<18} {'Area':<15} {'Email':<30}")
        print("-" * 95)
        for r in rows[:20]:
            print(f"{r.get('Business Name', ''):<28} {r.get('Trade', ''):<18} {r.get('London Area', ''):<15} {r.get('Email', ''):<30}")
        print(f"\n  {min(len(rows), 20)} of {len(rows)} leads shown")
    return 0


def _leads_import(args: argparse.Namespace) -> int:
    """Import leads from CSV to database."""
    from omniroute.services.lead_service import LeadService
    from omniroute.db.migrations import run_migrations

    # Ensure tables exist
    try:
        run_migrations(verbose=False)
    except Exception as e:
        log.error("Migration failed: %s", e)
        return 1

    svc = LeadService(data_dir=PROJECT_ROOT)
    try:
        result = svc.sync_from_csv()
        print(f"Sync complete: {result['created']} created, {result['skipped']} skipped (of {result['total']})")
        return 0
    except Exception as e:
        log.error("Import failed: %s", e)
        return 1


# ── Hunt command ───────────────────────────────────────────────────────


def cmd_hunt(args: argparse.Namespace) -> int:
    """Run the lead hunter agent."""
    ctx = _add_run_cfg(args)
    ctx.config["max_leads"] = args.max or 25
    if getattr(args, "write", False):
        ctx.dry_run = False

    agent = LeadHunterAgent(context=ctx)
    result = agent.run()

    print(result.summary or f"Lead hunter {'succeeded' if result.success else 'failed'}")
    if result.error:
        print(f"  Error: {result.error}", file=sys.stderr)
    return 0 if result.success else 1


# ── Outreach command ───────────────────────────────────────────────────


def cmd_outreach(args: argparse.Namespace) -> int:
    """Run outreach cycle."""
    from omniroute.agents.outreach import OutreachAgent

    ctx = _add_run_cfg(args)
    ctx.config["limit"] = args.limit or 30
    ctx.config["delay"] = args.delay or 45

    agent = OutreachAgent(context=ctx)
    result = agent.run()

    print(result.summary or f"Outreach {'succeeded' if result.success else 'failed'}")
    if result.error:
        print(f"  Error: {result.error}", file=sys.stderr)
    return 0 if result.success else 1


# ── Replies command ────────────────────────────────────────────────────


def cmd_replies(args: argparse.Namespace) -> int:
    """Run reply checking cycle."""
    from omniroute.agents.reply_handler import ReplyHandlerAgent

    ctx = _add_run_cfg(args)
    ctx.config["days"] = args.days or 3

    agent = ReplyHandlerAgent(context=ctx)
    result = agent.run()

    print(result.summary or f"Reply handler {'succeeded' if result.success else 'failed'}")
    buckets = result.data.get("buckets", {})
    if buckets:
        print("  Classifications:")
        for cat, count in sorted(buckets.items()):
            if count:
                print(f"    {cat:<12} {count}")
    if result.error:
        print(f"  Error: {result.error}", file=sys.stderr)
    return 0 if result.success else 1


# ── Deploy command ─────────────────────────────────────────────────────


def cmd_deploy(args: argparse.Namespace) -> int:
    """Deploy a website preview."""
    import csv

    from omniroute.agents.site_builder import SiteBuilderAgent

    # Look up the full lead first — fail fast with a clear message if unknown.
    business = args.business
    lead_data: dict[str, object] = {}
    leads_file = PROJECT_ROOT / "leads.csv"
    if leads_file.exists():
        with leads_file.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("Business Name", "").strip().lower() == business.lower():
                    lead_data = {
                        "business_name": row.get("Business Name", business),
                        "trade": row.get("Trade", ""),
                        "area": row.get("London Area", ""),
                        "phone": row.get("Phone", ""),
                        "email": row.get("Email", ""),
                        "services": [row.get("Trade", "")],
                    }
                    break
    if not lead_data:
        print(f"Lead '{business}' not found in leads.csv", file=sys.stderr)
        return 1

    ctx = AgentContext(
        dry_run=not getattr(args, "send", False),
        config={
            **lead_data,
            "business_name": business,
            "final": getattr(args, "final", False),
        },
    )

    agent = SiteBuilderAgent(context=ctx)
    result = agent.run()

    print(result.summary or f"Deploy {'succeeded' if result.success else 'failed'}")
    if result.error:
        print(f"  Error: {result.error}", file=sys.stderr)
    return 0 if result.success else 1


# ── DB commands ────────────────────────────────────────────────────────


def cmd_db(args: argparse.Namespace) -> int:
    """Handle database commands."""
    from omniroute.db.migrations import run_migrations
    from omniroute.db.session import test_connection

    if args.db_sub == "init":
        result = run_migrations(verbose=True)
        print(f"Migration: {result}")
        return 0

    if args.db_sub == "test":
        result = test_connection()
        import json
        print(json.dumps(result, indent=2))
        return 0 if result.get("connected") else 1

    return 1


# ── Main parser ────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser.

    Returns:
        Configured ArgumentParser.
    """
    p = argparse.ArgumentParser(prog="omniroute", description="Autonomous AI Website Agency")
    p.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")

    sub = p.add_subparsers(dest="command", help="Command")

    # status
    sub.add_parser("status", help="Pipeline snapshot")

    # leads
    leads_p = sub.add_parser("leads", help="Lead management")
    ls_sub = leads_p.add_subparsers(dest="subcommand")

    leads_list = ls_sub.add_parser("list", help="List leads")
    leads_list.add_argument("--limit", type=int, default=20)
    leads_list.add_argument("--status", default=None)
    leads_list.add_argument("--trade", default=None)
    leads_list.add_argument("--area", default=None)

    leads_import = ls_sub.add_parser("import", help="Import CSV leads to database")

    # hunt
    hunt_p = sub.add_parser("hunt", help="Run lead hunter")
    hunt_p.add_argument("--write", action="store_true", help="Actually append to leads.csv")
    hunt_p.add_argument("--tile", type=int, default=None, help="London tile (0-7)")
    hunt_p.add_argument("--max", type=int, default=25, help="Max leads")

    # outreach
    out_p = sub.add_parser("outreach", help="Outreach cycle")
    out_p.add_argument("--send", action="store_true", help="Actually send emails")
    out_p.add_argument("--limit", type=int, default=30)
    out_p.add_argument("--delay", type=int, default=45)

    # replies
    rep_p = sub.add_parser("replies", help="Check replies")
    rep_p.add_argument("--auto", action="store_true", help="Actually send replies")
    rep_p.add_argument("--days", type=int, default=3)

    # deploy
    dep_p = sub.add_parser("deploy", help="Deploy a website")
    dep_p.add_argument("--business", required=True)
    dep_p.add_argument("--send", action="store_true", help="Actually deploy to Netlify")
    dep_p.add_argument("--final", action="store_true", help="Mark as final production site")

    # db
    db_p = sub.add_parser("db", help="Database management")
    db_sub = db_p.add_subparsers(dest="db_sub")
    db_sub.add_parser("init", help="Create database tables")
    db_sub.add_parser("test", help="Test database connection")

    return p


def main(argv: list[str] | None = None) -> int:
    """Parse args and dispatch to the matching command.

    Args:
        argv: Command-line arguments (defaults to sys.argv).

    Returns:
        Exit code (0 = success).
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    # Configure logging
    configure_logging(
        level="DEBUG" if getattr(args, "verbose", False) else settings.log_level,
        fmt=settings.log_format,
    )

    if not args.command:
        parser.print_help()
        return 0

    dispatch = {
        "status": cmd_status,
        "leads": cmd_leads,
        "hunt": cmd_hunt,
        "outreach": cmd_outreach,
        "replies": cmd_replies,
        "deploy": cmd_deploy,
        "db": cmd_db,
    }

    handler = dispatch.get(args.command)
    if handler:
        return handler(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
