import asyncio
from langgraph.pregel.remote import RemoteGraph

async def main():
    url = "http://127.0.0.1:2024"

    # Using assistant ID (recommended)
    assistant_id = "77a13d9e-8bc2-4b4e-9878-f5b398728a01"
    remote_graph = RemoteGraph(assistant_id, url=url,api_key="",name="WREXT")

    # Stream results asynchronously
    async for mode, chunk in remote_graph.astream(
        {
            "input": {
                "request_payload": {
                    "title": "Ai Revolution in 2025",
                    "content_language": "English",
                    "status": "draft",
                    "workspace_id": "53332afc-8c91-48ad-9ee1-5c1736ef7a99",
                    "topic_id": "614203bf-cd0e-4ca5-b185-bf5299e62e7e",
                    "body_markdown": "",
                    "content_format": "Markdown",
                    "assigned_to_user_id": "0bf5d5e9-0520-41a1-aa73-6cd790d204a2",
                    "metadata": {
                        "content_summary": "",
                        "content_type": "",
                        "target_platform": "",
                        "target_industry": "",
                        "target_audience": [""],
                        "audience_size": "",
                        "complexity_level": "",
                        "content_tone": [""],
                        "target_region": "",
                        "content_objectives": [""],
                        "source_references": [""],
                        "content_word_count": 1,
                        "reading_time_minutes": 1,
                        "content_quality_scores": {"propertyName*": "anything"},
                        "featured_image_prompt": "",
                        "featured_image_alt_text": "",
                    },
                    "seo_data": {
                        "content_primary_keywords": [""],
                        "content_secondary_keywords": [""],
                        "content_meta_description": "",
                        "content_search_intent": [""],
                        "content_seo_score": 0,
                        "content_readability_score": 0,
                    },
                }
            }
        },
        stream_mode=["updates"]
    ):
        print(f"Stream chunk received: mode={mode}, chunk={chunk}")
            # if mode == "updates":
            #     logger.info(f"Nodes......[update] {chunk}")
           
            # else:
            #     logger.debug(f"Debugging.............[{mode}] {chunk}")


# Run the async function
if __name__ == "__main__":
    asyncio.run(main())




#  RUn TEsting
from datetime import datetime, timezone
from uuid import UUID
from typing import Dict, Any, Optional
from src.flow.service.utils import get_progress_percent
from src.flow.states.content_state import ContentState
from sqlalchemy.ext.asyncio import AsyncSession
from src.flow.service.process_manager import ProgressManager
from src.flow.service.base_clinet import LangGraphRemoteGraph
from src.flow.service.assistant_manager import AssistantManager
from langchain_core.runnables.config import RunnableConfig

from src.utils.logger import logger

