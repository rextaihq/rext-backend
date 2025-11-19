from datetime import datetime, timezone
from typing import Dict, Any, Optional
from src.flow.states.content_state import ContentState
from src.flow.service.base_clinet import LangGraphRemoteGraph
from langchain_core.runnables.config import RunnableConfig
from src.services.sse_service import (
    emit_step_start,
    emit_step_progress,
    emit_step_success,
    emit_step_failure,
    emit_pipeline_complete,
)
from src.utils.logger import logger


class RunManager(LangGraphRemoteGraph):
    """
    Manager for running LangGraph assistants and handling streaming progress.

    Responsibilities:
        - Start LangGraph flows asynchronously.
        - Stream progress updates from flows and persist them.
        - Run flows and wait for completion.
        - Cancel running flows.
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

    def __init__(self, url: str, assistant_id: str, name: str = "WREXT", api_key: Optional[str] = None):
        super().__init__(url, assistant_id, name, api_key)
        self.url = url
        self.api_key = api_key

    # -------------------- Content Creation -------------------- #
    async def create_content(
        self,
        input_payload: Dict[str, Any],
        thread_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Start a LangGraph assistant asynchronously without waiting for completion.
        """
        client = await self._get_client()
        run_req = {"input": input_payload, "thread_id": thread_id}
        if metadata:
            run_req["metadata"] = metadata

        return await self.safe_call(client.runs.create(**run_req), "run_assistant")

    # -------------------- Streaming -------------------- #
    async def stream_content(
        self,
        input_payload: ContentState,
        thread_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Stream updates from a running LangGraph assistant.

        Yields:
            Tuple (mode, chunk) where `mode` is the stream mode and `chunk` contains stage data.
        """
        graph = await self.get_remote_graph()
        operation_id = input_payload["content_id"]
        scope = "content"

        # Notify frontend: generation started
        await emit_step_start(
            operation_id=operation_id,
            scope=scope,
            step="generation_started",
            message="Content generation process initiated.",
            progress=0,
        )

        config = RunnableConfig(thread_id=thread_id) if thread_id else None

        try:
            async for mode, chunk in graph.astream(
                input={"request_payload": input_payload},
                config=config,
                stream_mode=["updates"]
            ):
                logger.info(f"Stream chunk: mode={mode}, chunk={chunk}")
                yield mode, chunk

                if mode == "updates" and chunk:
                    # Extract node name from chunk key
                    node = list(chunk.keys())[0]
                    step_info = self.PROGRESS_STEPS.get(node, {"percent": 0, "message": f"Processing {node}..."})
                    progress = step_info["percent"]
                    message = step_info["message"]

                    # Emit progress update
                    await emit_step_progress(
                        operation_id=operation_id,
                        scope=scope,
                        step=node,
                        message=message,
                        progress=progress,
                    )

                    # Emit step success if node is completed
                    if node == "completed":
                        await emit_step_success(
                            operation_id=operation_id,
                            scope=scope,
                            step=node,
                            message=message,
                            progress=progress,
                        )

            # Emit pipeline completion
            await emit_pipeline_complete(
                operation_id=operation_id,
                scope=scope,
                message="Content generation pipeline completed successfully.",
            )

        except Exception as e:
            logger.error(f"Error during LangGraph streaming: {e}")
            await emit_step_failure(
                operation_id=operation_id,
                scope=scope,
                step="content_generation",
                message=str(e),
            )

    # -------------------- Run & Wait -------------------- #
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

    # -------------------- Cancel Run -------------------- #
    async def cancel_run(self, run_id: str) -> Any:
        """Cancel a running assistant by run_id."""
        client = await self.get_client()
        return await client.runs.cancel(run_id=run_id)