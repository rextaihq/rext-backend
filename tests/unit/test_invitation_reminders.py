"""The daily invitation reminders: who gets one, once, and what the email holds."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import src.api.tasks.invitation_reminder_task as task
from src.api.database.base import Base
from src.api.models.user_models.invitations import UserInvitations
from src.api.models.user_models.roles import Role
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from tests.conftest import TEST_DATABASE_URL

NOW = datetime.now(timezone.utc)


def _with_parents(*tables):
    """The tables, and every table their foreign keys reach."""
    found = []

    def visit(table):
        if table in found:
            return
        found.append(table)
        for key in table.foreign_keys:
            visit(key.column.table)

    for table in tables:
        visit(table)
    return found


def _tables_for_an_unmigrated_database(sync, tables) -> None:
    """Make the tables on an empty test database only: a migrated one (CI's) is tested as
    its migrations built it."""
    if inspect(sync).has_table("alembic_version"):
        return
    Base.metadata.create_all(sync, tables=tables, checkfirst=True)


@pytest_asyncio.fixture
async def db():
    """The tables these tests need, inside a transaction that is rolled back. The job
    commits each reminder: here a commit only releases a savepoint."""
    tables = _with_parents(
        Users.__table__, Role.__table__, WorkspaceModel.__table__, UserInvitations.__table__
    )
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        await connection.run_sync(lambda sync: _tables_for_an_unmigrated_database(sync, tables))
        async with AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as session:
            yield session
        await transaction.rollback()
    await engine.dispose()


@pytest.fixture
def outbox(monkeypatch):
    """The emails the job hands to the email service, in place of sending them. An
    address in ``fails`` comes back as a send that failed (it is recorded, not raised)."""
    sent = []
    fails = set()

    class _Emails:
        def __init__(self, _db):
            pass

        async def send_email(self, **email):
            sent.append(email)
            return SimpleNamespace(status="failed" if email["to"] in fails else "sent")

    monkeypatch.setattr(task, "EmailService", _Emails)
    return SimpleNamespace(sent=sent, fails=fails)


async def _workspace(db, name="Acme", inviter_name="Ana"):
    inviter = Users(email=f"{uuid4().hex[:12]}@example.com", display_name=inviter_name)
    role = Role(name=f"editor-{uuid4().hex[:8]}", display_name="Editor", is_workspace_role=True)
    db.add_all([inviter, role])
    await db.flush()
    workspace = WorkspaceModel(user_id=inviter.id, name=name, slug=f"acme-{uuid4().hex[:8]}")
    db.add(workspace)
    await db.flush()
    return workspace, role, inviter


async def _invitation(db, place, *, expires_in: timedelta, **columns) -> UserInvitations:
    workspace, role, inviter = place
    invitation = UserInvitations(
        email=f"{uuid4().hex[:12]}@example.com",
        workspace_id=workspace.id,
        role_id=role.id,
        invited_by_user_id=inviter.id,
        invitation_token=uuid4().hex,
        expires_at=NOW + expires_in,
        **columns,
    )
    db.add(invitation)
    await db.commit()
    return invitation


@pytest.mark.asyncio
async def test_an_invitation_two_days_from_expiry_gets_one_reminder(db, outbox):
    place = await _workspace(db)
    due = await _invitation(db, place, expires_in=timedelta(hours=40))

    assert await task.send_invitation_reminders(db) == 1

    assert [email["to"] for email in outbox.sent] == [due.email]
    assert outbox.sent[0]["template_type"] == "invitation_reminder"
    assert due.invitation_token in outbox.sent[0]["html"]
    assert due.reminder_sent is True

    # The next day's run finds nothing left to send.
    assert await task.send_invitation_reminders(db) == 0
    assert len(outbox.sent) == 1


@pytest.mark.asyncio
async def test_only_a_pending_invitation_inside_the_two_days_is_reminded(db, outbox):
    place = await _workspace(db)
    await _invitation(db, place, expires_in=timedelta(days=5))
    await _invitation(db, place, expires_in=-timedelta(hours=1))
    await _invitation(db, place, expires_in=timedelta(hours=20), status="accepted")
    await _invitation(db, place, expires_in=timedelta(hours=20), reminder_sent=True)

    assert await task.send_invitation_reminders(db) == 0
    assert outbox.sent == []


@pytest.mark.asyncio
async def test_an_email_that_fails_is_not_marked_and_the_others_still_go(db, outbox):
    """A send that fails is recorded by the email service and doesn't raise. Its
    invitation stays unmarked, so the next run tries it again; the run goes on."""
    place = await _workspace(db)
    first = await _invitation(db, place, expires_in=timedelta(hours=10))
    second = await _invitation(db, place, expires_in=timedelta(hours=30))
    outbox.fails.add(first.email)

    assert await task.send_invitation_reminders(db) == 1

    assert [email["to"] for email in outbox.sent] == [first.email, second.email]
    assert (first.reminder_sent, second.reminder_sent) == (False, True)

    outbox.fails.clear()
    assert await task.send_invitation_reminders(db) == 1
    assert first.reminder_sent is True


@pytest.mark.asyncio
async def test_an_error_on_one_invitation_does_not_stop_the_run(db, outbox, monkeypatch):
    place = await _workspace(db)
    first = await _invitation(db, place, expires_in=timedelta(hours=10))
    second = await _invitation(db, place, expires_in=timedelta(hours=30))
    first_id, second_id = first.id, second.id
    remind = task._remind

    async def breaks_on_the_first(db, email_service, invitation, now, frontend_url):
        if invitation.id == first_id:
            raise RuntimeError("the template could not be rendered")
        return await remind(db, email_service, invitation, now, frontend_url)

    monkeypatch.setattr(task, "_remind", breaks_on_the_first)

    assert await task.send_invitation_reminders(db) == 1

    reminded = {
        row.id: row.reminder_sent
        for row in [
            await db.get(UserInvitations, first_id),
            await db.get(UserInvitations, second_id),
        ]
    }
    assert reminded == {first_id: False, second_id: True}


@pytest.mark.asyncio
async def test_an_invitation_to_a_deleted_workspace_gets_no_reminder(db, outbox):
    place = await _workspace(db)
    place[0].deleted_at = NOW - timedelta(days=1)
    invitation = await _invitation(db, place, expires_in=timedelta(hours=20))

    assert await task.send_invitation_reminders(db) == 0
    assert outbox.sent == []
    assert invitation.reminder_sent is False


@pytest.mark.asyncio
async def test_names_people_typed_reach_the_email_as_text(db, outbox):
    place = await _workspace(db, name="Acme <b>& Sons</b>", inviter_name='<a href="x">Ana</a>')
    await _invitation(db, place, expires_in=timedelta(hours=20))

    await task.send_invitation_reminders(db)

    html = outbox.sent[0]["html"]
    assert "Acme &lt;b&gt;&amp; Sons&lt;/b&gt;" in html
    assert "<b>& Sons</b>" not in html
    assert '<a href="x">Ana</a>' not in html
    # The subject is plain text: the name as it is.
    assert "Acme <b>& Sons</b>" in outbox.sent[0]["subject"]


@pytest.mark.asyncio
async def test_no_log_line_of_the_job_holds_an_address(db, outbox, caplog):
    place = await _workspace(db)
    invitation = await _invitation(db, place, expires_in=timedelta(hours=20))
    outbox.fails.add(invitation.email)

    with caplog.at_level("INFO"):
        await task.send_invitation_reminders(db)

    assert invitation.email not in caplog.text


@pytest.mark.asyncio
async def test_the_script_publishes_the_logo_before_it_sends(monkeypatch):
    """A run by hand has no server start behind it, where the logo is published."""
    import src.scripts.send_invitation_reminders as script

    order = []

    async def reminders() -> int:
        order.append("reminders")
        return 3

    monkeypatch.setattr(script, "publish_logo", lambda: order.append("logo") or True)
    monkeypatch.setattr(script, "run_invitation_reminders_task", reminders)

    assert await script.main() == 3
    assert order == ["logo", "reminders"]
