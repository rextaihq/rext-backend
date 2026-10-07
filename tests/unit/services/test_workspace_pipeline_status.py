"""Workspace creation that a restart can't strand (G20, revnix/rext-control#287).

The workspace pipeline runs as a task inside the API process, so a restart or a deploy ends a
run without a word. Each run is recorded on the workspace's row; a running row the process no
longer runs reads as interrupted, GET /workspaces/{id} shows it as `pipeline`, and
POST /workspaces/{id}/pipeline/retry runs it again. Checked on the test PostgreSQL inside a
rolled-back transaction, with the pipeline itself replaced (it reads a website and calls a model).
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.async_database import get_async_db
from src.api.database.base import Base
from src.api.middleware.exceptions import BusinessRuleViolationException
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.security.dependencies import get_current_user
from src.services import workspace_pipeline, workspace_service
from src.services.workspace_service import WorkspaceService, pipeline_state
from tests.conftest import TEST_DATABASE_URL

TABLES = [WorkspaceModel, WorkspaceMembers, UserRole]


def _with_their_references(models):
    """The tables and every table their foreign keys point at."""
    tables, stack = set(), [model.__table__ for model in models]
    while stack:
        table = stack.pop()
        if table not in tables:
            tables.add(table)
            stack.extend(fk.column.table for fk in table.foreign_keys)
    return list(tables)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(
                sync, tables=_with_their_references(TABLES), checkfirst=True
            )
        )
        async with AsyncSession(bind=connection, expire_on_commit=False) as db:
            yield db
        await transaction.rollback()
    await engine.dispose()


@pytest.fixture
def started_tasks(monkeypatch):
    """create_task replaced: the run's coroutine is kept, not run, and closed afterwards."""
    coroutines = []

    def fake_create_task(coroutine):
        coroutines.append(coroutine)
        return Mock()

    monkeypatch.setattr(workspace_service, "create_task", fake_create_task)
    monkeypatch.setattr(workspace_service.event_stream_manager, "set_operation_owner", AsyncMock())
    yield coroutines
    for coroutine in coroutines:
        coroutine.close()


async def _workspace(session, *, status=None, started_at=None, operation_id=None):
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    session.add(user)
    await session.flush()
    workspace = WorkspaceModel(
        user_id=user.id,
        name="Pipeline",
        slug=f"pipeline-{uuid4().hex[:8]}",
        url="https://example.org",
        pipeline_status=status,
        pipeline_started_at=started_at,
        pipeline_operation_id=operation_id,
    )
    session.add(workspace)
    await session.flush()
    session.add(WorkspaceMembers(user_id=user.id, workspace_id=workspace.id, status="active"))
    await session.flush()
    return user, workspace


def _before_this_process():
    return workspace_service._PROCESS_STARTED_AT - timedelta(seconds=1)


def test_a_running_row_reads_as_interrupted_once_its_process_is_gone(monkeypatch):
    now = datetime.now(timezone.utc)
    assert pipeline_state(WorkspaceModel()) is None
    assert pipeline_state(WorkspaceModel(pipeline_status="completed"))["status"] == "completed"
    assert pipeline_state(WorkspaceModel(pipeline_status="failed"))["status"] == "failed"

    running = WorkspaceModel(pipeline_status="running", pipeline_started_at=now)
    assert pipeline_state(running)["status"] == "running"
    running.pipeline_started_at = _before_this_process()
    assert pipeline_state(running)["status"] == "interrupted"

    # A process that has been up for an hour: a run that outlived any real one is gone too.
    monkeypatch.setattr(workspace_service, "_PROCESS_STARTED_AT", now - timedelta(hours=1))
    running.pipeline_started_at = now - timedelta(minutes=11)
    assert pipeline_state(running)["status"] == "interrupted"
    running.pipeline_started_at = now - timedelta(minutes=1)
    assert pipeline_state(running)["status"] == "running"


@pytest.mark.asyncio
async def test_an_interrupted_run_is_retried_and_recorded_as_running(session, started_tasks):
    user, workspace = await _workspace(
        session, status="running", started_at=_before_this_process(), operation_id="old-run"
    )

    operation_id = await WorkspaceService(session).retry_pipeline_for_user(workspace.id, user.id)

    assert len(started_tasks) == 1
    await session.refresh(workspace)
    assert workspace.pipeline_status == "running"
    assert workspace.pipeline_operation_id == operation_id != "old-run"
    assert pipeline_state(workspace)["status"] == "running"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [None, "completed"])
