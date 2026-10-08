#!/usr/bin/env python3
"""
Data Cleanup Script

Manual script for cleaning up old data based on retention policies.
Can be run manually or via cron job.

Usage:
    # Dry run (preview what would be deleted)
    python scripts/cleanup_old_data.py --dry-run

    # Actually delete old data
    python scripts/cleanup_old_data.py

    # Clean specific table only
    python scripts/cleanup_old_data.py --table audit_logs

    # Custom retention period
    python scripts/cleanup_old_data.py --table email_logs --retention-days 60
"""

import asyncio
import argparse
import sys
from pathlib import Path

# Add parent directory to path to import src modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.api.database.async_database import AsyncSessionLocal
from src.services.data_cleanup_service import DataCleanupService
from src.config.cleanup_config import cleanup_config


async def main():
    """Main entry point for cleanup script."""
    parser = argparse.ArgumentParser(
        description="Clean up old data based on retention policies",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to preview deletions
  python scripts/cleanup_old_data.py --dry-run

  # Delete old data from all tables
  python scripts/cleanup_old_data.py

  # Clean only audit logs
  python scripts/cleanup_old_data.py --table audit_logs

  # Custom retention for email logs
  python scripts/cleanup_old_data.py --table email_logs --retention-days 60

Retention Periods (defaults):
  - audit_logs: {audit} days
  - email_logs: {email} days
  - email_events: {event} days (orphaned only)
  - user_sessions: {session} days (inactive)
        """.format(
            audit=cleanup_config.AUDIT_LOG_RETENTION_DAYS,
            email=cleanup_config.EMAIL_LOG_RETENTION_DAYS,
            event=cleanup_config.EMAIL_EVENT_RETENTION_DAYS,
            session=cleanup_config.USER_SESSION_INACTIVE_DAYS,
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be deleted without actually deleting",
    )

    parser.add_argument(
        "--table",
        choices=["audit_logs", "email_logs", "email_events", "user_sessions", "all"],
        default="all",
        help="Specific table to clean (default: all)",
    )

    parser.add_argument(
        "--retention-days", type=int, help="Override default retention period (in days)"
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=cleanup_config.CLEANUP_BATCH_SIZE,
        help=f"Batch size for deletion (default: {cleanup_config.CLEANUP_BATCH_SIZE})",
    )

    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")
    # Below one day the cutoff is now or later: the run would take every row of the table.
    if args.retention_days is not None and args.retention_days < 1:
        parser.error("--retention-days must be at least 1")

    # Print configuration
    print("=" * 70)
    print("DATA CLEANUP SCRIPT")
    print("=" * 70)
    print(
        f"Mode: {'DRY RUN (no data will be deleted)' if args.dry_run else 'LIVE (data will be deleted)'}"
    )
    print(f"Table: {args.table}")
    print(f"Batch size: {args.batch_size}")
    print()

    if args.retention_days:
        print(f"Custom retention: {args.retention_days} days")
    else:
        print("Default retention periods:")
        for table, period in cleanup_config.get_retention_summary().items():
            print(f"  - {table}: {period}")

    print("=" * 70)
    print()

    if not args.dry_run:
        response = input("Are you sure you want to proceed? This will DELETE data. (yes/no): ")
        if response.lower() not in ["yes", "y"]:
            print("Aborted.")
            return

    # Override batch size if specified
    if args.batch_size != cleanup_config.CLEANUP_BATCH_SIZE:
        cleanup_config.CLEANUP_BATCH_SIZE = args.batch_size

    # Run cleanup
    async with AsyncSessionLocal() as db:
        cleanup_service = DataCleanupService(db=db, dry_run=args.dry_run)

        results = {}

        try:
            if args.table == "all":
                print("Running cleanup for all tables...\n")
                results = await cleanup_service.cleanup_all()
            elif args.table == "audit_logs":
                print("Cleaning audit logs...\n")
                results["audit_logs"] = await cleanup_service.cleanup_audit_logs(
                    retention_days=args.retention_days
                )
            elif args.table == "email_logs":
                print("Cleaning email logs...\n")
                results["email_logs"] = await cleanup_service.cleanup_email_logs(
                    retention_days=args.retention_days
                )
            elif args.table == "email_events":
                print("Cleaning orphaned email events...\n")
                results["email_events"] = await cleanup_service.cleanup_email_events(
                    retention_days=args.retention_days
                )
            elif args.table == "user_sessions":
                print("Cleaning inactive user sessions...\n")
                results["user_sessions"] = await cleanup_service.cleanup_inactive_sessions(
                    inactive_days=args.retention_days
                )

            # Print summary
            print()
            print("=" * 70)
            print("CLEANUP SUMMARY")
            print("=" * 70)

            total = 0
            for table, count in results.items():
                action = "Would delete" if args.dry_run else "Deleted"
                print(f"{action:12} {count:6,} records from {table}")
                total += count

            print("-" * 70)
            print(f"{'TOTAL:':12} {total:6,} records")
            print("=" * 70)

            if args.dry_run:
                print("\n✓ Dry run completed. No data was deleted.")
                print("  Run without --dry-run to actually delete data.")
            else:
                print("\n✓ Cleanup completed successfully.")

        except Exception as e:
            print(f"\n✗ ERROR: {str(e)}", file=sys.stderr)
            raise


if __name__ == "__main__":
    asyncio.run(main())
