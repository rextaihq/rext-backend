"""Unit / integration tests for DigestService (email activity digest)."""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.models.notification.notification_model import Notification
from src.api.models.user_models.notification_preferences import NotificationPreferences
from src.api.models.user_models.users import Users
from src.services.digest_service import DigestService


def _prefs(**kw) -> NotificationPreferences:
    base = dict(
        user_id=uuid.uuid4(),
        digest_enabled=True,
        email_notifications=True,
        digest_frequency="daily",
        digest_last_sent_at=None,
    )
    base.update(kw)
    return NotificationPreferences(**base)


class TestIsDue:
    def _now(self):
        return datetime(2026, 8, 28, 8, 0, tzinfo=timezone.utc)

    def test_first_ever_digest_is_due(self):
        assert DigestService.is_due(_prefs(digest_last_sent_at=None), self._now())

    def test_disabled_is_never_due(self):
        assert not DigestService.is_due(_prefs(digest_enabled=False), self._now())

    def test_email_master_switch_off_is_never_due(self):
        assert not DigestService.is_due(_prefs(email_notifications=False), self._now())

    def test_daily_not_due_after_2_hours(self):
        prefs = _prefs(digest_last_sent_at=self._now() - timedelta(hours=2))
        assert not DigestService.is_due(prefs, self._now())

    def test_daily_due_after_a_day(self):
        prefs = _prefs(digest_last_sent_at=self._now() - timedelta(hours=25))
        assert DigestService.is_due(prefs, self._now())

    def test_weekly_not_due_after_2_days(self):
        prefs = _prefs(
            digest_frequency="weekly",
            digest_last_sent_at=self._now() - timedelta(days=2),
        )
        assert not DigestService.is_due(prefs, self._now())

    def test_weekly_due_after_7_days(self):
        prefs = _prefs(
            digest_frequency="weekly",
            digest_last_sent_at=self._now() - timedelta(days=7),
        )
        assert DigestService.is_due(prefs, self._now())

    def test_naive_last_sent_is_treated_as_utc(self):
        prefs = _prefs(digest_last_sent_at=datetime(2026, 8, 20, 8, 0))  # naive, 8 days ago
        assert DigestService.is_due(prefs, self._now())


@pytest.mark.asyncio
class TestBuildAndSend:
    async def _make_user(self, db, verified=True, status="active"):
        user = Users(
            id=uuid.uuid4(),
            email=f"digest_{uuid.uuid4().hex[:8]}@example.com",
            full_name="Digest Tester",
            status=status,
            email_verified=verified,
        )
        db.add(user)
        await db.flush()
        return user

    async def test_build_digest_groups_by_type(self, db_session):
        now = datetime.now(timezone.utc)
        user = await self._make_user(db_session)
        prefs = _prefs(user_id=user.id, digest_last_sent_at=now - timedelta(hours=12))
        db_session.add(prefs)

        for i in range(3):
            db_session.add(Notification(
                id=uuid.uuid4(), user_id=user.id, title=f"Content {i}",
                message="A piece of content finished", type="content",
                created_at=now - timedelta(hours=1),
            ))
        db_session.add(Notification(
            id=uuid.uuid4(), user_id=user.id, title="Payment received",
            message="Your invoice was paid", type="billing",
            created_at=now - timedelta(hours=2),
        ))
        # Outside the window - must be excluded
        db_session.add(Notification(
            id=uuid.uuid4(), user_id=user.id, title="Old news",
            message="stale", type="content", created_at=now - timedelta(days=5),
        ))
        await db_session.flush()

        digest = await DigestService(db_session).build_digest(user, prefs, now)

        assert digest is not None
        assert digest["total_count"] == 4
        titles = {s["title"]: s["count"] for s in digest["sections"]}
        assert titles == {"Content": 3, "Billing & payments": 1}
        content_section = next(s for s in digest["sections"] if s["title"] == "Content")
        assert len(content_section["items"]) == 3
        assert content_section["items"][0]["title"].startswith("Content")

    async def test_build_digest_none_when_no_activity(self, db_session):
        now = datetime.now(timezone.utc)
        user = await self._make_user(db_session)
        prefs = _prefs(user_id=user.id, digest_last_sent_at=now - timedelta(hours=12))
        db_session.add(prefs)
        await db_session.flush()

        assert await DigestService(db_session).build_digest(user, prefs, now) is None

    async def test_get_enabled_preferences_filters(self, db_session):
        now = datetime.now(timezone.utc)
        u_on = await self._make_user(db_session)
        u_off = await self._make_user(db_session)
        u_master_off = await self._make_user(db_session)
        u_unverified = await self._make_user(db_session, verified=False)

        db_session.add_all([
            _prefs(user_id=u_on.id, digest_enabled=True),
            _prefs(user_id=u_off.id, digest_enabled=False),
            _prefs(user_id=u_master_off.id, digest_enabled=True, email_notifications=False),
            _prefs(user_id=u_unverified.id, digest_enabled=True),
        ])
        await db_session.flush()

        pairs = await DigestService(db_session).get_enabled_preferences()
        returned_ids = {u.id for _, u in pairs}

        assert u_on.id in returned_ids
        assert u_off.id not in returned_ids
        assert u_master_off.id not in returned_ids
        assert u_unverified.id not in returned_ids

    async def test_send_digest_stamps_and_calls_email(self, db_session):
        now = datetime.now(timezone.utc)
        user = await self._make_user(db_session)
        prefs = _prefs(user_id=user.id)
        db_session.add(prefs)
        await db_session.flush()

        service = DigestService(db_session)
        service.email_service.send_email = AsyncMock(
            return_value=SimpleNamespace(id=uuid.uuid4(), status="sent")
        )

        digest = {
            "frequency": "daily",
            "period_label": "Daily",
            "period_range": "Aug 27 – Aug 28, 2026",
            "total_count": 2,
            "sections": [{"title": "Content", "count": 2, "items": [
                {"title": "X", "message": "y", "when": "Aug 28, 09:00 UTC"},
            ]}],
        }

        ok = await service.send_digest(user, prefs, digest, now)

        assert ok is True
        assert prefs.digest_last_sent_at == now
        kwargs = service.email_service.send_email.call_args.kwargs
        assert kwargs["template_type"] == "digest"
        assert kwargs["to"] == user.email
        assert kwargs["tags"]["frequency"] == "daily"
        assert "digest" in kwargs["subject"].lower()