async def test_only_a_failed_or_interrupted_run_is_retried(session, started_tasks, status):
    user, workspace = await _workspace(
        session, status=status, started_at=datetime.now(timezone.utc)
    )

    with pytest.raises(BusinessRuleViolationException, match="failed or was interrupted"):
        await WorkspaceService(session).retry_pipeline_for_user(workspace.id, user.id)

    assert started_tasks == []


@pytest.mark.asyncio
async def test_a_refresh_waits_for_the_run_in_progress(session, started_tasks):
    user, workspace = await _workspace(
        session, status="running", started_at=datetime.now(timezone.utc), operation_id="live"
    )

    with pytest.raises(BusinessRuleViolationException, match="still being read"):
        await WorkspaceService(session).refresh_brand_voice_for_user(workspace.id, user.id)

    assert started_tasks == []
    assert workspace.pipeline_operation_id == "live"


@pytest.mark.asyncio
@pytest.mark.parametrize("pipeline_fails", [False, True])
async def test_a_run_records_how_it_ended(session, started_tasks, monkeypatch, pipeline_fails):
    user, workspace = await _workspace(session, status="failed")

    # The pipeline settles its outcome through on_finished, as WorkspacePipeline.run does.
    async def pipeline(**kwargs):
        await kwargs["on_finished"]("failed" if pipeline_fails else "completed")
        if pipeline_fails:
            raise RuntimeError("the site timed out")

    run = AsyncMock(side_effect=pipeline)
    monkeypatch.setattr(workspace_service, "run_workspace_pipeline", run)

    @asynccontextmanager
    async def same_session():
        yield session

    monkeypatch.setattr(workspace_service, "get_async_db_context", same_session)
    operation_id = await WorkspaceService(session).retry_pipeline_for_user(workspace.id, user.id)

    coroutine = started_tasks.pop()
    if pipeline_fails:
        with pytest.raises(RuntimeError):
            await coroutine
    else:
        await coroutine

    await session.refresh(workspace)
    assert run.await_args.kwargs["operation_id"] == operation_id
    assert workspace.pipeline_status == ("failed" if pipeline_fails else "completed")


@pytest.mark.asyncio
async def test_an_older_run_ending_late_leaves_the_newer_runs_status(session):
    _, workspace = await _workspace(
        session, status="running", started_at=datetime.now(timezone.utc), operation_id="newer"
    )

    await workspace_service._record_pipeline_end(session, workspace.id, "older", "failed")

    await session.refresh(workspace)
    assert workspace.pipeline_status == "running"
    assert workspace.pipeline_operation_id == "newer"


