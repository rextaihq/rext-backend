from __future__ import annotations

import asyncio
import re
from asyncio import Queue
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, AsyncIterator, Deque, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from src.utils.logger import logger

class OperationOwnershipError(Exception):
    """Raised when a user attempts to publish to an operation they do not own."""

    def __init__(self, operation_id: str, user_id: UUID) -> None:
        self.operation_id = operation_id
        self.user_id = user_id
        super().__init__(
            f"User {user_id} is not authorized to publish to operation {operation_id}"
        )

def _utcnow() -> datetime:
    """Return the current UTC time."""
    return datetime.now(timezone.utc)


# Matches plain UUIDs and prefixed UUIDs (e.g., "user-notifications-<uuid>")
# Allows lowercase alphanumeric characters and hyphens, 1-100 chars
OPERATION_ID_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9\-]{0,98}[a-z0-9])?$")


def validate_operation_id(operation_id: str) -> None:
    """
    Validate that the operation_id matches the expected format.
    Raises ValueError if validation fails.
    """
    if not OPERATION_ID_PATTERN.match(operation_id):
        raise ValueError(
            f"Invalid operation_id format: {operation_id}. "
            "Must be 1-100 lowercase alphanumeric characters or hyphens."
        )


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
    pending_events: Deque[str] = field(default_factory=deque)  # maxlen set post-init
    created_at: datetime = field(default_factory=_utcnow)
    last_event_at: datetime = field(default_factory=_utcnow)
    completed: bool = False
    completion_payload: Optional[Dict[str, Any]] = None
    owner_user_id: Optional[UUID] = None

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
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


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

    def _new_operation_state(self) -> _OperationState:
        """Create a new _OperationState with a bounded pending_events deque."""
        state = _OperationState()
        state.pending_events = deque(maxlen=self._pending_event_limit)
        return state

    async def subscribe(
        self,
        operation_id: str,
        user_id: UUID,
        max_duration_seconds: float = 7200.0,
    ) -> AsyncIterator[str]:
        """
        Subscribe to an operation's event stream.

        Yields formatted SSE strings until the stream completes, the client
        disconnects, or the maximum connection duration is reached.

        Args:
            operation_id: The operation to subscribe to.
            user_id: The authenticated user's ID.
            max_duration_seconds: Maximum connection lifetime in seconds (default: 2 hours).
        """
        validate_operation_id(operation_id)
        queue: Queue[Optional[str]] = asyncio.Queue()
        subscription = _Subscription(
            operation_id=operation_id,
            user_id=user_id,
            queue=queue,
        )

        async with self._lock:
            state = self._operations.get(operation_id)
            if state is None:
                state = self._new_operation_state()
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

        connection_start = datetime.now(timezone.utc)
        try:
            while True:
                # Check connection TTL
                elapsed = (datetime.now(timezone.utc) - connection_start).total_seconds()
                if elapsed >= max_duration_seconds:
                    logger.info(
                        "SSE connection TTL reached for operation %s (%.0fs)",
                        operation_id,
                        elapsed,
                    )
                    break

                try:
                    # Use timeout on queue.get to periodically check TTL
                    item = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    # No event received in 30s — loop back to check TTL
                    continue

                if item is None:
                    break
                yield item
        finally:
            await self._remove_subscription(operation_id, subscription)

    async def set_operation_owner(self, operation_id: str, user_id: UUID) -> None:
        """Set the owner of an operation when it's created."""
        async with self._lock:
            state = self._operations.get(operation_id)
            if state is None:
                state = self._new_operation_state()
                self._operations[operation_id] = state
            # Only set owner if not already set (first come, first served)
            if state.owner_user_id is None:
                state.owner_user_id = user_id

    async def verify_operation_ownership(self, operation_id: str, user_id: UUID) -> bool:
        """Verify that the user owns the operation."""
        async with self._lock:
            state = self._operations.get(operation_id)
            if state is None:
                # If operation doesn't exist yet, allow access (will be created on first event)
                return True
            # If owner is not set, allow access
            if state.owner_user_id is None:
                return True
            # Check if user is the owner
            return state.owner_user_id == user_id

    async def publish(self, event: OperationEvent, *, publisher_user_id: Optional[UUID] = None) -> None:
        """Publish an event to all subscribers and buffer it for future subscribers.

        Args:
            event: The SSE event to publish.
            publisher_user_id: The user ID of the publisher. When provided,
                ownership is verified before publishing. When ``None``,
                the call is treated as a trusted internal publish (e.g.,
                system-level notifications) and ownership checks are skipped.
                Callers should always supply this parameter when the
                ``operation_id`` originates from user input.
        """
        operation_id = event.operation_id
        validate_operation_id(operation_id)

        # --- Authorization gate ---
        if publisher_user_id is not None:
            is_owner = await self.verify_operation_ownership(operation_id, publisher_user_id)
            if not is_owner:
                logger.warning(
                    "Publish rejected: user %s is not the owner of operation %s",
                    publisher_user_id,
                    operation_id,
                )
                raise OperationOwnershipError(operation_id, publisher_user_id)

        formatted = self._format_event(event)
        subscribers: List[_Subscription] = []

        async with self._lock:
            state = self._operations.get(operation_id)
            if state is None:
                state = self._new_operation_state()
                self._operations[operation_id] = state

            state.last_event_at = datetime.now(timezone.utc)
            state.pending_events.append(formatted)

            # Store completion payload only on first completion (first-write-wins)
            if event.step == "pipeline.completed" and state.completion_payload is None:
                state.completion_payload = event.payload
            elif event.step == "pipeline.completed" and state.completion_payload is not None:
                logger.warning(
                    "Duplicate completion event for operation %s — ignoring payload overwrite",
                    operation_id,
                )

            subscribers = list(state.subscribers)

        if not subscribers:
            logger.debug(
                "Buffered event for operation %s (no active subscribers)",
                operation_id,
            )
            return
        logger.debug(
            "Publishing event to %d subscribers for operation %s",
            len(subscribers),
            operation_id,
        )
        await asyncio.gather(
            *(self._enqueue_event(subscriber, formatted) for subscriber in subscribers),
            return_exceptions=True,
        )

    async def complete(self, operation_id: str) -> None:
        """
        Mark an operation as complete and close subscriber streams.

        Queues receive a sentinel value that terminates the async generator.
        Idempotent: calling complete() on an already-completed operation is a no-op.
        """
        subscribers: List[_Subscription] = []

        async with self._lock:
            state = self._operations.get(operation_id)
            if state is None:
                return

            if state.completed:
                logger.debug(
                    "Operation %s already completed — ignoring duplicate complete()",
                    operation_id,
                )
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
        now = datetime.now(timezone.utc)
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

    async def cleanup_stale_subscriptions(self) -> None:
        """Remove subscriptions that have been inactive beyond the stale threshold."""
        now = datetime.now(timezone.utc)
        async with self._lock:
            for op_id, state in list(self._operations.items()):
                stale_subs = [
                    sub for sub in state.subscribers
                    if now - sub.last_activity >= self._stale_after
                ]
                for sub in stale_subs:
                    state.subscribers.remove(sub)
                    await sub.queue.put(None)  # Signal termination
                    logger.debug(
                        "Removed stale subscription for operation %s (user %s, inactive %.0fs)",
                        op_id,
                        sub.user_id,
                        (now - sub.last_activity).total_seconds(),
                    )

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
        """Periodically purge stale operations and subscriptions."""
        try:
            while True:
                await asyncio.sleep(self._cleanup_interval)
                await self.cleanup_stale_subscriptions()
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
            subscription.last_activity = datetime.now(timezone.utc)
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
    user_id: Optional[UUID] = None,
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
        ),
        publisher_user_id=user_id,
    )


async def emit_step_progress(
    *,
    operation_id: str,
    scope: str,
    step: str,
    message: str,
    progress: Optional[int] = None,
    payload: Optional[Dict[str, object]] = None,
    user_id: Optional[UUID] = None,
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
        ),
        publisher_user_id=user_id,
    )


async def emit_step_success(
    *,
    operation_id: str,
    scope: str,
    step: str,
    message: str,
    payload: Optional[Dict[str, object]] = None,
    progress: Optional[int] = None,
    user_id: Optional[UUID] = None,
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
        ),
        publisher_user_id=user_id,
    )


async def emit_step_failure(
    *,
    operation_id: str,
    scope: str,
    step: str,
    message: str,
    error: Optional[str] = None,
    user_id: Optional[UUID] = None,
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
        ),
        publisher_user_id=user_id,
    )


async def emit_pipeline_complete(
    *,
    operation_id: str,
    scope: str,
    message: str,
    payload: Optional[Dict[str, object]] = None,
    user_id: Optional[UUID] = None,
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
        ),
        publisher_user_id=user_id,
    )
    await event_stream_manager.complete(operation_id)
