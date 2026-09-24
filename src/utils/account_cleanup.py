"""
Account cleanup utilities for handling deactivated account deletion.
Async version using SQLAlchemy AsyncSession.
"""

from datetime import datetime, timedelta, timezone

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

        logger.info(f"Starting deactivated account cleanup. Cutoff date: {cutoff_date.isoformat()}")

        # SEC-RBAC-06: never let the cleanup job purge a Super Admin account.
        # Super Admins are managed out of band, never through this automated path.
        from src.api.models.user_models.roles import Role
        from src.api.models.user_models.user_roles import UserRole

        super_admin_ids = (
            select(UserRole.user_id)
            .join(Role, Role.id == UserRole.role_id)
            .where(Role.hierarchy_level >= 100, UserRole.workspace_id.is_(None))
        )

        # Async SELECT
        result = await db.execute(
            select(Users).where(
                Users.status == "inactive",
                Users.deactivated_at.isnot(None),
                Users.deactivated_at <= cutoff_date,
                Users.deleted_at.is_(None),
                Users.id.notin_(super_admin_ids),
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


# ------------------------------------------------------------------
# PERMANENT PURGE (ANONYMIZATION)
# ------------------------------------------------------------------
async def permanent_purge_deleted_accounts(db: AsyncSession) -> int:
    """
    Permanently purge (anonymize) accounts that have been soft-deleted past the retention period.
    This preserves billing and audit history while destroying PII.
    """
    import uuid

    from sqlalchemy import delete

    from src.api.config import get_settings
    from src.api.models.subscription_models.subscriptions import (
        SubscriptionStatus,
        UserSubscription,
    )
    from src.api.models.user_models.oauth_accounts import OAuthAccount
    from src.api.models.user_models.token_blacklist import TokenBlacklist
    from src.api.models.user_models.user_roles import UserRole
    from src.api.models.user_models.user_sessions import UserSession
    from src.api.models.workspace_models.workspace_member import WorkspaceMembers

    settings = get_settings()
    retention_days = settings.USER_DELETION_RETENTION_DAYS
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

    try:
        logger.info(
            f"Starting permanent purge of accounts deleted before {cutoff_date.isoformat()}"
        )

        # We only want to select users who are soft-deleted but not yet anonymized.
        # Use SKIP LOCKED to avoid race conditions with other workers
        query = (
            select(Users)
            .where(
                Users.deleted_at.isnot(None),
                Users.deleted_at <= cutoff_date,
                Users.status != "anonymized",
            )
            .with_for_update(skip_locked=True)
        )

        result = await db.execute(query)
        users_to_purge = result.scalars().all()

        purged_count = 0

        for user in users_to_purge:
            try:
                user_id = user.id

                # 1. Prune non-essential relational data
                await db.execute(delete(UserSession).where(UserSession.user_id == user_id))
                await db.execute(delete(TokenBlacklist).where(TokenBlacklist.user_id == user_id))
                await db.execute(delete(OAuthAccount).where(OAuthAccount.user_id == user_id))
                await db.execute(delete(UserRole).where(UserRole.user_id == user_id))
                await db.execute(
                    delete(WorkspaceMembers).where(WorkspaceMembers.user_id == user_id)
                )

                # 2. Cancel active subscriptions (Integration with Stripe/provider would ideally happen via events,
                # but we must mark them locally to prevent further local billing logic)
                subs_result = await db.execute(
                    select(UserSubscription).where(
                        UserSubscription.user_id == user_id,
                        UserSubscription.status.in_(
                            [SubscriptionStatus.ACTIVE.value, SubscriptionStatus.TRIAL.value]
                        ),
                    )
                )
                active_subs = subs_result.scalars().all()
                for sub in active_subs:
                    sub.status = SubscriptionStatus.CANCELLED.value
                    sub.cancelled_at = datetime.now(timezone.utc)
                    db.add(sub)

                # 3. Anonymize User PII
                fake_uuid = str(uuid.uuid4())
                user.email = f"deleted_{fake_uuid}@purged.local"
                user.full_name = "Deleted User"
                user.display_name = "Deleted User"
                user.avatar_url = None
                user.password_hash = None
                user.bio = None
                user.registration_device_fingerprint = None
                user.status = "anonymized"

                purged_count += 1
                logger.info(f"Permanently purged (anonymized) user {user_id}")

            except Exception as e:
                logger.error(f"Error purging user {user.id}: {str(e)}")
                continue

        if purged_count > 0:
            await db.commit()
            logger.info(f"Successfully purged {purged_count} account(s)")
        else:
            logger.info("No accounts pending permanent purge")

        return purged_count

    except Exception as e:
        logger.error(f"Error during permanent purge job: {str(e)}")
        await db.rollback()
        raise
