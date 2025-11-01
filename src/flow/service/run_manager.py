from datetime import datetime, timezone
from uuid import UUID
from typing import Dict, Any, Optional
from src.flow.service.utils import get_progress_percent
from src.flow.states.content_state import ContentState
from src.flow.service.process_manager import ProgressManager
from src.utils.logger import logger

class RunManager(ProgressManager):
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
    async def create_content(
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
    

    async def stream_content(
            self, 
            assistant_id, 
            input_payload:ContentState, 
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

        logger.info(
            f"Starting to stream content generation for assistant {assistant_id}",
            extra={"assistant_id": assistant_id, "thread_id": thread_id}
        )
        # initalizing progress tracking
        self.initialize_progress(
            content_id=UUID(input_payload["request_payload"]["content_id"]),
            step="initializing"
        )
        logger.info(
            f"Initialized progress tracking for content {input_payload['request_payload']['content_id']}",
            extra={"content_id": input_payload["request_payload"]["content_id"]}
        )

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
                    await self.update_progress(
                        content_id=UUID(input_payload["request_payload"]["content_id"]),
                        step=stage,
                        step_details=value,
                        message=f"Stage '{stage}' in progress"
                    )
            yield mode, chunk


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