async def _call(session, user, method, path):
    from src.api.server import app

    async def override_get_db():
        yield session

    app.dependency_overrides[get_async_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: {"identity": str(user.id)}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            return await ac.request(method, f"/api/v1/workspaces{path}")
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def allowed(monkeypatch):
    # Imported inside require_permissions' wrapper, so patched where they are defined.
    monkeypatch.setattr("src.utils.rbac_utils.check_all_permissions", AsyncMock(return_value=True))
    monkeypatch.setattr("src.utils.rbac_utils.check_any_permission", AsyncMock(return_value=True))


@pytest.mark.asyncio
async def test_the_retry_route_and_the_detail_show_the_new_run(
    session, started_tasks, allowed, monkeypatch
):
    user, workspace = await _workspace(
        session, status="running", started_at=_before_this_process(), operation_id="old-run"
    )
    # The detail's cached brand voice and its counts read tables this test doesn't build.
    monkeypatch.setattr(
        WorkspaceService,
        "get_workspace_with_brand_voice",
        AsyncMock(return_value={"id": str(workspace.id)}),
    )
    monkeypatch.setattr(WorkspaceService, "get_workspace_analytics", AsyncMock(return_value={}))

    before = await _call(session, user, "GET", f"/{workspace.id}")
    assert before.status_code == 200
    assert before.json()["data"]["workspace"]["pipeline"]["status"] == "interrupted"

    retried = await _call(session, user, "POST", f"/{workspace.id}/pipeline/retry")
    assert retried.status_code == 200
    operation_id = retried.json()["data"]["operation_id"]

    after = await _call(session, user, "GET", f"/{workspace.id}")
    assert after.json()["data"]["workspace"]["pipeline"]["status"] == "running"
    assert after.json()["data"]["workspace"]["pipeline"]["operation_id"] == operation_id

    again = await _call(session, user, "POST", f"/{workspace.id}/pipeline/retry")
    assert again.status_code == 400


# G20a (rext-control#672): a live run is never "interrupted", a run is cut off at the limit, the end
# waits for its row, and the outcome is on the row before the terminal event goes out.


@pytest.mark.asyncio
async def test_a_live_run_past_the_limit_still_runs_and_cant_be_retried(
    session, started_tasks, monkeypatch
):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(workspace_service, "_PROCESS_STARTED_AT", now - timedelta(hours=1))
    user, workspace = await _workspace(
        session, status="running", started_at=now - timedelta(minutes=11), operation_id="slow"
    )
    assert pipeline_state(workspace)["status"] == "interrupted"

    monkeypatch.setattr(workspace_service, "_live_operations", {"slow"})
    assert pipeline_state(workspace)["status"] == "running"
    with pytest.raises(BusinessRuleViolationException, match="failed or was interrupted"):
        await WorkspaceService(session).retry_pipeline_for_user(workspace.id, user.id)
    assert started_tasks == []


@pytest.mark.asyncio
async def test_a_run_past_the_limit_is_cut_off_and_recorded_as_failed(session, monkeypatch):
    _, workspace = await _workspace(
        session, status="running", started_at=datetime.now(timezone.utc), operation_id="hung"
    )
    seen_live = []

    async def hangs(**kwargs):
        seen_live.append(kwargs["operation_id"] in workspace_service._live_operations)
        await asyncio.sleep(5)

    monkeypatch.setattr(workspace_service, "run_workspace_pipeline", hangs)
    monkeypatch.setattr(workspace_service, "_PIPELINE_RUN_LIMIT", timedelta(seconds=0.05))
    # The cut-off run's session is rolled back before the record; here that session also holds the
    # fixture's tables, so the rollback is only counted.
    rollback = AsyncMock()
    monkeypatch.setattr(session, "rollback", rollback)

    with pytest.raises(TimeoutError):
        await workspace_service._run_pipeline_recorded(
            session,
            operation_id="hung",
            workspace_id=workspace.id,
            user_id=uuid4(),
            url="https://a.example",
        )

    await session.refresh(workspace)
    rollback.assert_awaited()
    assert seen_live == [True]
    assert "hung" not in workspace_service._live_operations
    assert workspace.pipeline_status == "failed"


@pytest.mark.asyncio
async def test_the_end_waits_for_the_row_its_request_has_not_committed_yet(monkeypatch):
    monkeypatch.setattr(workspace_service, "_RECORD_RETRY_SECONDS", 0)
    db = Mock()
    # Not there yet (the creating request hasn't committed), then there.
    db.execute = AsyncMock(side_effect=[Mock(rowcount=0), Mock(rowcount=1)])
    db.scalar = AsyncMock(return_value=None)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    await workspace_service._record_pipeline_end(db, uuid4(), "new-run", "failed")

    assert db.execute.await_count == 2
    db.rollback.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
async def test_the_outcome_is_recorded_before_the_terminal_event(monkeypatch, fails):
    order = []

    async def on_finished(status):
        order.append(f"recorded {status}")

    async def emitted(*args, **kwargs):
        order.append("event")

    monkeypatch.setattr(workspace_pipeline, "emit_pipeline_complete", emitted)
    monkeypatch.setattr(workspace_pipeline, "emit_step_failure", emitted)
    monkeypatch.setattr(workspace_pipeline, "invalidate_cache_key", AsyncMock())
    pipeline = workspace_pipeline.WorkspacePipeline(
        db=AsyncMock(),
        operation_id="op",
        workspace_id=uuid4(),
        user_id=uuid4(),
        url="https://a.example",
        on_finished=on_finished,
    )
    scrape = (
        AsyncMock(side_effect=RuntimeError("down"))
        if fails
        else AsyncMock(return_value=Mock(content=""))
    )
    monkeypatch.setattr(pipeline, "_scrape_website", scrape)
    for step in ("_extract_brand_voice", "_persist_brand_voice", "_embed_brand_voice"):
        monkeypatch.setattr(pipeline, step, AsyncMock(return_value=None))
    monkeypatch.setattr(pipeline, "_discover_competitors", AsyncMock(return_value=None))
    monkeypatch.setattr(pipeline, "_store_favicon", AsyncMock(return_value=None))

    if fails:
        with pytest.raises(RuntimeError):
            await pipeline.run()
    else:
        await pipeline.run()

    assert order == [f"recorded {'failed' if fails else 'completed'}", "event"]
