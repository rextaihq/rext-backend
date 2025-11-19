from src.flow.service.base_clinet import LangGraphRemoteGraph
from src.flow.service.assistant_manager import AssistantManager
from src.flow.service.run_manager import RunManager
from src.flow.service.thread_manager import ThreadManager


class LangGraphService(AssistantManager):
    def __init__(self, url, db, api_key=None, progress_callback=None, assistant_id=None):
        super().__init__(url=url, assistant_id=assistant_id, name="WREXT", api_key=api_key)
        self.run_manager = RunManager(url=url, assistant_id=self.assistant_id,name="WREXT",api_key=api_key)

        self.thread_manager = ThreadManager(url, assistant_id=assistant_id, name="WREXT", api_key=api_key)
        self.progress_callback = progress_callback


    async def close(self):
        """Close LangGraph client connection if open."""
        if getattr(self, "_client", None):
            await self._client.aclose()
