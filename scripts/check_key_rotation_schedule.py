#!/usr/bin/env python3
"""
LemonSqueezy API Key Rotation Schedule Checker

Checks if API key rotation is due based on configured rotation policy.
Sends alerts when rotation is needed.

Usage:
    python scripts/check_key_rotation_schedule.py

    # Check rotation schedule and exit with code 0 if not due, 1 if due
    python scripts/check_key_rotation_schedule.py --strict

    # Update last rotation date (run after completing rotation)
    python scripts/check_key_rotation_schedule.py --update

Configuration:
    ROTATION_POLICY_DAYS: Days between rotations (default: 90)
    ROTATION_WARNING_DAYS: Days before rotation to start warning (default: 30)
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path


# Configuration
ROTATION_POLICY_DAYS = int(os.getenv("KEY_ROTATION_POLICY_DAYS", "90"))
ROTATION_WARNING_DAYS = int(os.getenv("KEY_ROTATION_WARNING_DAYS", "30"))
ROTATION_URGENT_DAYS = int(os.getenv("KEY_ROTATION_URGENT_DAYS", "7"))

# File to track last rotation date
ROTATION_TRACKING_FILE = "docs/security/.last-key-rotation"


def ensure_tracking_file_exists():
    """Create tracking file and directory if they don't exist"""
    tracking_path = Path(ROTATION_TRACKING_FILE)

    # Create directory if needed
    tracking_path.parent.mkdir(parents=True, exist_ok=True)

    # Create file with current date if it doesn't exist
    if not tracking_path.exists():
        print("⚠️  No rotation history found. Creating tracking file...")
        update_rotation_date()
        print(f"   Created: {ROTATION_TRACKING_FILE}")
        print(f"   Next rotation due in {ROTATION_POLICY_DAYS} days")
        return False

    return True


def get_last_rotation_date() -> datetime:
    """Get the last rotation date from tracking file"""
    tracking_path = Path(ROTATION_TRACKING_FILE)

    with open(tracking_path) as f:
        last_rotation_str = f.read().strip()

    try:
        return datetime.fromisoformat(last_rotation_str)
    except ValueError:
        # Invalid format, assume current date
        print(f"⚠️  Invalid date format in {ROTATION_TRACKING_FILE}")
        print("   Using current date as last rotation")
        return datetime.now()


def update_rotation_date():
    """Update the last rotation date to current date"""
    tracking_path = Path(ROTATION_TRACKING_FILE)
    tracking_path.parent.mkdir(parents=True, exist_ok=True)

    current_date = datetime.now()

    with open(tracking_path, "w") as f:
        f.write(current_date.isoformat())

    print(f"✅ Updated last rotation date to: {current_date.strftime('%Y-%m-%d')}")
    print(
        f"   Next rotation due: {(current_date + timedelta(days=ROTATION_POLICY_DAYS)).strftime('%Y-%m-%d')}"
    )


def check_rotation_status() -> dict:
    """
    Check rotation status and return detailed information

    Returns:
        dict with keys: last_rotation, days_since, days_until, status, message
    """
    if not ensure_tracking_file_exists():
        # New tracking file created, no action needed yet
        return {
            "last_rotation": datetime.now(),
            "days_since": 0,
            "days_until": ROTATION_POLICY_DAYS,
            "status": "ok",
            "message": "Tracking initialized",
        }

    last_rotation = get_last_rotation_date()
    days_since_rotation = (datetime.now() - last_rotation).days
    days_until_due = ROTATION_POLICY_DAYS - days_since_rotation

    # Determine status
    if days_until_due <= 0:
        status = "overdue"
        message = "ROTATION OVERDUE - Perform rotation immediately"
    elif days_until_due <= ROTATION_URGENT_DAYS:
        status = "urgent"
        message = f"URGENT: Rotation due in {days_until_due} days - Schedule immediately"
    elif days_until_due <= ROTATION_WARNING_DAYS:
        status = "warning"
        message = f"Rotation due in {days_until_due} days - Start planning"
    else:
        status = "ok"
        message = "No action required"

    return {
        "last_rotation": last_rotation,
        "days_since": days_since_rotation,
        "days_until": days_until_due,
        "status": status,
        "message": message,
        "next_rotation": last_rotation + timedelta(days=ROTATION_POLICY_DAYS),
    }


def print_status(status_info: dict):
    """Print formatted status information"""
    print("=" * 60)
    print("LemonSqueezy API Key Rotation Status")
    print("=" * 60)
    print()
    print(f"Rotation Policy:     Every {ROTATION_POLICY_DAYS} days")
    print(f"Last Rotation:       {status_info['last_rotation'].strftime('%Y-%m-%d')}")
    print(f"Days Since Rotation: {status_info['days_since']} days")
    print(f"Next Rotation Due:   {status_info['next_rotation'].strftime('%Y-%m-%d')}")
    print(f"Days Until Due:      {status_info['days_until']} days")
    print()

    # Status-based output
    if status_info["status"] == "overdue":
        print("🚨 STATUS: OVERDUE")
        print(f"   {status_info['message']}")
        print()
        print("   ACTION REQUIRED:")
        print("   1. Review docs/security/API_KEY_ROTATION.md")
        print("   2. Schedule maintenance window")
        print("   3. Execute rotation procedure")
        print("   4. Update tracking: python scripts/check_key_rotation_schedule.py --update")

    elif status_info["status"] == "urgent":
        print("⚠️  STATUS: URGENT")
        print(f"   {status_info['message']}")
        print()
        print("   ACTION REQUIRED:")
        print("   1. Schedule rotation this week")
        print("   2. Notify engineering team")
        print("   3. Prepare rotation procedure")

    elif status_info["status"] == "warning":
        print("📅 STATUS: UPCOMING")
        print(f"   {status_info['message']}")
        print()
        print("   RECOMMENDED ACTIONS:")
        print("   1. Review rotation procedure")
        print("   2. Schedule rotation date")
        print("   3. Notify stakeholders")

    else:
        print("✅ STATUS: CURRENT")
        print(f"   {status_info['message']}")
        print(f"   Next check recommended in {ROTATION_WARNING_DAYS} days")

    print()
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Check LemonSqueezy API key rotation schedule")
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update last rotation date to now (run after completing rotation)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if rotation is due (for CI/CD checks)",
    )

    args = parser.parse_args()

    # Update mode
    if args.update:
        update_rotation_date()
        return 0

    # Check mode
    status_info = check_rotation_status()
    print_status(status_info)

    # Strict mode for CI/CD
    if args.strict:
        if status_info["status"] in ["overdue", "urgent"]:
            sys.exit(1)

    return 0


if __name__ == "__main__":
    sys.exit(main())