@pytest.mark.asyncio
class TestRunOrchestration:
    async def _service_with_mock_db(self):
        db = AsyncMock()
        service = DigestService(db)
        return service, db

    async def test_run_sends_when_due_with_activity(self):
        service, db = await self._service_with_mock_db()
        now_user = Users(id=uuid.uuid4(), email="a@example.com", email_verified=True)
        prefs = _prefs(user_id=now_user.id)

        service.get_enabled_preferences = AsyncMock(return_value=[(prefs, now_user)])
        service.build_digest = AsyncMock(return_value={"total_count": 1})
        service.send_digest = AsyncMock(return_value=True)

        result = await service.run()

        assert result.sent == 1
        assert result.skipped_empty == 0
        service.send_digest.assert_awaited_once()
        db.commit.assert_awaited()

    async def test_run_skips_empty_but_advances_clock(self):
        service, db = await self._service_with_mock_db()
        user = Users(id=uuid.uuid4(), email="b@example.com", email_verified=True)
        prefs = _prefs(user_id=user.id)

        service.get_enabled_preferences = AsyncMock(return_value=[(prefs, user)])
        service.build_digest = AsyncMock(return_value=None)
        service.send_digest = AsyncMock()

        result = await service.run()

        assert result.sent == 0
        assert result.skipped_empty == 1
        service.send_digest.assert_not_awaited()
        assert prefs.digest_last_sent_at is not None
        db.commit.assert_awaited()

    async def test_run_skips_not_due(self):
        service, db = await self._service_with_mock_db()
        user = Users(id=uuid.uuid4(), email="c@example.com", email_verified=True)
        prefs = _prefs(user_id=user.id, digest_last_sent_at=datetime.now(timezone.utc))

        service.get_enabled_preferences = AsyncMock(return_value=[(prefs, user)])
        service.build_digest = AsyncMock()
        service.send_digest = AsyncMock()

        result = await service.run()

        assert result.skipped_not_due == 1
        assert result.sent == 0
        service.build_digest.assert_not_awaited()

    async def test_run_isolates_per_user_errors(self):
        service, db = await self._service_with_mock_db()
        u1 = Users(id=uuid.uuid4(), email="d@example.com", email_verified=True)
        u2 = Users(id=uuid.uuid4(), email="e@example.com", email_verified=True)
        p1, p2 = _prefs(user_id=u1.id), _prefs(user_id=u2.id)

        service.get_enabled_preferences = AsyncMock(return_value=[(p1, u1), (p2, u2)])
        service.build_digest = AsyncMock(side_effect=[RuntimeError("boom"), {"total_count": 1}])
        service.send_digest = AsyncMock(return_value=True)

        result = await service.run()

        assert result.errors == 1
        assert result.sent == 1
        assert str(u1.id) in result.error_user_ids
        db.rollback.assert_awaited()
