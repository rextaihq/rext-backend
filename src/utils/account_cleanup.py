
"""
Account cleanup utilities for handling deactivated account deletion.

This module provides functions to automatically delete accounts that have been
deactivated for 14 days or more.
"""

from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.api.models.user_models.users import Users
from src.utils.logger import logger


def delete_deactivated_accounts(db: Session) -> int:
    """
    Permanently delete accounts that have been deactivated for 14 days or more.

    This function:
    1. Finds all users with status='inactive' and deactivated_at >= 14 days ago
    2. Sets deleted_at timestamp for soft deletion
    3. Returns count of deleted accounts

    Args:
        db: SQLAlchemy database session

    Returns:
        int: Number of accounts deleted

    Example:
        >>> from src.api.database.async_database import get_async_db as get_db
        >>> db = next(get_db())
        >>> deleted_count = delete_deactivated_accounts(db)
        >>> logger.info(f"Deleted {deleted_count} accounts")
    """
    try:
        # Calculate cutoff date (14 days ago)
        cutoff_date = datetime.utcnow() - timedelta(days=14)

        logger.info(f"Starting deactivated account cleanup. Cutoff date: {cutoff_date.isoformat()}")

        # Find all inactive users deactivated 14+ days ago
        result = db.execute(
            select(Users).where(
                Users.status == "inactive",
                Users.deactivated_at.isnot(None),
                Users.deactivated_at <= cutoff_date,
                Users.deleted_at.is_(None)
            )
        )
        deactivated_users = result.scalars().all()

        deleted_count = 0

        for user in deactivated_users:
            try:
                # Soft delete the user
                user.deleted_at = datetime.utcnow()
                logger.info(
                    f"Deleting deactivated account: {user.email} (ID: {user.id}), "
                    f"deactivated on {user.deactivated_at.isoformat()}"
                )
                deleted_count += 1

            except Exception as e:
                logger.error(f"Error deleting user {user.id}: {str(e)}")
                continue

        # Commit all deletions
        if deleted_count > 0:
            db.commit()
            logger.info(f"Successfully deleted {deleted_count} deactivated account(s)")
        else:
            logger.info("No deactivated accounts found for deletion")

        return deleted_count

    except Exception as e:
        logger.error(f"Error during deactivated account cleanup: {str(e)}")
        db.rollback()
        raise


def get_pending_deletions(db: Session) -> list:
    """
    Get list of accounts scheduled for deletion with their deletion dates.

    Returns accounts that are deactivated but not yet deleted, along with
    their scheduled deletion date.

    Args:
        db: SQLAlchemy database session

    Returns:
        list: List of dicts containing user info and scheduled deletion date

    Example:
        >>> pending = get_pending_deletions(db)
        >>> for account in pending:
        ...     logger.info(f"{account['email']} - deletes on {account['scheduled_deletion']}")
    """
    try:
        result = db.execute(
            select(Users).where(
                Users.status == "inactive",
                Users.deactivated_at.isnot(None),
                Users.deleted_at.is_(None)
            )
        )
        deactivated_users = result.scalars().all()

        pending_deletions = []
        for user in deactivated_users:
            scheduled_deletion = user.deactivated_at + timedelta(days=14)
            days_remaining = (scheduled_deletion - datetime.utcnow()).days

            pending_deletions.append({
                "user_id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "deactivated_at": user.deactivated_at.isoformat(),
                "scheduled_deletion": scheduled_deletion.isoformat(),
                "days_remaining": max(0, days_remaining)
            })

        return pending_deletions

    except Exception as e:
        logger.error(f"Error getting pending deletions: {str(e)}")
        raise


def cancel_account_deactivation(user_id: str, db: Session) -> bool:
    """
    Cancel account deactivation and reactivate the account.

    Allows users to reactivate their account before the 14-day deletion window expires.

    Args:
        user_id: UUID of the user
        db: SQLAlchemy database session

    Returns:
        bool: True if reactivation successful, False otherwise

    Example:
        >>> success = cancel_account_deactivation("user-uuid", db)
        >>> if success:
        ...     logger.info("Account reactivated successfully")
    """
    try:
        result = db.execute(
            select(Users).where(Users.id == user_id)
        )
        user = result.scalars().first()

        if not user:
            logger.warning(f"User not found: {user_id}")
            return False

        if user.status != "inactive":
            logger.warning(f"User {user_id} is not deactivated (status: {user.status})")
            return False

        # Reactivate account
        user.status = "active"
        user.deactivated_at = None
        user.updated_at = datetime.utcnow()

        db.commit()
        logger.info(f"Account reactivated: {user.email} (ID: {user_id})")

        return True

    except Exception as e:
        logger.error(f"Error reactivating account {user_id}: {str(e)}")
        db.rollback()
        return False
