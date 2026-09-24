from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from src.services.sse_service import EventStreamManager, OperationEvent


@pytest.mark.asyncio
async def test_subscribe_emits_connection_event() -> None:
    manager = EventStreamManager(cleanup_interval_seconds=0)
    operation_id = "op-connection"
    user_id = uuid4()
    received: list[str] = []

    async def consumer() -> None:
        async for payload in manager.subscribe(operation_id, user_id):
            received.append(payload)
            break

    await asyncio.wait_for(asyncio.create_task(consumer()), timeout=1.0)

    assert received, "Expected at least one SSE message"
    assert "event: connection.connected" in received[0]


@pytest.mark.asyncio
async def test_publish_delivers_event_to_subscriber() -> None:
    manager = EventStreamManager(cleanup_interval_seconds=0)
    operation_id = "op-publish"
    user_id = uuid4()
    received: list[str] = []

    async def consumer() -> None:
        async for payload in manager.subscribe(operation_id, user_id):
            received.append(payload)
            if len(received) == 2:
                break

    consume_task = asyncio.create_task(consumer())
    await asyncio.sleep(0)  # allow subscription registration

    await manager.publish(
        OperationEvent(
            operation_id=operation_id,
            scope="workspace",
            step="scrape.started",
            status="started",
            message="Scraping website",
            progress=10,
        )
    )

    await asyncio.sleep(0)
    await manager.complete(operation_id)
    await asyncio.wait_for(consume_task, timeout=1.0)

    assert len(received) == 2
    assert received[1].startswith("id: ")
    assert "event: workspace.scrape.started" in received[1]
    assert '"status":"started"' in received[1]


@pytest.mark.asyncio
async def test_multiple_subscribers_receive_same_events() -> None:
    manager = EventStreamManager(cleanup_interval_seconds=0)
    operation_id = "op-multi"

    async def collect() -> list[str]:
        events: list[str] = []
        async for payload in manager.subscribe(operation_id, uuid4()):
            events.append(payload)
            if len(events) == 2:
                break
        return events

    task_one = asyncio.create_task(collect())
    task_two = asyncio.create_task(collect())
    await asyncio.sleep(0)

    await manager.publish(
        OperationEvent(
            operation_id=operation_id,
            scope="workspace",
            step="brand_voice.completed",
            status="completed",
            message="Brand voice generated",
        )
    )
    await manager.complete(operation_id)

    events_one = await asyncio.wait_for(task_one, timeout=1.0)
    events_two = await asyncio.wait_for(task_two, timeout=1.0)

    for events in (events_one, events_two):
        assert len(events) == 2
        assert "event: workspace.brand_voice.completed" in events[1]


@pytest.mark.asyncio
async def test_pending_events_delivered_to_late_subscriber() -> None:
    manager = EventStreamManager(cleanup_interval_seconds=0)
    operation_id = "op-backlog"
    late_user = uuid4()

    await manager.publish(
        OperationEvent(
            operation_id=operation_id,
            scope="workspace",
            step="scrape.completed",
            status="completed",
            message="Scrape finished",
            progress=30,
        )
    )

    received: list[str] = []

    async def consumer() -> None:
        async for payload in manager.subscribe(operation_id, late_user):
            received.append(payload)
            if len(received) == 2:
                break

    await asyncio.wait_for(asyncio.create_task(consumer()), timeout=1.0)

    assert len(received) == 2
    assert "event: workspace.scrape.completed" in received[1]
    assert '"message":"Scrape finished"' in received[1]


@pytest.mark.asyncio
async def test_cleanup_removes_completed_operation() -> None:
    manager = EventStreamManager(
        cleanup_interval_seconds=0,
        stale_after_seconds=0.01,
    )
    operation_id = "op-cleanup"

    await manager.publish(
        OperationEvent(
            operation_id=operation_id,
            scope="workspace",
            step="pipeline.completed",
            status="completed",
            message="Pipeline finished",
        )
    )
    await manager.complete(operation_id)
    await manager.cleanup_stale_operations()

    active = await manager.active_operation_ids()
    assert operation_id not in active


@pytest.mark.asyncio
async def test_publish_rejects_unauthorized_user() -> None:
    """Publish must raise OperationOwnershipError when publisher is not the owner."""
    from src.services.sse_service import OperationOwnershipError

    manager = EventStreamManager(cleanup_interval_seconds=0)
    operation_id = "op-auth-test"
    owner_id = uuid4()
    attacker_id = uuid4()

    await manager.set_operation_owner(operation_id, owner_id)

    event = OperationEvent(
        operation_id=operation_id,
        scope="workspace",
        step="scrape.started",
        status="started",
        message="Should be rejected",
    )

    with pytest.raises(OperationOwnershipError):
        await manager.publish(event, publisher_user_id=attacker_id)


@pytest.mark.asyncio
async def test_publish_allows_owner() -> None:
    """Publish must succeed when the publisher is the operation owner."""
    manager = EventStreamManager(cleanup_interval_seconds=0)
    operation_id = "op-owner-test"
    owner_id = uuid4()

    await manager.set_operation_owner(operation_id, owner_id)

    event = OperationEvent(
        operation_id=operation_id,
        scope="workspace",
        step="scrape.started",
        status="started",
        message="Should be accepted",
    )

    # Should not raise
    await manager.publish(event, publisher_user_id=owner_id)


@pytest.mark.asyncio
async def test_publish_allows_none_user_id_for_internal_calls() -> None:
    """Publish with publisher_user_id=None must skip ownership checks (backward compat)."""
    manager = EventStreamManager(cleanup_interval_seconds=0)
    operation_id = "op-internal-test"
    owner_id = uuid4()

    await manager.set_operation_owner(operation_id, owner_id)

    event = OperationEvent(
        operation_id=operation_id,
        scope="system",
        step="health.check",
        status="started",
        message="Internal event",
    )

    # Should not raise even though no user_id is provided
    await manager.publish(event, publisher_user_id=None)


@pytest.mark.asyncio
async def test_set_operation_owner_first_write_wins() -> None:
    """Only the first call to set_operation_owner should set the owner."""
    manager = EventStreamManager(cleanup_interval_seconds=0)
    operation_id = "op-first-wins"
    first_user = uuid4()
    second_user = uuid4()

    await manager.set_operation_owner(operation_id, first_user)
    await manager.set_operation_owner(operation_id, second_user)

    # First user should remain the owner
    assert await manager.verify_operation_ownership(operation_id, first_user) is True
    assert await manager.verify_operation_ownership(operation_id, second_user) is False
