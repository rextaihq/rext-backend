"""
Email Digest Service

Builds and sends the "account activity digest" email to users who have enabled
it in their notification preferences (daily / weekly / monthly cadence).

Flow:
    scheduled task (daily)  ->  DigestService.run()
        -> find users whose digest is enabled AND due for their cadence
        -> aggregate their `notifications` for the period, grouped by type
        -> render + send the digest email
        -> stamp notification_preferences.digest_last_sent_at

A user only receives an email when there is at least one activity item in the
period — an empty digest is skipped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config import get_settings
from src.api.database.async_database import get_async_db_context
from src.api.models.notification.notification_model import Notification
from src.api.models.user_models.notification_preferences import NotificationPreferences
from src.api.models.user_models.users import Users
from src.services.email_service import EmailService
from src.utils.logger import logger

# Nominal cadence, the "is it due yet?" threshold (kept a little below the
# nominal period so a job that runs slightly early/late still fires each day),
# and how far back to look for the very first digest (when we have no
# digest_last_sent_at to anchor on).
_FREQUENCY_CONFIG: Dict[str, Dict[str, timedelta]] = {
    "daily": {"due_after": timedelta(hours=20), "first_lookback": timedelta(days=1)},
    "weekly": {"due_after": timedelta(days=6), "first_lookback": timedelta(days=7)},
    "monthly": {"due_after": timedelta(days=27), "first_lookback": timedelta(days=30)},
}

_FREQUENCY_LABEL = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly"}

# Human titles for notification `type` values; anything not listed is
# title-cased from the raw value.
_TYPE_TITLES = {
    "content": "Content",
    "content_generation": "Content generation",
    "publish": "Publishing",
    "publish_failed": "Publishing",
    "workspace": "Workspace",
    "billing": "Billing & payments",
    "payment": "Billing & payments",
    "subscription": "Subscription",
    "knowledge_base": "Knowledge base",
    "kb": "Knowledge base",
    "security": "Security",
    "system": "System",
    "error": "Issues",
}

# Cap the work per user so a noisy account cannot blow up the job / email.
_MAX_NOTIFICATIONS = 500
_MAX_ITEMS_PER_SECTION = 5


@dataclass
class DigestRunResult:
    checked: int = 0
    sent: int = 0
    skipped_empty: int = 0
    skipped_not_due: int = 0
    errors: int = 0
    error_user_ids: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "checked": self.checked,
            "sent": self.sent,
            "skipped_empty": self.skipped_empty,
            "skipped_not_due": self.skipped_not_due,
            "errors": self.errors,
            "error_user_ids": self.error_user_ids,
        }


def _humanize_type(raw: Optional[str]) -> str:
    if not raw:
        return "Activity"
    key = raw.lower()
    if key in _TYPE_TITLES:
        return _TYPE_TITLES[key]
    return raw.replace("_", " ").replace("-", " ").strip().capitalize() or "Activity"


class DigestService:
    """Builds and sends account-activity digest emails."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()
        self.email_service = EmailService(db)

    # ------------------------------------------------------------------ #
    # Due detection
    # ------------------------------------------------------------------ #
    @staticmethod
    def _normalize_frequency(freq: Optional[str]) -> str:
        freq = (freq or "daily").lower()
        return freq if freq in _FREQUENCY_CONFIG else "daily"

    @classmethod
    def is_due(cls, prefs: NotificationPreferences, now: datetime) -> bool:
        """Whether this user should receive a digest on this run."""
        if not prefs.digest_enabled or not prefs.email_notifications:
            return False
        freq = cls._normalize_frequency(prefs.digest_frequency)
        last = prefs.digest_last_sent_at
        if last is None:
            return True
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return (now - last) >= _FREQUENCY_CONFIG[freq]["due_after"]

    @classmethod
    def _period_start(cls, prefs: NotificationPreferences, now: datetime) -> datetime:
        """Aggregation window start — never look back more than one cadence."""
        freq = cls._normalize_frequency(prefs.digest_frequency)
        floor = now - _FREQUENCY_CONFIG[freq]["first_lookback"]
        last = prefs.digest_last_sent_at
        if last is None:
            return floor
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return max(last, floor)

    # ------------------------------------------------------------------ #
    # Fetch candidates
    # ------------------------------------------------------------------ #
    async def get_enabled_preferences(self) -> List[tuple[NotificationPreferences, Users]]:
        """All (prefs, user) pairs where the digest is switched on."""
        stmt = (
            select(NotificationPreferences, Users)
            .join(Users, Users.id == NotificationPreferences.user_id)
            .where(
                NotificationPreferences.digest_enabled.is_(True),
                NotificationPreferences.email_notifications.is_(True),
                Users.deleted_at.is_(None),
                Users.status == "active",
                Users.email_verified.is_(True),
            )
        )
        result = await self.db.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    # ------------------------------------------------------------------ #
    # Build one digest
    # ------------------------------------------------------------------ #
    async def build_digest(
        self,
        user: Users,
        prefs: NotificationPreferences,
        now: datetime,
    ) -> Optional[dict]:
        """
        Aggregate the user's notifications for the period.

        Returns a dict ready for the template, or None when there is nothing
        to report (caller should not send an email).
        """
        since = self._period_start(prefs, now)

        stmt = (
            select(Notification)
            .where(
                Notification.user_id == user.id,
                Notification.created_at >= since,
                Notification.deleted_at.is_(None),
            )
            .order_by(Notification.created_at.desc())
            .limit(_MAX_NOTIFICATIONS)
        )
        result = await self.db.execute(stmt)
        notifications = list(result.scalars().all())

        if not notifications:
            return None

        # Group by notification type, preserving first-seen order.
        groups: Dict[str, List[Notification]] = {}
        for n in notifications:
            groups.setdefault(n.type or "activity", []).append(n)

        sections: List[dict] = []
        for raw_type, items in groups.items():
            sections.append({
                "title": _humanize_type(raw_type),
                "count": len(items),
                "items": [
                    {
                        "title": it.title,
                        "message": (it.message or "")[:200],
                        "when": it.created_at.strftime("%b %d, %H:%M UTC"),
                    }
                    for it in items[:_MAX_ITEMS_PER_SECTION]
                ],
            })

        freq = self._normalize_frequency(prefs.digest_frequency)
        return {
            "frequency": freq,
            "period_label": _FREQUENCY_LABEL[freq],
            "period_range": (
                f"{since.strftime('%b %d')} – {now.strftime('%b %d, %Y')}"
            ),
            "total_count": len(notifications),
            "sections": sections,
        }

    # ------------------------------------------------------------------ #
    # Send
    # ------------------------------------------------------------------ #
    async def send_digest(
        self,
        user: Users,
        prefs: NotificationPreferences,
        digest: dict,
        now: datetime,
    ) -> bool:
        from emails.templates.notifications import render_digest_email

        frontend = self.settings.FRONTEND_URL.rstrip("/")
        notifications_url = f"{frontend}/notifications"
        unsubscribe_url = f"{frontend}/settings/notifications"
        if prefs.unsubscribe_token:
            unsubscribe_url = (
                f"{frontend}/unsubscribe?token={prefs.unsubscribe_token}&type=digest"
            )

        html = render_digest_email(
            user_name=user.display_name or user.full_name or user.email,
            period_label=digest["period_label"],
            period_range=digest["period_range"],
            total_count=digest["total_count"],
            sections=digest["sections"],
            notifications_url=notifications_url,
            unsubscribe_url=unsubscribe_url,
        )

        updates = digest["total_count"]
        subject = (
            f"Your {digest['period_label'].lower()} digest "
            f"— {updates} update{'s' if updates != 1 else ''}"
        )

        email_log = await self.email_service.send_email(
            to=user.email,
            subject=subject,
            html=html,
            user_id=user.id,
            template_type="digest",
            tags={
                "type": "notification",
                "action": "digest",
                "frequency": digest["frequency"],
            },
        )

        prefs.digest_last_sent_at = now

        sent_ok = email_log.status not in ("failed", "bounced")
        if sent_ok:
            logger.info(
                "Digest email sent",
                extra={
                    "user_id": str(user.id),
                    "frequency": digest["frequency"],
                    "total_count": updates,
                    "email_log_id": str(email_log.id),
                },
            )
        else:
            logger.warning(
                "Digest email send returned non-success status",
                extra={
                    "user_id": str(user.id),
                    "status": email_log.status,
                    "email_log_id": str(email_log.id),
                },
            )
        return sent_ok

    # ------------------------------------------------------------------ #
    # Orchestration
    # ------------------------------------------------------------------ #
    async def run(self) -> DigestRunResult:
        now = datetime.now(timezone.utc)
        result = DigestRunResult()

        candidates = await self.get_enabled_preferences()
        logger.info(f"[Digest] {len(candidates)} user(s) with digest enabled")

        for prefs, user in candidates:
            result.checked += 1

            if not self.is_due(prefs, now):
                result.skipped_not_due += 1
                continue

            try:
                digest = await self.build_digest(user, prefs, now)

                if digest is None:
                    # Nothing to report. Still advance the clock so we don't
                    # re-check this user every single run.
                    prefs.digest_last_sent_at = now
                    result.skipped_empty += 1
                    await self.db.commit()
                    continue

                await self.send_digest(user, prefs, digest, now)
                await self.db.commit()
                result.sent += 1

            except Exception as exc:  # noqa: BLE001 - isolate per-user failures
                await self.db.rollback()
                result.errors += 1
                result.error_user_ids.append(str(user.id))
                logger.error(
                    f"[Digest] Failed for user {user.id}: {exc}",
                    exc_info=True,
                )

        logger.info(f"[Digest] Run complete: {result.as_dict()}")
        return result


async def run_digest_task() -> dict:
    """Scheduler entry point (see src/tasks/scheduled_tasks.py)."""
    async with get_async_db_context() as db:
        service = DigestService(db)
        result = await service.run()
        return result.as_dict()


if __name__ == "__main__":
    import asyncio

    print(asyncio.run(run_digest_task()))
