from datetime import datetime, timezone
from uuid import UUID
from typing import Dict, Any, Optional
from src.api.schema.content_schema import ContentProgressResponse
from src.flow.service.utils import get_progress_percent

class RunManager:
    """
    Manager for running LangGraph assistants and handling streaming progress.

    Responsibilities:
        - Start LangGraph flows asynchronously.
        - Stream progress updates from flows and persist them.
        - Run flows and wait for completion.
        - Cancel running flows.
    
    Expects:
        - `self.get_client()` method to provide a LangGraph client instance.
        - `self.update_content_progress(content_id, progress_payload)` method
          to persist progress updates (e.g., from ProgressManager).
    """
    # Background runner
    async def run_assistant(
        self,
        assistant_id: str,
        input_payload: Dict[str, Any],
        thread_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Start a LangGraph assistant asynchronously without waiting for completion.

        Args:
            assistant_id: The ID of the assistant to run.
            input_payload: Input dictionary to pass to the assistant.
            thread_id: Optional thread ID for the run.
            metadata: Optional metadata dictionary.

        Returns:
            Dict containing the initial response from LangGraph for the run.
        """
        client = await self.get_client()
        run_req = {"assistant_id": assistant_id, "input": input_payload, "thread_id": thread_id}
        if metadata:
            run_req["metadata"] = metadata
        return await self.safe_call(client.runs.create(**run_req), "run_assistant")
    

    async def run_assistant_stream(
            self, 
            assistant_id, 
            input_payload, 
            thread_id=None, 
            metadata=None
    ):
        """
        Stream updates from a running LangGraph assistant.

        Streams updates in real-time and persists progress for each stage.
        Expects `input_payload["request_payload"]["content_id"]` to be present.

        Args:
            assistant_id: The ID of the assistant to stream.
            input_payload: Input dictionary to pass to the assistant.
            thread_id: Optional thread ID for the run.
            metadata: Optional metadata dictionary.

        Yields:
            Tuple (mode, chunk) where `mode` is the stream mode
            (e.g., "updates") and `chunk` contains stage data.
        """
        client = await self.get_client()
        stream_args = {
            "assistant_id": assistant_id,
            "input": input_payload,
            "thread_id": thread_id,
            "stream_mode": ["updates"],
        }
        if metadata:
            stream_args["metadata"] = metadata

        async for mode, chunk in client.runs.stream(**stream_args):
            if isinstance(mode, str) and mode.lower() == "updates" and isinstance(chunk, dict):
                for stage, value in chunk.items():
                    progress_payload = ContentProgressResponse(
                        content_id=UUID(input_payload["request_payload"]["content_id"]),
                        current_step=stage,
                        progress_percent=get_progress_percent(stage),
                        status_message=f"{stage} running",
                        started_at=datetime.now(timezone.utc),
                        step_details=value,
                    )
                    await self.update_content_progress(progress_payload.content_id, progress_payload)
            yield mode, chunk


    async def run_assistant_and_wait(
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
