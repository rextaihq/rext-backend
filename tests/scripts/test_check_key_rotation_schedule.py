"""
Tests for LemonSqueezy API Key Rotation Schedule Checker

Tests the check_key_rotation_schedule.py script functionality.
"""

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

# Add scripts directory to path
scripts_dir = Path(__file__).parent.parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

# Import the rotation checker functions
from check_key_rotation_schedule import (  # noqa: E402 -- intentional: avoids a circular import
    ROTATION_POLICY_DAYS,
    ROTATION_URGENT_DAYS,
    ROTATION_WARNING_DAYS,
    check_rotation_status,
    get_last_rotation_date,
    update_rotation_date,
)


@pytest.fixture
def temp_tracking_file(monkeypatch):
    """Create a temporary tracking file for tests"""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        temp_file = f.name

    # Patch the tracking file path
    monkeypatch.setattr("check_key_rotation_schedule.ROTATION_TRACKING_FILE", temp_file)

    yield temp_file

    # Cleanup
    if os.path.exists(temp_file):
        os.remove(temp_file)


class TestGetLastRotationDate:
    """Test retrieving last rotation date"""

    def test_get_valid_rotation_date(self, temp_tracking_file):
        """Test retrieving a valid rotation date"""
        # Write a known date to tracking file
        test_date = datetime(2025, 1, 1, 12, 0, 0)

        with open(temp_tracking_file, "w") as f:
            f.write(test_date.isoformat())

        # Get the date
        result = get_last_rotation_date()

        assert result == test_date

    def test_get_invalid_date_format(self, temp_tracking_file):
        """Test handling invalid date format in tracking file"""
        # Write invalid date format
        with open(temp_tracking_file, "w") as f:
            f.write("invalid-date-format")

        # Should return current date and not crash
        result = get_last_rotation_date()

        # Should be close to now
        assert abs((datetime.now() - result).total_seconds()) < 5


class TestUpdateRotationDate:
    """Test updating rotation date"""

    def test_update_creates_file(self, temp_tracking_file):
        """Test that update_rotation_date creates the file"""
        # Remove temp file if it exists
        if os.path.exists(temp_tracking_file):
            os.remove(temp_tracking_file)

        # Update rotation date
        update_rotation_date()

        # File should exist
        assert os.path.exists(temp_tracking_file)

    def test_update_writes_current_date(self, temp_tracking_file):
        """Test that update_rotation_date writes current date"""
        # Update rotation date
        update_rotation_date()

        # Read back the date
        with open(temp_tracking_file) as f:
            written_date_str = f.read().strip()

        written_date = datetime.fromisoformat(written_date_str)

        # Should be very close to now (within 5 seconds)
        assert abs((datetime.now() - written_date).total_seconds()) < 5

    def test_update_overwrites_existing_date(self, temp_tracking_file):
        """Test that update_rotation_date overwrites existing date"""
        # Write old date
        old_date = datetime(2024, 1, 1)
        with open(temp_tracking_file, "w") as f:
            f.write(old_date.isoformat())

        # Update to current date
        update_rotation_date()

        # Read back
        with open(temp_tracking_file) as f:
            new_date_str = f.read().strip()

        new_date = datetime.fromisoformat(new_date_str)

        # Should be current date, not old date
        assert new_date > old_date
        assert abs((datetime.now() - new_date).total_seconds()) < 5


