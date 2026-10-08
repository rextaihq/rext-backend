"""A workspace for a business with no website yet (revnix/rext-control#853).

The create request carries the owner's description of the business in place of an address. It is
kept as the brand voice's About, word for word, and the pipeline's one step drafts the rest of the
voice from it: no site is read, so no people, competitors or favicon. A run that failed or was
interrupted is run again from the About. The service is checked on the test PostgreSQL inside a
rolled-back transaction, the pipeline against a stand-in session, and the model is never called.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.api.database.base import Base
from src.api.middleware.exceptions import BusinessRuleViolationException, RextValidationException
from src.api.models.knowledge_models.knowledge_model import BrandVoice
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.schema.brand_voice_schema import BrandSchema
from src.api.schema.workspace_schema import (
    DESCRIPTION_MAX_LENGTH,
    WorkspacePipelineRetryRequest,
    WorkspacePipelineState,
    WorkspaceSchema,
)
from src.services import workspace_pipeline, workspace_service
from src.services.workspace_pipeline import WorkspacePipeline
from src.services.workspace_service import WorkspaceService, pipeline_state
from src.utils.name_utils import validate_brand_name
from tests.conftest import TEST_DATABASE_URL

DESCRIPTION = "We bake sourdough bread and pastries for cafés and restaurants in Leeds."
TABLES = [WorkspaceModel, WorkspaceMembers, UserRole, BrandVoice]


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
def started_runs(monkeypatch):
    """The runs the service starts, as the arguments each was given: none of them runs."""
    runs = []

    async def recorded(db, **kwargs):
        runs.append(kwargs)

    def fake_create_task(coroutine):
        coroutine.close()
        return Mock()

    monkeypatch.setattr(workspace_service, "create_task", fake_create_task)
    monkeypatch.setattr(workspace_service, "_run_pipeline_recorded", recorded)
    monkeypatch.setattr(workspace_service.event_stream_manager, "set_operation_owner", AsyncMock())
    return runs


async def _user(session):
    user = Users(email=f"{uuid4().hex[:12]}@example.com")
    session.add(user)
    await session.flush()
    return user


async def _workspace_without_a_site(session, *, status, about=DESCRIPTION):
    user = await _user(session)
    workspace = WorkspaceModel(
        user_id=user.id,
        name="Crumb and Crust",
        slug=f"crumb-{uuid4().hex[:8]}",
        url=None,
        pipeline_status=status,
        pipeline_started_at=datetime.now(timezone.utc),
        pipeline_operation_id="first-run",
    )
    session.add(workspace)
    await session.flush()
    session.add(WorkspaceMembers(user_id=user.id, workspace_id=workspace.id, status="active"))
    if about is not None:
        session.add(BrandVoice(workspace_id=workspace.id, about=about))
    await session.flush()
    return user, workspace


# The request


def test_the_request_takes_a_description_in_place_of_a_website():
    asked = WorkspaceSchema(name="Crumb and Crust", description=f"  {DESCRIPTION}\n")
    assert asked.url is None
    assert asked.description == DESCRIPTION

    assert WorkspaceSchema(name="Crumb and Crust", description="   ").description is None
    # Its length is the route's to judge, once trimmed and only when it is used: spaces around a
    # description of full length don't refuse it, and one sent with a website refuses nothing.
    padded = WorkspaceSchema(
        name="Crumb and Crust", description=f"  {'x' * DESCRIPTION_MAX_LENGTH}  "
    )
    assert len(padded.description) == DESCRIPTION_MAX_LENGTH
    with_site = WorkspaceSchema(
        name="Crumb and Crust", url="https://example.com", description="x" * 5000
    )
    assert with_site.url is not None
    # A website is still held to its own rules when one is sent.
    with pytest.raises(ValidationError):
        WorkspaceSchema(name="Crumb and Crust", url="http://example.com")


# The service


@pytest.mark.asyncio
async def test_creating_without_a_site_keeps_the_description_and_starts_the_run_from_it(
    session, started_runs, monkeypatch
):
    user = await _user(session)
    service = WorkspaceService(session)
    monkeypatch.setattr(service, "_ensure_active_user", AsyncMock())
    monkeypatch.setattr(service, "create_workspace_member", AsyncMock())
    monkeypatch.setattr(service, "_get_workspace_owner_role", AsyncMock(return_value=Mock()))
    monkeypatch.setattr(service, "_assign_role_to_user", AsyncMock())

    created = await service.create_workspace_for_user(
        user_id=user.id, name="Crumb and Crust", timezone=None, url=None, description=DESCRIPTION
    )

    workspace = await session.get(WorkspaceModel, created["workspace"]["id"])
    assert workspace.url is None
    assert workspace.pipeline_status == "running"
    voice = (
        await session.execute(select(BrandVoice).where(BrandVoice.workspace_id == workspace.id))
    ).scalar_one()
    assert voice.about == DESCRIPTION
    assert voice.brand_name is None

    # The run is created to be given the description and the name; nothing ran it here.
    assert created["operation_id"] == workspace.pipeline_operation_id


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["failed", "running"])
async def test_a_run_that_failed_or_was_interrupted_is_run_again_from_the_about(
    session, started_runs, monkeypatch, status
):
    user, workspace = await _workspace_without_a_site(session, status=status)
    if status == "running":
        # A running row this process doesn't run: a restart ended it.
        workspace.pipeline_started_at = workspace_service._PROCESS_STARTED_AT.replace(year=2020)
        await session.flush()
    service = WorkspaceService(session)
    monkeypatch.setattr(service, "_ensure_active_user", AsyncMock())

    operation_id = await service.retry_pipeline_for_user(workspace.id, user.id)

    await session.refresh(workspace)
    assert workspace.pipeline_operation_id == operation_id != "first-run"
    assert workspace.pipeline_status == "running"


@pytest.mark.asyncio
async def test_the_run_again_is_given_the_about_and_the_name(session, monkeypatch):
    user, workspace = await _workspace_without_a_site(session, status="failed")
    given = {}

    async def recorded(db, **kwargs):
        given.update(kwargs)

    started = []

    def kept(coroutine):
        started.append(coroutine)
        return Mock()

    monkeypatch.setattr(workspace_service, "create_task", kept)
    monkeypatch.setattr(workspace_service, "_run_pipeline_recorded", recorded)
    monkeypatch.setattr(workspace_service.event_stream_manager, "set_operation_owner", AsyncMock())

    class _Context:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_):
            return False

    monkeypatch.setattr(workspace_service, "get_async_db_context", lambda: _Context())
    service = WorkspaceService(session)
    monkeypatch.setattr(service, "_ensure_active_user", AsyncMock())

    await service.retry_pipeline_for_user(workspace.id, user.id)
    await started[0]

    assert given["url"] is None
    assert given["description"] == DESCRIPTION
    assert given["name"] == "Crumb and Crust"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["completed", "failed"])
async def test_a_refresh_has_no_website_to_read(session, started_runs, monkeypatch, status):
    user, workspace = await _workspace_without_a_site(session, status=status)
    service = WorkspaceService(session)
    monkeypatch.setattr(service, "_ensure_active_user", AsyncMock())

    # "Read the website again" stays a refusal, whatever the last run did: only the retry of a
    # run that failed or was interrupted drafts again, so the owner's edits are never drafted over.
    with pytest.raises(RextValidationException, match="URL is required"):
        await service.refresh_brand_voice_for_user(workspace.id, user.id)
    assert started_runs == []
    await session.refresh(workspace)
    assert workspace.pipeline_operation_id == "first-run"


@pytest.mark.asyncio
async def test_a_completed_run_is_not_retried(session, started_runs, monkeypatch):
    user, workspace = await _workspace_without_a_site(session, status="completed")
    service = WorkspaceService(session)
    monkeypatch.setattr(service, "_ensure_active_user", AsyncMock())

    with pytest.raises(BusinessRuleViolationException, match="failed or was interrupted"):
        await service.retry_pipeline_for_user(workspace.id, user.id)
    assert started_runs == []


@pytest.mark.asyncio
async def test_with_no_about_left_there_is_nothing_to_draft_from(
    session, started_runs, monkeypatch
):
    user, workspace = await _workspace_without_a_site(session, status="failed", about="  ")
    service = WorkspaceService(session)
    monkeypatch.setattr(service, "_ensure_active_user", AsyncMock())

    with pytest.raises(RextValidationException, match="Describe the business, or add a website"):
        await service.retry_pipeline_for_user(workspace.id, user.id)


@pytest.mark.asyncio
async def test_a_run_in_progress_is_not_started_twice(session, started_runs, monkeypatch):
    user, workspace = await _workspace_without_a_site(session, status="running")
    monkeypatch.setattr(workspace_service, "_live_operations", {"first-run"})
    service = WorkspaceService(session)
    monkeypatch.setattr(service, "_ensure_active_user", AsyncMock())

    with pytest.raises(BusinessRuleViolationException, match="failed or was interrupted"):
        await service.retry_pipeline_for_user(workspace.id, user.id)
    assert started_runs == []


# Made from a name alone, and set up later (revnix/rext-control#905)


def _service(session, monkeypatch):
    service = WorkspaceService(session)
    monkeypatch.setattr(service, "_ensure_active_user", AsyncMock())
    return service


def _runs_given(monkeypatch, session):
    """The run the service starts, awaited here in place of the pipeline: what it was given."""
    given, started = {}, []

    async def recorded(db, **kwargs):
        given.update(kwargs)

    def kept(coroutine):
        started.append(coroutine)
        return Mock()

    class _Context:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *_):
            return False

    monkeypatch.setattr(workspace_service, "create_task", kept)
    monkeypatch.setattr(workspace_service, "_run_pipeline_recorded", recorded)
    monkeypatch.setattr(workspace_service.event_stream_manager, "set_operation_owner", AsyncMock())
    monkeypatch.setattr(workspace_service, "get_async_db_context", lambda: _Context())
    return given, started


def test_a_workspace_nothing_has_run_for_says_so():
    state = pipeline_state(WorkspaceModel(pipeline_status="not_started"))

    assert state == {"status": "not_started", "operation_id": None, "started_at": None}
    assert WorkspacePipelineState(**state).status == "not_started"
    # A name is all the request needs.
    assert WorkspaceSchema(name="Crumb and Crust").url is None


@pytest.mark.asyncio
async def test_a_name_alone_makes_the_workspace_and_starts_nothing(
    session, started_runs, monkeypatch
):
    user = await _user(session)
    service = _service(session, monkeypatch)
    monkeypatch.setattr(service, "create_workspace_member", AsyncMock())
    monkeypatch.setattr(service, "_get_workspace_owner_role", AsyncMock(return_value=Mock()))
    monkeypatch.setattr(service, "_assign_role_to_user", AsyncMock())
    owner = AsyncMock()
    monkeypatch.setattr(workspace_service.event_stream_manager, "set_operation_owner", owner)

    created = await service.create_workspace_for_user(
        user_id=user.id, name="Crumb and Crust", timezone=None, url=None
    )

    assert created["operation_id"] is None
    assert created["workspace"]["pipeline"] == {
        "status": "not_started",
        "operation_id": None,
        "started_at": None,
    }
    workspace = await session.get(WorkspaceModel, created["workspace"]["id"])
    assert (workspace.url, workspace.pipeline_status) == (None, "not_started")
    # Nothing is read or drafted, and no brand voice is made up for it.
    assert started_runs == []
    owner.assert_not_awaited()
    voices = await session.execute(
        select(BrandVoice).where(BrandVoice.workspace_id == workspace.id)
    )
    assert voices.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_a_description_sent_later_is_kept_and_drafted_from(session, monkeypatch):
    user, workspace = await _workspace_without_a_site(session, status="not_started", about=None)
    given, started = _runs_given(monkeypatch, session)

    operation_id = await _service(session, monkeypatch).retry_pipeline_for_user(
        workspace.id, user.id, description=DESCRIPTION
    )
    await started[0]

    voice = (
        await session.execute(select(BrandVoice).where(BrandVoice.workspace_id == workspace.id))
    ).scalar_one()
    assert voice.about == DESCRIPTION
    assert (given["url"], given["description"], given["name"]) == (
        None,
        DESCRIPTION,
        "Crumb and Crust",
    )
    await session.refresh(workspace)
    assert (workspace.pipeline_status, workspace.pipeline_operation_id) == ("running", operation_id)


@pytest.mark.asyncio
async def test_other_words_start_the_voice_over(session, monkeypatch):
    user, workspace = await _workspace_without_a_site(session, status="failed", about="Old words.")
    voice = (
        await session.execute(select(BrandVoice).where(BrandVoice.workspace_id == workspace.id))
    ).scalar_one()
    voice.brand_name, voice.selling_position, voice.target_audience = "Old Name", "Old.", ["Old"]
    await session.flush()
    given, started = _runs_given(monkeypatch, session)
    order = []
    commit = session.commit

    async def committed():
        order.append("committed")
        await commit()

    async def forgotten(key):
        order.append(key)

    monkeypatch.setattr(session, "commit", committed)
    monkeypatch.setattr(workspace_service, "invalidate_cache_key", forgotten)

    await _service(session, monkeypatch).retry_pipeline_for_user(
        workspace.id, user.id, description=DESCRIPTION
    )
    await started[0]

    assert given["description"] == DESCRIPTION
    # What was drafted from the old words goes with them: the new draft keeps what it leaves
    # empty, and would otherwise mix the two.
    await session.refresh(voice)
    assert (voice.about, voice.brand_name, voice.selling_position) == (DESCRIPTION, None, None)
    assert voice.target_audience == []
    # The detail's cached copy is dropped once the new words are committed, not before: a read
    # in between would only put the old ones back.
    assert order[:2] == ["committed", f"workspace:brand_voice:{workspace.id}"]


@pytest.mark.asyncio
async def test_the_same_words_again_keep_what_was_drafted(session, monkeypatch):
    user, workspace = await _workspace_without_a_site(session, status="failed")
    voice = (
        await session.execute(select(BrandVoice).where(BrandVoice.workspace_id == workspace.id))
    ).scalar_one()
    voice.brand_name = "Crumb and Crust"
    await session.flush()
    _, started = _runs_given(monkeypatch, session)
    monkeypatch.setattr(workspace_service, "invalidate_cache_key", AsyncMock())

    await _service(session, monkeypatch).retry_pipeline_for_user(
        workspace.id, user.id, description=f"  {DESCRIPTION} ".strip()
    )
    await started[0]

    await session.refresh(voice)
    assert voice.brand_name == "Crumb and Crust"


@pytest.mark.asyncio
async def test_a_description_sent_blank_is_refused_not_taken_for_none(
    session, started_runs, monkeypatch
):
    # The run failed and an About is kept: a blank description must not draft from it silently.
    user, workspace = await _workspace_without_a_site(session, status="failed")
    asked = WorkspacePipelineRetryRequest(description="   ")
    assert asked.description == ""
    assert WorkspacePipelineRetryRequest().description is None

    with pytest.raises(RextValidationException, match="too short"):
        await _service(session, monkeypatch).retry_pipeline_for_user(
            workspace.id, user.id, description=asked.description
        )
    assert started_runs == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("website", "description", "says"),
    [
        (None, "We bake bread.", "too short"),
        (None, "x" * 1001, "too long"),
        ("https://example.org", DESCRIPTION, "has a website"),
        (None, None, "Describe the business, or add a website"),
    ],
)
async def test_what_cant_be_drafted_from_is_refused_on_the_description(
    session, started_runs, monkeypatch, website, description, says
):
    user, workspace = await _workspace_without_a_site(session, status="not_started", about=None)
    workspace.url = website
    await session.flush()

    with pytest.raises(RextValidationException, match=says) as refused:
        await _service(session, monkeypatch).retry_pipeline_for_user(
            workspace.id, user.id, description=description
        )

    assert [detail["field"] for detail in refused.value.details] == ["description"]
    assert started_runs == []
    await session.refresh(workspace)
    assert workspace.pipeline_status == "not_started"


@pytest.mark.asyncio
@pytest.mark.parametrize("way", ["retry", "refresh"])
async def test_a_website_added_later_is_read_in_the_usual_way(session, monkeypatch, way):
    user, workspace = await _workspace_without_a_site(session, status="not_started", about=None)
    workspace.url = "https://example.org"
    await session.flush()
    given, started = _runs_given(monkeypatch, session)
    service = _service(session, monkeypatch)

    if way == "retry":
        await service.retry_pipeline_for_user(workspace.id, user.id)
    else:
        await service.refresh_brand_voice_for_user(workspace.id, user.id)
    await started[0]

    assert (given["url"], given["description"]) == ("https://example.org", None)


@pytest.mark.asyncio
async def test_a_refresh_before_any_website_is_still_refused(session, started_runs, monkeypatch):
    user, workspace = await _workspace_without_a_site(session, status="not_started", about=None)

    with pytest.raises(RextValidationException, match="URL is required"):
        await _service(session, monkeypatch).refresh_brand_voice_for_user(workspace.id, user.id)
    assert started_runs == []


# The business's name, as its owner typed it (revnix/rext-control#922)


def test_a_typed_business_name_follows_the_workspace_names_rule():
    assert validate_brand_name("  Tom’s Bakery (Leeds) ") == "Tom’s Bakery (Leeds)"
    asked = WorkspaceSchema(name="Ana's workspace", description=DESCRIPTION, brand_name="  ")
    assert asked.brand_name is None

    with pytest.raises(RextValidationException) as refused:
        validate_brand_name("<b>Crumb</b>")
    (detail,) = refused.value.details
    assert detail["field"] == "brand_name"
    assert "Workspace name" not in detail["message"]


@pytest.mark.asyncio
async def test_a_name_typed_at_creation_is_the_brands_name(session, monkeypatch):
    user = await _user(session)
    given, started = _runs_given(monkeypatch, session)
    service = _service(session, monkeypatch)
    monkeypatch.setattr(service, "create_workspace_member", AsyncMock())
    monkeypatch.setattr(service, "_get_workspace_owner_role", AsyncMock(return_value=Mock()))
    monkeypatch.setattr(service, "_assign_role_to_user", AsyncMock())

    created = await service.create_workspace_for_user(
        user_id=user.id,
        name="Ana's workspace",
        timezone=None,
        url=None,
        description=DESCRIPTION,
        brand_name="Crumb and Crust",
    )
    await started[0]

    voice = (
        await session.execute(
            select(BrandVoice).where(BrandVoice.workspace_id == created["workspace"]["id"])
        )
    ).scalar_one()
    assert (voice.about, voice.brand_name) == (DESCRIPTION, "Crumb and Crust")
    assert given["brand_name"] == "Crumb and Crust"


@pytest.mark.asyncio
async def test_a_name_typed_on_the_set_up_page_is_kept_with_the_description(session, monkeypatch):
    user, workspace = await _workspace_without_a_site(session, status="not_started", about=None)
    given, started = _runs_given(monkeypatch, session)
    monkeypatch.setattr(workspace_service, "invalidate_cache_key", AsyncMock())

    await _service(session, monkeypatch).retry_pipeline_for_user(
        workspace.id, user.id, description=DESCRIPTION, brand_name="Crumb and Crust"
    )
    await started[0]

    voice = (
        await session.execute(select(BrandVoice).where(BrandVoice.workspace_id == workspace.id))
    ).scalar_one()
    assert (voice.about, voice.brand_name) == (DESCRIPTION, "Crumb and Crust")
    assert (given["description"], given["brand_name"]) == (DESCRIPTION, "Crumb and Crust")


@pytest.mark.asyncio
async def test_other_words_with_a_name_keep_the_name_typed_now(session, monkeypatch):
    user, workspace = await _workspace_without_a_site(session, status="failed", about="Old words.")
    voice = (
        await session.execute(select(BrandVoice).where(BrandVoice.workspace_id == workspace.id))
    ).scalar_one()
    voice.brand_name = "Old Name"
    await session.flush()
    given, started = _runs_given(monkeypatch, session)
    monkeypatch.setattr(workspace_service, "invalidate_cache_key", AsyncMock())

    await _service(session, monkeypatch).retry_pipeline_for_user(
        workspace.id, user.id, description=DESCRIPTION, brand_name="Crumb and Crust"
    )
    await started[0]

    await session.refresh(voice)
    assert voice.brand_name == "Crumb and Crust"
    assert given["brand_name"] == "Crumb and Crust"


@pytest.mark.asyncio
async def test_a_run_again_is_given_the_name_the_voice_holds(session, monkeypatch):
    user, workspace = await _workspace_without_a_site(session, status="failed")
    voice = (
        await session.execute(select(BrandVoice).where(BrandVoice.workspace_id == workspace.id))
    ).scalar_one()
    voice.brand_name = "Crumb and Crust"
    await session.flush()
    given, started = _runs_given(monkeypatch, session)

    await _service(session, monkeypatch).retry_pipeline_for_user(workspace.id, user.id)
    await started[0]

    assert (given["description"], given["brand_name"]) == (DESCRIPTION, "Crumb and Crust")


# The run


def _events(monkeypatch):
    events = []

    def record(kind):
        async def emit(**kwargs):
            events.append((kind, kwargs))

        return emit

    for kind in ("start", "success", "failure"):
        monkeypatch.setattr(workspace_pipeline, f"emit_step_{kind}", record(kind))
    monkeypatch.setattr(workspace_pipeline, "emit_pipeline_complete", record("complete"))
    monkeypatch.setattr(workspace_pipeline, "invalidate_cache_key", AsyncMock())
    return events


def _session_with(*rows):
    """A stand-in session whose brand-voice read answers `rows` in turn, then the last one."""
    answers = list(rows)

    async def execute(*_, **__):
        row = answers.pop(0) if len(answers) > 1 else answers[0]
        return SimpleNamespace(scalar_one_or_none=lambda: row)

    db = AsyncMock(spec=AsyncSession)
    db.add = Mock()
    db.execute = execute
    return db


async def _drafted(content: str) -> BrandSchema:
    return BrandSchema(
        brand_name="Crumb and Crust",
        about=content,
        customer_profile="Cafés and restaurants that want fresh bread each morning.",
        selling_position="Sourdough and pastries baked for the trade.",
        target_audience=["Café owners", "Restaurant chefs"],
        brand_voice=["Warm", "Plain-spoken"],
        content_pillar=["Sourdough", "Supplying cafés"],
    )


def _pipeline(db, **kwargs):
    pipeline = WorkspacePipeline(
        db=db,
        operation_id="op-853",
        workspace_id=uuid4(),
        user_id=uuid4(),
        url=None,
        description=DESCRIPTION,
        name="Crumb and Crust",
        brand_voice_generator=kwargs.pop("generator", _drafted),
        **kwargs,
    )
    for step in ("_scrape_website", "_discover_competitors", "_store_favicon"):
        setattr(pipeline, step, AsyncMock(side_effect=AssertionError(f"{step} ran")))
    pipeline._persist_brand_voice = AsyncMock(side_effect=AssertionError("the site's saver ran"))
    pipeline._persist_personas = AsyncMock(side_effect=AssertionError("personas were touched"))
    pipeline._embed_brand_voice = AsyncMock()
    return pipeline


@pytest.mark.asyncio
async def test_the_run_without_a_site_is_the_voice_step_alone(monkeypatch):
    events = _events(monkeypatch)
    voice = BrandVoice(workspace_id=uuid4(), about=DESCRIPTION)
    db = _session_with(voice)

    await _pipeline(db).run()

    # One step is announced, and the run ends as every run does.
    assert [(kind, sent.get("step")) for kind, sent in events] == [
        ("start", "brand_voice"),
        ("success", "brand_voice"),
        ("complete", None),
    ]
    assert events[1][1]["payload"]["personas"] == []
    done = events[-1][1]["payload"]
    assert done["brand_voice"]["about"] == DESCRIPTION
    assert done["personas"] == []
    assert "top_competitors" not in done

    # The row the create request wrote is the one filled in.
    db.add.assert_not_called()
    db.commit.assert_awaited()
    assert voice.brand_name == "Crumb and Crust"
    assert voice.customer_profile.startswith("Cafés and restaurants")
    assert voice.target_audience == ["Café owners", "Restaurant chefs"]
    assert voice.brand_voice == ["Warm", "Plain-spoken"]
    assert voice.content_pillar == ["Sourdough", "Supplying cafés"]


@pytest.mark.asyncio
async def test_the_owners_words_stay_as_the_about(monkeypatch):
    _events(monkeypatch)
    voice = BrandVoice(workspace_id=uuid4(), about=DESCRIPTION)

    async def reworded(content: str) -> BrandSchema:
        return BrandSchema(about="An artisan bakery of renown.", customer_profile="Cafés.")

    await _pipeline(_session_with(voice), generator=reworded).run()

    assert voice.about == DESCRIPTION
    assert voice.customer_profile == "Cafés."


@pytest.mark.asyncio
async def test_a_run_ahead_of_its_request_waits_for_the_row(monkeypatch):
    _events(monkeypatch)
    monkeypatch.setattr(workspace_pipeline, "_ABOUT_ROW_WAIT_SECONDS", 0)
    voice = BrandVoice(workspace_id=uuid4(), about=DESCRIPTION)
    db = _session_with(None, None, voice)

    await _pipeline(db).run()

    db.add.assert_not_called()
    assert voice.selling_position == "Sourdough and pastries baked for the trade."


@pytest.mark.asyncio
async def test_a_run_whose_row_never_comes_fails_rather_than_write_a_second(monkeypatch):
    events = _events(monkeypatch)
    monkeypatch.setattr(workspace_pipeline, "_ABOUT_ROW_WAIT_SECONDS", 0)
    db = _session_with(None)

    # Nothing keeps a workspace to one brand voice: a row added here, beside the one the create
    # request commits a moment later, would break every read of it.
    with pytest.raises(RuntimeError, match="not there to draft into"):
        await _pipeline(db).run()

    db.add.assert_not_called()
    assert events[-1] == ("failure", events[-1][1])
    assert events[-1][1]["step"] == "pipeline"


@pytest.mark.asyncio
async def test_a_draft_that_fails_fails_the_run_and_saves_nothing(monkeypatch):
    events = _events(monkeypatch)
    voice = BrandVoice(workspace_id=uuid4(), about=DESCRIPTION)
    db = _session_with(voice)

    async def refused(content: str) -> BrandSchema:
        raise RuntimeError("the model is away")

    with pytest.raises(RuntimeError):
        await _pipeline(db, generator=refused).run()

    assert [(kind, sent.get("step")) for kind, sent in events] == [
        ("start", "brand_voice"),
        ("failure", "brand_voice"),
        ("failure", "pipeline"),
    ]
    assert voice.customer_profile is None
    assert voice.about == DESCRIPTION


@pytest.mark.asyncio
@pytest.mark.parametrize(("url", "label"), [(None, None), ("https://example.com", "Client 2")])
async def test_the_workspaces_label_is_not_embedded_as_the_brand_without_a_site(
    monkeypatch, url, label
):
    embedded = {}

    class _Embeddings:
        async def upsert_brand_voice_embedding(self, **kwargs):
            embedded.update(kwargs)

    monkeypatch.setattr(
        "src.services.brand_voice_embedding_service.BrandVoiceEmbeddingService", _Embeddings
    )
    db = AsyncMock(spec=AsyncSession)
    db.execute = AsyncMock(
        return_value=SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(name="Client 2"))
    )
    pipeline = WorkspacePipeline(
        db=db, operation_id="op", workspace_id=uuid4(), user_id=uuid4(), url=url
    )

    await pipeline._embed_brand_voice(BrandSchema(about=DESCRIPTION))

    assert embedded["workspace_name"] == label


@pytest.mark.asyncio
async def test_the_name_the_voice_holds_stands_over_the_drafts_finding(monkeypatch):
    _events(monkeypatch)
    voice = BrandVoice(workspace_id=uuid4(), about=DESCRIPTION, brand_name="Crumb and Crust")

    async def renamed(content: str) -> BrandSchema:
        return BrandSchema(brand_name="Leeds Bakery Co", customer_profile="Cafés.")

    await _pipeline(_session_with(voice), generator=renamed).run()

    assert voice.brand_name == "Crumb and Crust"
    assert voice.customer_profile == "Cafés."


# The draft itself


def test_the_description_is_drafted_from_only_when_there_is_no_site():
    def built(url):
        return WorkspacePipeline(
            db=AsyncMock(spec=AsyncSession),
            operation_id="op",
            workspace_id=uuid4(),
            user_id=uuid4(),
            url=url,
            description=DESCRIPTION,
        )

    without, with_site = built(None), built("https://example.com")
    assert without._brand_voice_generator == without._description_voice_generator
    assert with_site._brand_voice_generator == with_site._default_brand_voice_generator


@pytest.mark.asyncio
async def test_the_draft_keeps_the_description_and_names_no_one(monkeypatch):
    asked = {}

    async def answered(model, messages, **kwargs):
        asked["messages"] = messages
        # Whatever the model sends back for these three, none of it is kept.
        return BrandSchema(
            brand_name="Crumb and Crust",
            about="A bakery with twenty years of awards.",
            customer_profile="Cafés and restaurants.",
            competitors=["Another Bakery"],
            personas=[{"name": "Sam Baker", "source": "founder"}],
        )

    monkeypatch.setattr(workspace_pipeline, "load_model", lambda **_: Mock())
    monkeypatch.setattr(workspace_pipeline, "ainvoke_watched", answered)
    pipeline = WorkspacePipeline(
        db=AsyncMock(spec=AsyncSession),
        operation_id="op",
        workspace_id=uuid4(),
        user_id=uuid4(),
        url=None,
        description=DESCRIPTION,
        name="Crumb and Crust",
    )

    drafted = await pipeline._description_voice_generator(f"  {DESCRIPTION} ")

    assert drafted.about == DESCRIPTION
    assert drafted.competitors == []
    assert drafted.personas == []
    assert drafted.customer_profile == "Cafés and restaurants."
    rules, given = (message.content for message in asked["messages"])
    assert "Never invent a fact" in rules
    assert DESCRIPTION in given and "Crumb and Crust" in given
    # Nothing to draft from: no call at all.
    asked.clear()
    assert await pipeline._description_voice_generator("   ") is None
    assert asked == {}


@pytest.mark.asyncio
async def test_the_draft_is_told_the_typed_name_and_asked_for_no_other(monkeypatch):
    asked = {}

    async def answered(model, messages, **kwargs):
        asked["messages"] = messages
        return BrandSchema(brand_name="Leeds Sourdough House", customer_profile="Cafés.")

    monkeypatch.setattr(workspace_pipeline, "load_model", lambda **_: Mock())
    monkeypatch.setattr(workspace_pipeline, "ainvoke_watched", answered)
    pipeline = WorkspacePipeline(
        db=AsyncMock(spec=AsyncSession),
        operation_id="op",
        workspace_id=uuid4(),
        user_id=uuid4(),
        url=None,
        description=DESCRIPTION,
        name="Ana's workspace",
        brand_name="Crumb and Crust",
    )

    drafted = await pipeline._description_voice_generator(DESCRIPTION)

    assert drafted.brand_name == "Crumb and Crust"
    given = asked["messages"][1].content
    # The workspace's own name is a label ("Ana's workspace"): it is not offered as the brand's.
    assert "The business is called: Crumb and Crust" in given
    assert "Ana's workspace" not in given
