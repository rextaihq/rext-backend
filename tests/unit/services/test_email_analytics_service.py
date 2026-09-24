from datetime import datetime, timezone
from unittest.mock import ANY, AsyncMock, Mock, call
from uuid import uuid4

import pytest

from src.api.models.email_models.email_event import EmailEvent
from src.api.models.email_models.email_log import EmailLog
from src.services.email_analytics_service import EmailAnalyticsService


class TestEmailAnalyticsService:
    @pytest.mark.asyncio
    async def test_get_event_count_without_workspace(self):
        """Should query without join when workspace_id is not provided"""
        mock_db = AsyncMock()
        service = EmailAnalyticsService(mock_db)

        # Mock result
        mock_result = Mock()
        mock_result.scalar.return_value = 10
        mock_db.execute.return_value = mock_result

        count = await service._get_event_count(
            event_type="opened", start_date=datetime.now(timezone.utc)
        )

        assert count == 10
        mock_db.execute.assert_called_once()

        # Verify call args
        # We can't easily check SQL string without actual DB engine, but we can verify args passed

    @pytest.mark.asyncio
    async def test_get_event_count_with_workspace(self):
        """Should query with join when workspace_id is provided"""
        mock_db = AsyncMock()
        service = EmailAnalyticsService(mock_db)

        mock_result = Mock()
        mock_result.scalar.return_value = 5
        mock_db.execute.return_value = mock_result

        workspace_id = uuid4()
        count = await service._get_event_count(
            event_type="clicked", start_date=datetime.now(timezone.utc), workspace_id=workspace_id
        )

        assert count == 5
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_overview_stats_calls_helper(self):
        """Should call _get_event_count for each event type"""
        mock_db = AsyncMock()
        service = EmailAnalyticsService(mock_db)

        # Mock _get_event_count to return values
        # We rely on the method implementation not being mocked away, but here we want to verifying interaction
        # To test get_overview_stats logic, we should mock _get_event_count on the instance

        # Create service instance
        service = EmailAnalyticsService(mock_db)

        # Mock the helper method on the instance
        service._get_event_count = AsyncMock(side_effect=[100, 50, 10])

        # Mock other queries (sent, delivered, bounced)
        mock_scalar = Mock()
        mock_scalar.scalar.return_value = 1000
        mock_db.execute.return_value = mock_scalar

        stats = await service.get_overview_stats()

        assert stats["total_opened"] == 100
        assert stats["total_clicked"] == 50
        assert stats["total_complained"] == 10

        # Verify helper calls
        assert service._get_event_count.call_count == 3
        service._get_event_count.assert_has_calls(
            [call("opened", ANY, None), call("clicked", ANY, None), call("complained", ANY, None)]
        )


class TestEmailAnalyticsNoFanOut:
    """Multiple events per email must not multiply sent/delivered counts."""

    @pytest.mark.asyncio
    async def test_by_template_and_timeline_not_inflated_by_events(self, db_session):
        now = datetime.now(timezone.utc)
        tmpl = f"verification_{uuid4().hex[:8]}"

        delivered_log = EmailLog(
            id=uuid4(),
            provider="resend",
            provider_message_id=f"m1_{uuid4().hex}",
            to_email="a@example.com",
            from_email="noreply@rext.com",
            subject="s",
            template_type=tmpl,
            status="delivered",
            created_at=now,
        )
        sent_log = EmailLog(
            id=uuid4(),
            provider="resend",
            provider_message_id=f"m2_{uuid4().hex}",
            to_email="b@example.com",
            from_email="noreply@rext.com",
            subject="s",
            template_type=tmpl,
            status="sent",
            created_at=now,
        )
        db_session.add_all([delivered_log, sent_log])
        await db_session.flush()

        # 4 events on the one delivered email (would fan out sent -> 4 pre-fix)
        for i, etype in enumerate(["delivered", "opened", "opened", "clicked"]):
            db_session.add(
                EmailEvent(
                    id=uuid4(),
                    email_log_id=delivered_log.id,
                    provider="resend",
                    provider_event_id=f"evt_{uuid4().hex}",
                    provider_message_id=delivered_log.provider_message_id,
                    event_type=etype,
                    event_data={},
                    received_at=now,
                    created_at=now,
                )
            )
        await db_session.flush()

        service = EmailAnalyticsService(db_session)

        rows = await service.get_analytics_by_template(date_range="30d")
        row = next(r for r in rows if r["template_type"] == tmpl)
        assert row["sent"] == 2
        assert row["delivered"] == 1
        assert row["opened"] == 1  # distinct email, not 2 open events
        assert row["clicked"] == 1

        timeline = await service.get_timeline(period="daily", date_range="30d")
        bucket = [p for p in timeline if p["sent"] > 0]
        assert sum(p["sent"] for p in bucket) >= 2
        assert sum(p["opened"] for p in bucket) >= 1
        # opened count in any bucket never exceeds sent in that bucket
        assert all(p["opened"] <= p["sent"] for p in timeline)
        # delivered / failed are now exposed per bucket
        assert sum(p["delivered"] for p in bucket) >= 1
        assert all("failed" in p for p in timeline)
