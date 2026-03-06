"""
Account cleanup utilities for handling deactivated account deletion.
Async version using SQLAlchemy AsyncSession.
"""

from datetime import datetime, timezone, timedelta,timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.user_models.users import Users
from src.utils.logger import logger


# ------------------------------------------------------------------
# DELETE DEACTIVATED ACCOUNTS
# ------------------------------------------------------------------
async def delete_deactivated_accounts(db: AsyncSession) -> int:
    """
    Permanently delete accounts that have been deactivated for 14 days or more.
    """
    try:
        # Calculate cutoff date (14 days ago)
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=14)

        logger.info(
            f"Starting deactivated account cleanup. Cutoff date: {cutoff_date.isoformat()}"
        )

        # Async SELECT
        result = await db.execute(
            select(Users).where(
                Users.status == "inactive",
                Users.deactivated_at.isnot(None),
                Users.deactivated_at <= cutoff_date,
                Users.deleted_at.is_(None),
            )
        )

        deactivated_users = result.scalars().all()

        deleted_count = 0

        for user in deactivated_users:
            try:
                # Soft delete the user
                user.deleted_at = datetime.now(timezone.utc)
                logger.info(
                    f"Deleting deactivated account: {user.email} (ID: {user.id}), "
                    f"deactivated on {user.deactivated_at.isoformat()}"
                )

                deleted_count += 1

            except Exception as e:
                logger.error(f"Error deleting user {user.id}: {str(e)}")
                continue

        if deleted_count > 0:
            await db.commit()
            logger.info(f"Successfully deleted {deleted_count} deactivated account(s)")
        else:
            logger.info("No deactivated accounts found for deletion")

        return deleted_count

    except Exception as e:
        logger.error(f"Error during deactivated account cleanup: {str(e)}")
        await db.rollback()
        raise


# ------------------------------------------------------------------
# GET PENDING DELETIONS
# ------------------------------------------------------------------
async def get_pending_deletions(db: AsyncSession) -> list:
    """
    Get list of accounts scheduled for deletion.
    """
    try:
        result = await db.execute(
            select(Users).where(
                Users.status == "inactive",
                Users.deactivated_at.isnot(None),
                Users.deleted_at.is_(None),
            )
        )

        deactivated_users = result.scalars().all()

        pending_deletions = []

        for user in deactivated_users:
            scheduled_deletion = user.deactivated_at + timedelta(days=14)
            days_remaining = (scheduled_deletion - datetime.now(timezone.utc)).days

            pending_deletions.append(
                {
                    "user_id": str(user.id),
                    "email": user.email,
                    "full_name": user.full_name,
                    "deactivated_at": user.deactivated_at.isoformat(),
                    "scheduled_deletion": scheduled_deletion.isoformat(),
                    "days_remaining": max(0, days_remaining),
                }
            )

        return pending_deletions

    except Exception as e:
        logger.error(f"Error getting pending deletions: {str(e)}")
        raise


# ------------------------------------------------------------------
# CANCEL DEACTIVATION
# ------------------------------------------------------------------
async def cancel_account_deactivation(user_id: str, db: AsyncSession) -> bool:
    """
    Cancel account deactivation and reactivate the account.
    """
    try:
        result = await db.execute(select(Users).where(Users.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            logger.warning(f"User not found: {user_id}")
            return False

        if user.status != "inactive":
            logger.warning(f"User {user_id} is not deactivated (status: {user.status})")
            return False

        # Reactivate account
        user.status = "active"
        user.deactivated_at = None
        user.updated_at = datetime.now(timezone.utc)

        await db.commit()

        logger.info(f"Account reactivated: {user.email} (ID: {user_id})")

        return True

    except Exception as e:
        logger.error(f"Error reactivating account {user_id}: {str(e)}")
        await db.rollback()
        return False
