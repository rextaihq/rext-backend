from __future__ import annotations

import asyncio
from asyncio import Queue
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Deque, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from src.utils.logger import logger


def _utcnow() -> datetime:
    """Return the current UTC time."""
    return datetime.now(timezone.utc)


@dataclass
class _Subscription:
    """Metadata for an active SSE subscriber."""

    operation_id: str
    user_id: UUID
    queue: Queue[Optional[str]]
    last_activity: datetime = field(default_factory=_utcnow)


@dataclass
class _OperationState:
    """Holds subscriber state and pending events for an operation."""

    subscribers: List[_Subscription] = field(default_factory=list)
    pending_events: Deque[str] = field(default_factory=deque)
    created_at: datetime = field(default_factory=_utcnow)
    last_event_at: datetime = field(default_factory=_utcnow)
    completed: bool = False
    completion_payload: Optional[Dict[str, Any]] = None


class OperationEvent(BaseModel):
    """Schema representing a single SSE payload."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    operation_id: str
    scope: str
    step: str
    status: str
    message: str
    progress: Optional[int] = None
    payload: Optional[Dict[str, object]] = None
    timestamp: str = Field(default_factory=lambda: _utcnow().isoformat())


class EventStreamManager:
    """
    Manage Server-Sent Event subscriptions and dispatch.

    Responsibilities:
    - Maintain per-operation subscriber queues
    - Buffer recent events for late subscribers
    - Format events according to SSE spec (id/event/data)
    - Clean up completed or stale operations
    """

    def __init__(
        self,
        *,
        cleanup_interval_seconds: float = 300.0,
        stale_after_seconds: float = 300.0,
        pending_event_limit: int = 50,
    ) -> None:
        self._cleanup_interval = cleanup_interval_seconds
        self._stale_after = timedelta(seconds=stale_after_seconds)
        self._pending_event_limit = max(1, pending_event_limit)
        self._operations: Dict[str, _OperationState] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task[None]] = None

    async def subscribe(self, operation_id: str, user_id: UUID) -> AsyncIterator[str]:
        """
        Subscribe to an operation's event stream.

        Yields formatted SSE strings until the stream completes or the client disconnects.
        """
        queue: Queue[Optional[str]] = asyncio.Queue()
        subscription = _Subscription(
            operation_id=operation_id,
            user_id=user_id,
            queue=queue,
        )

        async with self._lock:
            state = self._operations.get(operation_id)
            if state is None:
                state = _OperationState()
                self._operations[operation_id] = state
            state.subscribers.append(subscription)
            pending_events = list(state.pending_events)

        self._ensure_cleanup_task()

        connection_event = OperationEvent(
            operation_id=operation_id,
            scope="connection",
            step="connected",
            status="connected",
            message="SSE connection established",
        )

        await queue.put(self._format_event(connection_event))

        for event_text in pending_events:
            await queue.put(event_text)

        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            await self._remove_subscription(operation_id, subscription)

    async def publish(self, event: OperationEvent) -> None:
        """Publish an event to all subscribers and buffer it for future subscribers."""
        operation_id = event.operation_id
        formatted = self._format_event(event)
        subscribers: List[_Subscription] = []

        async with self._lock:
            state = self._operations.get(operation_id)
            if state is None:
                state = _OperationState()
                self._operations[operation_id] = state

            state.last_event_at = _utcnow()
            state.pending_events.append(formatted)
            while len(state.pending_events) > self._pending_event_limit:
                state.pending_events.popleft()

            # Store completion payload if this is a terminal event
            if event.step == "pipeline.completed":
                state.completion_payload = event.payload

            subscribers = list(state.subscribers)

        if not subscribers:
            logger.debug(
                "Buffered event for operation %s (no active subscribers)",
                operation_id,
            )
            return

        await asyncio.gather(
            *(self._enqueue_event(subscriber, formatted) for subscriber in subscribers),
            return_exceptions=True,
        )

    async def complete(self, operation_id: str) -> None:
        """
        Mark an operation as complete and close subscriber streams.

        Queues receive a sentinel value that terminates the async generator.
        """
        subscribers: List[_Subscription] = []

        async with self._lock:
            state = self._operations.get(operation_id)
            if state is None:
                return

            state.completed = True
            subscribers = list(state.subscribers)

        for subscription in subscribers:
            await subscription.queue.put(None)

    async def drop_operation(self, operation_id: str) -> None:
        """Remove an operation and all buffered events."""
        async with self._lock:
            if operation_id in self._operations:
                del self._operations[operation_id]
                logger.debug("Dropped operation %s from event manager", operation_id)

    async def cleanup_stale_operations(self) -> None:
        """Remove operations that have no subscribers and are stale or completed."""
        now = _utcnow()
        async with self._lock:
            stale_ids = [
                op_id
                for op_id, state in list(self._operations.items())
                if not state.subscribers
                and (state.completed or now - state.last_event_at >= self._stale_after)
            ]
            for op_id in stale_ids:
                del self._operations[op_id]
                logger.debug("Cleaned up stale operation %s", op_id)

    async def active_operation_ids(self) -> List[str]:
        """Return active operation identifiers (intended for diagnostics/tests)."""
        async with self._lock:
            return list(self._operations.keys())

    async def is_operation_completed(self, operation_id: str) -> bool:
        """Check if an operation has been marked as completed."""
        async with self._lock:
            state = self._operations.get(operation_id)
            return state.completed if state else False

    async def subscribe_completed(self, operation_id: str, user_id: UUID) -> AsyncIterator[str]:
        """
        Subscribe to an already completed operation.
        Immediately sends a completion event and closes.
        """
        # Get the stored completion payload
        payload = None
        async with self._lock:
            state = self._operations.get(operation_id)
            if state:
                payload = state.completion_payload

        # Send connection event
        connection_event = OperationEvent(
            operation_id=operation_id,
            scope="connection",
            step="connected",
            status="connected",
            message="SSE connection established (operation completed)",
        )
        yield self._format_event(connection_event)

        # Send completion event with original payload
        completion_event = OperationEvent(
            operation_id=operation_id,
            scope="workspace",
            step="pipeline.completed",
            status="completed",
            message="Operation already completed",
            progress=100,
            payload=payload,
        )
        yield self._format_event(completion_event)

        # End the stream
        return

    async def shutdown(self) -> None:
        """Cancel the background cleanup task, if running."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    def _ensure_cleanup_task(self) -> None:
        if self._cleanup_interval <= 0:
            return

        if self._cleanup_task and not self._cleanup_task.done():
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop (e.g., during import-time execution)
            return

        self._cleanup_task = loop.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        """Periodically purge stale operations."""
        try:
            while True:
                await asyncio.sleep(self._cleanup_interval)
                await self.cleanup_stale_operations()
        except asyncio.CancelledError:
            logger.debug("EventStreamManager cleanup task cancelled")
            raise

    async def _remove_subscription(
        self,
        operation_id: str,
        subscription: _Subscription,
    ) -> None:
        async with self._lock:
            state = self._operations.get(operation_id)
            if state is None:
                return

            if subscription in state.subscribers:
                state.subscribers.remove(subscription)

            if not state.subscribers and state.completed:
                del self._operations[operation_id]
                logger.debug(
                    "Removed completed operation %s after last subscriber disconnected",
                    operation_id,
                )

    async def _enqueue_event(self, subscription: _Subscription, event_text: str) -> None:
        try:
            await subscription.queue.put(event_text)
            subscription.last_activity = _utcnow()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning(
                "Failed to enqueue event for operation %s: %s",
                subscription.operation_id,
                exc,
            )

    def _format_event(self, event: OperationEvent) -> str:
        """Return an SSE-compliant string with id/event/data fields."""
        event_name = f"{event.scope}.{event.step}"
        payload = event.model_dump_json()
        return f"id: {event.id}\nevent: {event_name}\ndata: {payload}\n\n"