class TestCheckRotationStatus:
    """Test rotation status checking"""

    def test_status_ok_recently_rotated(self, temp_tracking_file):
        """Test status when key was recently rotated"""
        # Set last rotation to 10 days ago
        last_rotation = datetime.now() - timedelta(days=10)

        with open(temp_tracking_file, "w") as f:
            f.write(last_rotation.isoformat())

        # Check status
        status = check_rotation_status()

        assert status["status"] == "ok"
        assert status["days_since"] == 10
        assert status["days_until"] == ROTATION_POLICY_DAYS - 10
        assert "No action required" in status["message"]

    def test_status_warning_approaching_rotation(self, temp_tracking_file):
        """Test status when rotation is approaching (within warning period)"""
        # Set last rotation to (POLICY - WARNING + 1) days ago
        # E.g., 90 - 30 + 1 = 61 days ago → 29 days until due (within warning)
        days_ago = ROTATION_POLICY_DAYS - ROTATION_WARNING_DAYS + 1
        last_rotation = datetime.now() - timedelta(days=days_ago)

        with open(temp_tracking_file, "w") as f:
            f.write(last_rotation.isoformat())

        # Check status
        status = check_rotation_status()

        assert status["status"] == "warning"
        assert status["days_until"] == ROTATION_WARNING_DAYS - 1
        assert "Start planning" in status["message"]

    def test_status_urgent_rotation_due_soon(self, temp_tracking_file):
        """Test status when rotation is urgent (within urgent period)"""
        # Set last rotation to (POLICY - URGENT + 1) days ago
        # E.g., 90 - 7 + 1 = 84 days ago → 6 days until due (urgent)
        days_ago = ROTATION_POLICY_DAYS - ROTATION_URGENT_DAYS + 1
        last_rotation = datetime.now() - timedelta(days=days_ago)

        with open(temp_tracking_file, "w") as f:
            f.write(last_rotation.isoformat())

        # Check status
        status = check_rotation_status()

        assert status["status"] == "urgent"
        assert status["days_until"] <= ROTATION_URGENT_DAYS
        assert "URGENT" in status["message"]

    def test_status_overdue_rotation_past_due(self, temp_tracking_file):
        """Test status when rotation is overdue"""
        # Set last rotation to (POLICY + 10) days ago
        days_ago = ROTATION_POLICY_DAYS + 10
        last_rotation = datetime.now() - timedelta(days=days_ago)

        with open(temp_tracking_file, "w") as f:
            f.write(last_rotation.isoformat())

        # Check status
        status = check_rotation_status()

        assert status["status"] == "overdue"
        assert status["days_until"] <= 0
        assert "OVERDUE" in status["message"]

    def test_status_exact_rotation_day(self, temp_tracking_file):
        """Test status on exact rotation day"""
        # Set last rotation to exactly POLICY days ago
        last_rotation = datetime.now() - timedelta(days=ROTATION_POLICY_DAYS)

        with open(temp_tracking_file, "w") as f:
            f.write(last_rotation.isoformat())

        # Check status
        status = check_rotation_status()

        # On exact day, days_until = 0, which is <= 0 → overdue
        assert status["status"] == "overdue"
        assert status["days_until"] == 0


class TestRotationWorkflow:
    """Integration tests for complete rotation workflows"""

    def test_new_installation_workflow(self, temp_tracking_file):
        """Test workflow for new installation (no tracking file)"""
        # Remove tracking file
        if os.path.exists(temp_tracking_file):
            os.remove(temp_tracking_file)

        # Check status (should initialize)
        status = check_rotation_status()

        # Should create file and return 'ok' status
        assert status["status"] == "ok"
        assert os.path.exists(temp_tracking_file)
        assert status["days_until"] == ROTATION_POLICY_DAYS

    def test_complete_rotation_workflow(self, temp_tracking_file):
        """Test complete rotation: overdue → rotate → update → ok"""
        # 1. Initial state: rotation is overdue
        old_date = datetime.now() - timedelta(days=ROTATION_POLICY_DAYS + 5)
        with open(temp_tracking_file, "w") as f:
            f.write(old_date.isoformat())

        # Check status: should be overdue
        status = check_rotation_status()
        assert status["status"] == "overdue"

        # 2. Perform rotation (simulated by updating date)
        update_rotation_date()

        # 3. Check status again: should be ok now
        status = check_rotation_status()
        assert status["status"] == "ok"
        assert status["days_until"] == ROTATION_POLICY_DAYS

    def test_rotation_reminder_progression(self, temp_tracking_file):
        """Test status progression as time passes"""
        # Start: Just rotated
        current_date = datetime.now()

        # Status at 50 days (ok - not in warning period yet)
        # ROTATION_POLICY_DAYS = 90, WARNING = 30, so 90-30 = 60 days is boundary
        # Use 50 days to be safely in 'ok' status
        date_50_days_ago = current_date - timedelta(days=50)
        with open(temp_tracking_file, "w") as f:
            f.write(date_50_days_ago.isoformat())

        status = check_rotation_status()
        assert status["status"] == "ok"

        # Status at 70 days (warning - within 30 day warning period)
        date_70_days_ago = current_date - timedelta(days=70)
        with open(temp_tracking_file, "w") as f:
            f.write(date_70_days_ago.isoformat())

        status = check_rotation_status()
        assert status["status"] == "warning"

        # Status at 85 days (urgent - within 7 day urgent period)
        date_85_days_ago = current_date - timedelta(days=85)
        with open(temp_tracking_file, "w") as f:
            f.write(date_85_days_ago.isoformat())

        status = check_rotation_status()
        assert status["status"] == "urgent"

        # Status at 95 days (overdue - past 90 day policy)
        date_95_days_ago = current_date - timedelta(days=95)
        with open(temp_tracking_file, "w") as f:
            f.write(date_95_days_ago.isoformat())

        status = check_rotation_status()
        assert status["status"] == "overdue"