# ------------------------------
# RunManager
# ------------------------------
class RunManager(LangGraphRemoteGraph, ProgressManager):
    """
    Manager for running LangGraph assistants and streaming frontend progress updates.
    """

    def __init__(self, db: AsyncSession, url: str, assistant_id: Optional[str] = None, name: str = "WREXT", api_key: Optional[str] = None):
        LangGraphRemoteGraph.__init__(self, url, assistant_id or "", name, api_key)
        ProgressManager.__init__(self, db)
        self.db = db

    async def create_content(self, input_payload: Dict[str, Any], thread_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        client = await self.get_client()
        run_req = {"input": input_payload, "thread_id": thread_id}
        if metadata:
            run_req["metadata"] = metadata
        return await self.safe_call(client.runs.create(**run_req), "run_assistant")

    async def stream_content(self,input_payload: Dict[str, Any], thread_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        graph = await self.get_remote_graph()

        content_id = input_payload.get("content_id")
        await self.initialize_progress(content_id)

        try:
            config = RunnableConfig(thread_id=thread_id) if thread_id else None
            async for mode, chunk in graph.astream(
                input={"request_payload": input_payload},
                config=config,
                stream_mode=["updates"]
            ):
                node = chunk.get("data", {}).get("node", "unknown")
                status = chunk.get("status", "in_progress")

                # Frontend-only progress update
                await self.update_progress(
                    content_id=content_id,
                    step=node,
                    message=chunk.get("message"),
                    step_details=chunk
                )

                yield mode, chunk

                if status == "completed":
                    await self.mark_completed(content_id)
                elif status == "failed":
                    await self.mark_failed(content_id, error_message=chunk.get("message", "Failed"))

        except Exception as e:
            logger.error(f"Error streaming content {content_id}: {e}")
            await self.mark_failed(content_id, error_message=str(e))
            

    async def create_content_and_wait(
        self,
        assistant_id: str,
        input_payload: Dict[str, Any],
        thread_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Run a LangGraph assistant and wait for final completion.

        Args:
            assistant_id: ID of the assistant to run.
            input_payload: Input dictionary for the assistant.
            thread_id: Optional thread ID for the run.
            metadata: Optional metadata dictionary.
            **kwargs: Additional keyword arguments passed to the SDK `wait` method.

        Returns:
            Dict containing the final result from LangGraph after completion.
        """
        client = await self.get_client()
        return await self.safe_call(
            client.runs.wait(
                assistant_id=assistant_id,
                thread_id=thread_id,
                input=input_payload,
                metadata=metadata or {},
                **kwargs
            ),
            "run_assistant_and_wait",
        )
    

    async def cancel_run(self, run_id: str) -> Any:
        """
        Cancel a running assistant by run_id.
        """
        client = await self.get_client()
        return await client.runs.cancel(run_id=run_id)


#  Process esting
from datetime import datetime, timezone
from uuid import UUID
from typing import Dict, Any, Optional
from src.flow.service.base_clinet import LangGraphRemoteGraph
from src.services.sse_service import (
    emit_step_start,
    emit_step_progress,
    emit_step_success,
    emit_step_failure,
    emit_pipeline_complete,
    event_stream_manager,
)
from src.api.models.content_models.content_progress import ContentProgress
from src.api.models.content_models.content import Content
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.utils.logger import logger
from langchain_core.runnables.config import RunnableConfig

# ------------------------------
# ProgressManager (Frontend-only)
# ------------------------------
class ProgressManager:
    """
    Manager for handling content progress for frontend updates (no DB updates on intermediate steps).
    """

    PROGRESS_STEPS = {
        "initializing": {"percent": 0, "message": "Initializing content generation..."},
        "FetchUser": {"percent": 10, "message": "Fetching user information..."},
        "FetchWorkspace": {"percent": 15, "message": "Loading workspace details..."},
        "FetchTopic": {"percent": 20, "message": "Retrieving topic information..."},
        "WebContext": {"percent": 30, "message": "Searching web for relevant context..."},
        "KnowledgeContext": {"percent": 40, "message": "Retrieving workspace knowledge..."},
        "ScrapeContent": {"percent": 50, "message": "Scraping and processing sources..."},
        "RerankContent": {"percent": 60, "message": "Ranking content by relevance..."},
        "BlogGeneration": {"percent": 75, "message": "Generating content with AI..."},
        "SaveContent": {"percent": 95, "message": "Saving generated content..."},
        "completed": {"percent": 100, "message": "Content generation completed!"},
        "failed": {"percent": -1, "message": "Content generation failed"}
    }

    def __init__(self, db: AsyncSession):
        self.db = db

    async def initialize_progress(self, content_id: UUID, step: str = "initializing"):
        """Emit initial frontend event only"""
        step_info = self.PROGRESS_STEPS.get(step, {"percent": 0, "message": "Starting..."})
        await emit_step_start(
            operation_id=str(content_id),
            scope="content_generation",
            step=step,
            message=step_info["message"],
            progress=step_info["percent"]
        )

    async def update_progress(self, content_id: UUID, step: str, message: Optional[str] = None, step_details: Optional[Dict[str, Any]] = None):
        """Emit frontend-only progress events (no DB update)"""
        step_info = self.PROGRESS_STEPS.get(step, {"percent": 0, "message": "Processing..."})
        progress_percent = step_info["percent"]
        status_message = message or step_info["message"]

        await emit_step_progress(
            operation_id=str(content_id),
            scope="content_generation",
            step=step,
            message=status_message,
            progress=progress_percent,
            payload=step_details or {}
        )

        # Emit success/failure events if completed/failed
        if progress_percent == 100:
            await emit_step_success(
                operation_id=str(content_id),
                scope="content_generation",
                step=step,
                message=status_message,
                progress=progress_percent
            )
        elif progress_percent < 0:
            await emit_step_failure(
                operation_id=str(content_id),
                scope="content_generation",
                step=step,
                message=status_message
            )

    async def mark_completed(self, content_id: UUID):
        """Mark the pipeline completed (DB can optionally be updated here)"""
        await self.update_progress(content_id, "completed")
        await emit_pipeline_complete(
            operation_id=str(content_id),
            scope="content_generation",
            message="Content generation pipeline completed successfully."
        )
        await event_stream_manager.complete(str(content_id))

    async def mark_failed(self, content_id: UUID, error_message: str):
        """Mark the pipeline failed (DB can optionally be updated here)"""
        await self.update_progress(content_id, "failed", message=error_message)
        # Optional: update DB content status
        result = await self.db.execute(select(Content).where(Content.id == content_id))
        content = result.scalar_one_or_none()
        if content:
            content.status = "failed"
            content.updated_at = datetime.now(timezone.utc)
            await self.db.flush()
        await event_stream_manager.complete(str(content_id))