from src.flow.service.base_clinet import LangGraphBaseClient
from src.flow.service.assistant_manager import AssistantManager
from src.flow.service.process_manager import ProgressManager
from src.flow.service.run_manager import RunManager
from src.flow.service.thread_manager import ThreadManager

class LangGraphService(
    LangGraphBaseClient, AssistantManager, RunManager, ThreadManager
):
    """
    Unified service for LangGraph operations.

    Combines:
        - LangGraphBaseClient: client management
        - AssistantManager: assistant CRUD
        - ProgressManager: track and persist progress
        - RunManager: run and stream flows

    Usage:
        service = LangGraphService(url, db, api_key, progress_callback)
    """

    def __init__(self, url, db, api_key=None, progress_callback=None):
        LangGraphBaseClient.__init__(self, url, api_key)
        # ProgressManager.__init__(self, db, progress_callback)

    async def close(self):
        """Close LangGraph client connection if open."""
        if self._client:
            await self._client.aclose()