class TestEdgeCases:
    """Test edge cases and error conditions"""

    def test_future_rotation_date(self, temp_tracking_file):
        """Test handling of rotation date in the future (invalid scenario)"""
        # Set last rotation to future date (should not happen normally)
        future_date = datetime.now() + timedelta(days=10)

        with open(temp_tracking_file, "w") as f:
            f.write(future_date.isoformat())

        # Check status
        status = check_rotation_status()

        # days_since will be negative
        assert status["days_since"] < 0
        # days_until will be > POLICY
        assert status["days_until"] > ROTATION_POLICY_DAYS

    def test_very_old_rotation_date(self, temp_tracking_file):
        """Test handling of very old rotation date"""
        # Set last rotation to 1 year ago
        old_date = datetime.now() - timedelta(days=365)

        with open(temp_tracking_file, "w") as f:
            f.write(old_date.isoformat())

        # Check status
        status = check_rotation_status()

        assert status["status"] == "overdue"
        assert status["days_since"] == 365
        assert status["days_until"] < 0

    def test_empty_tracking_file(self, temp_tracking_file):
        """Test handling of empty tracking file"""
        # Create empty file
        with open(temp_tracking_file, "w") as f:
            f.write("")

        # Should handle gracefully (return current date)
        result = get_last_rotation_date()

        # Should be close to now
        assert abs((datetime.now() - result).total_seconds()) < 5


class TestCommandLineInterface:
    """Test CLI argument handling"""

    @patch("sys.argv", ["check_key_rotation_schedule.py", "--update"])
    def test_cli_update_flag(self, temp_tracking_file):
        """Test --update command line flag"""
        from check_key_rotation_schedule import main

        # Run with --update flag
        exit_code = main()

        # Should succeed
        assert exit_code == 0

        # File should exist with current date
        assert os.path.exists(temp_tracking_file)

    @patch("sys.argv", ["check_key_rotation_schedule.py", "--strict"])
    def test_cli_strict_mode_rotation_ok(self, temp_tracking_file):
        """Test --strict mode when rotation is not due"""
        from check_key_rotation_schedule import main

        # Set recent rotation
        recent_date = datetime.now() - timedelta(days=10)
        with open(temp_tracking_file, "w") as f:
            f.write(recent_date.isoformat())

        # Run in strict mode
        exit_code = main()

        # Should return 0 (ok)
        assert exit_code == 0

    @patch("sys.argv", ["check_key_rotation_schedule.py", "--strict"])
    def test_cli_strict_mode_rotation_overdue(self, temp_tracking_file):
        """Test --strict mode when rotation is overdue"""
        from check_key_rotation_schedule import main

        # Set overdue rotation
        overdue_date = datetime.now() - timedelta(days=ROTATION_POLICY_DAYS + 10)
        with open(temp_tracking_file, "w") as f:
            f.write(overdue_date.isoformat())

        # Run in strict mode
        with pytest.raises(SystemExit) as exc_info:
            main()

        # Should exit with code 1 (failure)
        assert exc_info.value.code == 1