event_stream_manager = EventStreamManager()


async def emit_step_start(
    *,
    operation_id: str,
    scope: str,
    step: str,
    message: str,
    progress: Optional[int] = None,
) -> None:
    """Emit an event indicating that a pipeline step has started."""
    await event_stream_manager.publish(
        OperationEvent(
            operation_id=operation_id,
            scope=scope,
            step=f"{step}.started",
            status="started",
            message=message,
            progress=progress,
        )
    )


async def emit_step_progress(
    *,
    operation_id: str,
    scope: str,
    step: str,
    message: str,
    progress: int,
    payload: Optional[Dict[str, object]] = None,
) -> None:
    """Emit an event describing progress within a pipeline step."""
    await event_stream_manager.publish(
        OperationEvent(
            operation_id=operation_id,
            scope=scope,
            step=step,
            status="progress",
            message=message,
            progress=progress,
            payload=payload,
        )
    )


async def emit_step_success(
    *,
    operation_id: str,
    scope: str,
    step: str,
    message: str,
    payload: Optional[Dict[str, object]] = None,
    progress: Optional[int] = None,
) -> None:
    """Emit an event when a pipeline step completes successfully."""
    await event_stream_manager.publish(
        OperationEvent(
            operation_id=operation_id,
            scope=scope,
            step=f"{step}.completed",
            status="completed",
            message=message,
            payload=payload,
            progress=progress,
        )
    )


async def emit_step_failure(
    *,
    operation_id: str,
    scope: str,
    step: str,
    message: str,
    error: Optional[str] = None,
) -> None:
    """Emit an event when a pipeline step fails."""
    payload = {"error": error} if error else None
    await event_stream_manager.publish(
        OperationEvent(
            operation_id=operation_id,
            scope=scope,
            step=f"{step}.failed",
            status="failed",
            message=message,
            payload=payload,
        )
    )


async def emit_pipeline_complete(
    *,
    operation_id: str,
    scope: str,
    message: str,
    payload: Optional[Dict[str, object]] = None,
) -> None:
    """Emit a final event for a pipeline and close the subscriber streams."""
    await event_stream_manager.publish(
        OperationEvent(
            operation_id=operation_id,
            scope=scope,
            step="pipeline.completed",
            status="completed",
            message=message,
            payload=payload,
            progress=100,
        )
    )
    await event_stream_manager.complete(operation_id)

