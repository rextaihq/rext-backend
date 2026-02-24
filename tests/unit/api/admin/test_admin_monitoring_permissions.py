import sys
import os
import asyncio
from unittest.mock import MagicMock, patch
from uuid import uuid4

# Add src to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../../")))

from src.services.monitoring_service import MonitoringService

async def test_resolve_error_log_service_write():
    """
    Verify that MonitoringService.resolve_error_log correctly updates the log status.
    This confirms the logic that the 'audit.write' permission protects.
    """
    db = MagicMock()
    log_id = uuid4()
    admin_id = uuid4()
    
    # Mock the log object
    mock_log = MagicMock()
    mock_log.resolved = False
    
    # Create service
    service = MonitoringService(db)
    
    # Define an async side effect for the internal helper
    async def mock_get_log(*args, **kwargs):
        return mock_log
        
    with patch.object(service, '_get_error_log_by_id', side_effect=mock_get_log):
        # Resolve error log
        await service.resolve_error_log(log_id, admin_id)
        
        # Assertions
        assert mock_log.resolved is True
        assert mock_log.resolved_by == admin_id
        assert mock_log.resolved_at is not None
        
    print("✅ test_resolve_error_log_service_write passed")

if __name__ == "__main__":
    async def run_tests():
        try:
            await test_resolve_error_log_service_write()
            print("\nAll Task 372 verification simulations passed! 🚀")
        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
            
    asyncio.run(run_tests())
