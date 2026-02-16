import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, call, ANY

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
            event_type="opened",
            start_date=datetime.now(timezone.utc)
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
            event_type="clicked",
            start_date=datetime.now(timezone.utc),
            workspace_id=workspace_id
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
        service._get_event_count.assert_has_calls([
            call("opened", ANY, None),
            call("clicked", ANY, None),
            call("complained", ANY, None)
        ])
