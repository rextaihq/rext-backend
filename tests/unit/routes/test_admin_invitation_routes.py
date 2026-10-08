"""Platform admin invitations, through their routes (revnix/rext-control#915).

A super admin invites an address to a platform role; the invited person gets an email
with a link, signs in with that address and accepts; the role is theirs. Checked on the
test PostgreSQL inside a rolled-back transaction: the routes' commits and rollbacks act
on a savepoint inside it. The roles are real rows; the email service is an outbox.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import src.services.admin_invitation_emails as emails_module
from src.api.database.async_database import get_async_db
from src.api.database.base import Base
from src.api.middleware.rate_limiter import EndpointRateLimiter
from src.api.models.admin_models.admin_invitations import PlatformAdminInvitations
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.security.dependencies import get_current_user
from tests.conftest import TEST_DATABASE_URL

pytestmark = pytest.mark.asyncio

ADMIN_URL = "/api/v1/admin/platform/invitations"
PUBLIC_URL = "/api/v1/admin-invitations"
LEVELS = {"super_admin": 100, "admin": 80, "support": 3, "workspace_owner": 60}


def _with_parents(*tables):
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


@pytest_asyncio.fixture
async def connection():
    """One connection inside a transaction that is rolled back at the end. Every session
    on it (the test's own, and one per request as in production) commits to a savepoint."""
    tables = _with_parents(
        Users.__table__,
        Role.__table__,
        UserRole.__table__,
        WorkspaceModel.__table__,
        PlatformAdminInvitations.__table__,
        AuditLog.__table__,
    )
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as conn:
        transaction = await conn.begin()

        def tables_unless_migrated(sync):
            if not inspect(sync).has_table("alembic_version"):
                Base.metadata.create_all(sync, tables=tables, checkfirst=True)

        await conn.run_sync(tables_unless_migrated)
        yield conn
        await transaction.rollback()
    await engine.dispose()


def _session_on(connection) -> AsyncSession:
    return AsyncSession(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )


@pytest_asyncio.fixture
async def session(connection):
    """The test's own session, for what it sets up and reads back."""
    async with _session_on(connection) as db:
        yield db


@pytest.fixture
def outbox(monkeypatch):
    """The emails handed to the email service, in place of sending them. With ``fails``
    set, a send comes back as failed (the service records that and doesn't raise)."""
    box = SimpleNamespace(sent=[], fails=False)

    class _Emails:
        def __init__(self, _db):
            pass

        async def send_email(self, **email):
            box.sent.append(email)
            return SimpleNamespace(status="failed" if box.fails else "sent")

    monkeypatch.setattr(emails_module, "EmailService", _Emails)
    return box


async def _role(db, name: str) -> Role:
    """The role of that name: the seeded one where the database has it, or one made here."""
    role = (await db.execute(select(Role).where(Role.name == name))).scalar_one_or_none()
    if role is None:
        role = Role(
            name=name,
            display_name=name.replace("_", " ").title(),
            hierarchy_level=LEVELS[name],
            is_workspace_role=name.startswith("workspace"),
        )
        db.add(role)
        await db.flush()
    return role


async def _person(db, *roles: str, email=None, verified=True, name="Ada Admin"):
    """An account with those platform roles: its id and address, as plain values."""
    user = Users(
        email=email or f"{uuid4().hex[:12]}@example.com",
        display_name=name,
        email_verified=verified,
    )
    db.add(user)
    await db.flush()
    for role_name in roles:
        db.add(UserRole(user_id=user.id, role_id=(await _role(db, role_name)).id))
    await db.commit()
    return SimpleNamespace(id=user.id, email=user.email)


@pytest.fixture
def call(connection, monkeypatch):
    """call(caller, method, url, json=None, *, impersonating=False, permissions=()) ->
    response, as that signed-in account (or as nobody, with caller None). Each request
    has a session of its own, as in production. The roles and the super-admin check are
    the real ones; ``permissions`` are what the caller's roles give it."""
    from src.api.server import app

    async def override_db():
        async with _session_on(connection) as db:
            yield db

    async def no_limit(self, request: Request):
        return None

    monkeypatch.setattr(EndpointRateLimiter, "__call__", no_limit)

    async def _call(caller, method, url, json=None, *, impersonating=False, permissions=()):
        async def held(*_args, **_kwargs):
            return list(permissions)

        monkeypatch.setattr("src.utils.rbac_utils.get_user_permissions", held)
        app.dependency_overrides[get_async_db] = override_db
        if caller is not None:
            app.dependency_overrides[get_current_user] = lambda: {
                "identity": str(caller.id),
                "roles": [],
                "is_impersonating": impersonating,
            }
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                return await ac.request(method, url, json=json)
        finally:
            app.dependency_overrides.clear()

    return _call


def _invite(email: str, role: str = "admin", **fields) -> dict:
    return {"email": email, "admin_role": role, **fields}


async def _rows(db, email: str) -> list[PlatformAdminInvitations]:
    found = await db.execute(
        select(PlatformAdminInvitations)
        .where(PlatformAdminInvitations.email == email.lower())
        .execution_options(populate_existing=True)
    )
    return list(found.scalars())


async def _platform_roles(db, user) -> set[str]:
    found = await db.execute(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user.id, UserRole.workspace_id.is_(None))
    )
    return set(found.scalars())


async def _validate(call, token: str):
    return await call(None, "POST", f"{PUBLIC_URL}/validate", {"token": token})


async def _accept(call, account, token: str, **session):
    return await call(account, "POST", f"{PUBLIC_URL}/accept", {"token": token}, **session)


async def _decline(call, token: str, reason: str = "No"):
    return await call(None, "POST", f"{PUBLIC_URL}/decline", {"token": token, "reason": reason})


def _token_in(email: dict) -> str:
    return email["html"].split("/accept-admin-invitation?token=")[1].split('"')[0].split("<")[0]


# Creating


@pytest.mark.parametrize("role", ["super_admin", "admin", "support"])
async def test_a_super_admin_invites_each_platform_role_and_the_email_goes_out(
    session, call, outbox, role
):
    """What failed on live: the answer was built from the row after it was written, by
    reading the inviter and unset columns the async session would not read there."""
    founder = await _person(session, "super_admin", name="Ada Admin")
    await _role(session, role)
    invited = f"{uuid4().hex[:10]}@Example.com"

    response = await call(founder, "POST", ADMIN_URL, _invite(invited, role, message="Welcome."))

    assert response.status_code == 201, response.text
    answer = response.json()["data"]
    assert (answer["email"], answer["admin_role"], answer["status"]) == (
        invited.lower(),
        role,
        "pending",
    )
    assert answer["invited_by_name"] == "Ada Admin"
    assert answer["can_be_accepted"] is True
    assert "invitation_token" not in answer

    (row,) = await _rows(session, invited)
    assert row.status == "pending" and len(row.invitation_token) >= 48

    (email,) = outbox.sent
    assert email["to"] == invited.lower()
    assert email["template_type"] == "admin_invitation"
    assert f"/accept-admin-invitation?token={row.invitation_token}" in email["html"]
    assert "Ada Admin" in email["html"] and "Welcome." in email["html"]


async def test_an_invitation_whose_email_cant_be_sent_is_not_stored(session, call, outbox):
    """The admin is told, and nothing is left behind: "sent" always means the person
    has the link."""
    founder = await _person(session, "super_admin")
    await _role(session, "admin")
    invited = f"{uuid4().hex[:10]}@example.com"
    outbox.fails = True

    response = await call(founder, "POST", ADMIN_URL, _invite(invited))

    assert response.status_code == 502
    assert "couldn't be sent" in response.json()["message"]
    assert await _rows(session, invited) == []

    # And once email works again, the same address can be invited.
    outbox.fails = False
    assert (await call(founder, "POST", ADMIN_URL, _invite(invited))).status_code == 201


@pytest.mark.parametrize("roles", [("admin",), ("support",), ("workspace_owner",), ()])
async def test_only_a_super_admin_can_invite(session, call, outbox, roles):
    caller = await _person(session, *roles)
    await _role(session, "admin")
    invited = f"{uuid4().hex[:10]}@example.com"

    response = await call(caller, "POST", ADMIN_URL, _invite(invited))

    assert response.status_code == 403
    assert await _rows(session, invited) == [] and outbox.sent == []


async def test_nobody_signed_out_can_invite_or_list(session, call, outbox):
    invite = await call(None, "POST", ADMIN_URL, _invite("signed-out@example.com"))
    listing = await call(None, "GET", ADMIN_URL)

    assert 400 <= invite.status_code < 500 and 400 <= listing.status_code < 500
    assert await _rows(session, "signed-out@example.com") == [] and outbox.sent == []


@pytest.mark.parametrize("rows", [("super_admin", "admin"), ("super_admin", "super_admin")])
async def test_a_super_admin_with_two_platform_role_rows_still_opens_the_page_and_invites(
    session, call, outbox, rows
):
    """On live two accounts hold two role rows outside any workspace (nothing in the table
    stops a second one), and the check "is this account a super admin" raised on finding
    more than one: the page didn't open and nothing could be sent."""
    founder = await _person(session, *rows)
    await _role(session, "admin")
    invited = f"{uuid4().hex[:10]}@example.com"

    listing = await call(founder, "GET", f"{ADMIN_URL}?limit=100&offset=0")
    made = await call(founder, "POST", ADMIN_URL, _invite(invited))

    assert listing.status_code == 200, listing.text
    assert made.status_code == 201, made.text
    assert len(outbox.sent) == 1


@pytest.mark.parametrize("role", ["support_admin", "platform_admin", "workspace_owner", "editor"])
async def test_a_role_that_isnt_a_platform_role_is_refused(session, call, outbox, role):
    """The screen once offered two names no role has. Only the three platform roles can
    be given by an invitation, whatever else the roles table holds."""
    founder = await _person(session, "super_admin")
    await _role(session, "workspace_owner")

    response = await call(founder, "POST", ADMIN_URL, _invite("new@example.com", role))

    assert response.status_code == 422
    assert outbox.sent == []


async def test_an_address_with_a_pending_invitation_isnt_invited_twice(session, call, outbox):
    founder = await _person(session, "super_admin")
    await _role(session, "admin")
    invited = f"{uuid4().hex[:10]}@example.com"
    assert (await call(founder, "POST", ADMIN_URL, _invite(invited))).status_code == 201

    await _role(session, "support")
    again = await call(founder, "POST", ADMIN_URL, _invite(invited.upper(), "support"))

    assert again.status_code == 409
    assert len(await _rows(session, invited)) == 1 and len(outbox.sent) == 1


@pytest.mark.parametrize(
    ("holds", "invited_as", "refused"),
    [
        (("admin",), "admin", True),
        (("admin",), "super_admin", True),
        (("super_admin",), "support", True),
        (("super_admin", "admin"), "admin", True),
        (("support",), "support", True),
        (("support",), "admin", False),
        (("workspace_owner",), "admin", False),
    ],
)
async def test_an_address_that_already_holds_a_platform_role(
    session, call, outbox, holds, invited_as, refused
):
    """An account that is an admin already isn't invited again, and one that holds the
    very role invited isn't either, whatever the letter case of the address. A support
    account can be invited to a higher role; a customer's own roles don't count."""
    founder = await _person(session, "super_admin")
    await _role(session, invited_as)
    there = await _person(session, *holds, email=f"{uuid4().hex[:10]}@example.com")

    response = await call(founder, "POST", ADMIN_URL, _invite(there.email.upper(), invited_as))

    assert response.status_code == (400 if refused else 201), response.text
    assert len(outbox.sent) == (0 if refused else 1)


# Listing, reading, resending, revoking


async def test_the_list_and_one_invitation_read_back_with_their_people(session, call, outbox):
    founder = await _person(session, "super_admin", name="Ada Admin")
    await _role(session, "admin")
    await _role(session, "support")
    first, second = f"{uuid4().hex[:10]}@example.com", f"{uuid4().hex[:10]}@example.com"
    made = await call(founder, "POST", ADMIN_URL, _invite(first))
    await call(founder, "POST", ADMIN_URL, _invite(second, "support"))
    invitation_id = made.json()["data"]["id"]
    await call(founder, "DELETE", f"{ADMIN_URL}/{invitation_id}", {"reason": "Wrong address"})

    listed = await call(founder, "GET", ADMIN_URL)
    pending = await call(founder, "GET", f"{ADMIN_URL}?status=pending")
    one = await call(founder, "GET", f"{ADMIN_URL}/{invitation_id}")

    assert listed.status_code == pending.status_code == one.status_code == 200
    emails = {row["email"]: row for row in listed.json()["data"]["invitations"]}
    assert {first, second} <= set(emails)
    assert emails[first]["invited_by_name"] == "Ada Admin"
    assert [row["email"] for row in pending.json()["data"]["invitations"] if row["email"] in emails]
    assert first not in {row["email"] for row in pending.json()["data"]["invitations"]}
    revoked = one.json()["data"]
    assert (revoked["status"], revoked["revoked_by_name"], revoked["revoked_reason"]) == (
        "revoked",
        "Ada Admin",
        "Wrong address",
    )
    assert revoked["can_be_accepted"] is False


async def test_a_resend_sends_a_new_link_and_the_old_one_stops_working(session, call, outbox):
    founder = await _person(session, "super_admin")
    await _role(session, "admin")
    invited = f"{uuid4().hex[:10]}@example.com"
    made = await call(founder, "POST", ADMIN_URL, _invite(invited))
    old = _token_in(outbox.sent[0])

    resent = await call(
        founder, "POST", f"{ADMIN_URL}/{made.json()['data']['id']}/resend", {"expiry_days": 14}
    )

    assert resent.status_code == 200, resent.text
    new = _token_in(outbox.sent[1])
    assert new != old and len(outbox.sent) == 2
    assert (await _validate(call, old)).json()["data"]["valid"] is False
    assert (await _validate(call, new)).json()["data"]["valid"] is True


async def test_a_resend_whose_email_cant_be_sent_leaves_the_old_link(session, call, outbox):
    founder = await _person(session, "super_admin")
    await _role(session, "admin")
    invited = f"{uuid4().hex[:10]}@example.com"
    made = await call(founder, "POST", ADMIN_URL, _invite(invited))
    old = _token_in(outbox.sent[0])
    outbox.fails = True

    resent = await call(founder, "POST", f"{ADMIN_URL}/{made.json()['data']['id']}/resend", {})

    assert resent.status_code == 502
    (row,) = await _rows(session, invited)
    assert row.invitation_token == old


# Opening the link


async def test_the_link_says_who_invited_whom_to_what(session, call, outbox):
    founder = await _person(session, "super_admin", name="Ada Admin")
    await _role(session, "support")
    invited = f"{uuid4().hex[:10]}@example.com"
    await call(founder, "POST", ADMIN_URL, _invite(invited, "support", message="Welcome."))

    opened = await _validate(call, _token_in(outbox.sent[0]))

    seen = opened.json()["data"]
    assert (seen["valid"], seen["email"], seen["admin_role"]) == (True, invited, "support")
    assert (seen["invited_by_name"], seen["message"]) == ("Ada Admin", "Welcome.")


async def test_a_link_that_was_never_sent_says_nothing(session, call):
    opened = await _validate(call, uuid4().hex)

    seen = opened.json()["data"]
    assert (seen["valid"], seen["email"], seen["admin_role"]) == (False, "", "")


# Accepting


async def _invited(session, call, outbox, role="admin", **person):
    founder = await _person(session, "super_admin")
    await _role(session, role)
    account = await _person(session, **person)
    made = await call(founder, "POST", ADMIN_URL, _invite(account.email, role))
    assert made.status_code == 201, made.text
    return founder, account, _token_in(outbox.sent[-1]), made.json()["data"]["id"]


@pytest.mark.parametrize("role", ["super_admin", "admin", "support"])
async def test_accepting_gives_the_invited_account_the_role_once(session, call, outbox, role):
    _, account, token, _ = await _invited(session, call, outbox, role, name="Grace")

    accepted = await _accept(call, account, token)

    assert accepted.status_code == 200, accepted.text
    answer = accepted.json()["data"]
    assert (answer["status"], answer["accepted_by_name"]) == ("accepted", "Grace")
    assert await _platform_roles(session, account) == {role}

    # The token is used up: a second try changes nothing.
    again = await _accept(call, account, token)
    assert again.status_code == 400
    assert await _platform_roles(session, account) == {role}
    assert (await _validate(call, token)).json()["data"]["valid"] is False


async def test_accepting_drops_the_accounts_cached_permissions_once_the_role_is_stored(
    session, call, outbox, monkeypatch
):
    """Or the new admin is refused until the cache runs out. Dropped before the role is
    stored, a request in between would cache the old set again."""
    _, account, token, _ = await _invited(session, call, outbox, "support")
    someone_else = await _person(session)
    steps = []
    commit = AsyncSession.commit

    async def stored(self):
        await commit(self)
        steps.append("stored")

    async def dropped(pattern):
        steps.append(pattern)
        return 0

    monkeypatch.setattr(AsyncSession, "commit", stored)
    monkeypatch.setattr("src.api.routes.admin.admin_invitation_routes.invalidate_cache", dropped)

    assert (await _accept(call, someone_else, token)).status_code == 400
    assert steps == []

    assert (await _accept(call, account, token)).status_code == 200
    assert steps[:2] == ["stored", f"user:permissions:{account.id}:*"]


async def test_an_account_with_another_address_cant_accept(session, call, outbox):
    _, account, token, _ = await _invited(session, call, outbox, "super_admin")
    someone_else = await _person(session)

    refused = await _accept(call, someone_else, token)

    assert refused.status_code == 400
    assert await _platform_roles(session, someone_else) == set()
    assert await _platform_roles(session, account) == set()
    # The invitation still stands for the account it names.
    assert (await _accept(call, account, token)).status_code == 200


async def test_nobody_signed_out_can_accept(session, call, outbox):
    _, account, token, _ = await _invited(session, call, outbox)

    refused = await _accept(call, None, token)

    assert 400 <= refused.status_code < 500
    assert await _platform_roles(session, account) == set()


async def test_an_address_that_isnt_verified_cant_accept(session, call, outbox):
    """The role goes to whoever proved the address is theirs."""
    _, account, token, _ = await _invited(session, call, outbox, verified=False)

    refused = await _accept(call, account, token)

    assert refused.status_code == 400
    assert "Verify your email" in refused.json()["message"]
    assert await _platform_roles(session, account) == set()


async def test_an_expired_invitation_cant_be_accepted(session, call, outbox):
    _, account, token, invitation_id = await _invited(session, call, outbox)
    (row,) = await _rows(session, account.email)
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await session.commit()

    refused = await _accept(call, account, token)

    assert refused.status_code == 400
    assert await _platform_roles(session, account) == set()


async def test_a_revoked_invitation_cant_be_accepted(session, call, outbox):
    founder, account, token, invitation_id = await _invited(session, call, outbox)
    revoked = await call(founder, "DELETE", f"{ADMIN_URL}/{invitation_id}", {"reason": "No"})
    assert revoked.status_code == 200

    refused = await _accept(call, account, token)

    assert refused.status_code == 400
    assert await _platform_roles(session, account) == set()


async def test_a_declined_invitation_cant_be_accepted(session, call, outbox):
    _, account, token, _ = await _invited(session, call, outbox)
    declined = await _decline(call, token, "Not me")
    assert declined.status_code == 200

    refused = await _accept(call, account, token)

    assert refused.status_code == 400
    assert await _platform_roles(session, account) == set()


async def test_an_admin_acting_as_the_invited_account_cant_accept_for_it(session, call, outbox):
    """An impersonated session has the invited account's identity and address. The role
    is given only in that person's own session."""
    _, account, token, _ = await _invited(session, call, outbox, "super_admin")

    refused = await _accept(call, account, token, impersonating=True)

    assert refused.status_code == 403
    assert await _platform_roles(session, account) == set()
    # The invitation isn't spent by the attempt.
    assert (await _accept(call, account, token)).status_code == 200


async def test_an_account_made_an_admin_since_isnt_raised_by_an_old_link(session, call, outbox):
    """Inviting an admin to a higher role is refused when the invitation is made. The same
    holds when the account became an admin after it: the old link doesn't raise it."""
    _, account, token, _ = await _invited(session, call, outbox, "super_admin")
    session.add(UserRole(user_id=account.id, role_id=(await _role(session, "admin")).id))
    await session.commit()

    refused = await _accept(call, account, token)

    assert refused.status_code == 400
    assert await _platform_roles(session, account) == {"admin"}


async def test_an_accepted_invitation_cant_be_declined_revoked_or_sent_again(session, call, outbox):
    founder, account, token, invitation_id = await _invited(session, call, outbox)
    assert (await _accept(call, account, token)).status_code == 200

    declined = await _decline(call, token)
    revoked = await call(founder, "DELETE", f"{ADMIN_URL}/{invitation_id}", {"reason": "Late"})
    resent = await call(founder, "POST", f"{ADMIN_URL}/{invitation_id}/resend", {})

    assert (declined.status_code, revoked.status_code, resent.status_code) == (400, 400, 400)
    (row,) = await _rows(session, account.email)
    assert row.status == "accepted" and row.invitation_token == token
    assert await _platform_roles(session, account) == {"admin"}
    assert len(outbox.sent) == 1


async def test_reading_invitations_is_a_super_admins_even_with_the_permission(
    session, call, outbox
):
    """An admin's role holds the permission these routes ask for (user.invite). The
    invitations name people and carry their inviter's words: only a super admin reads them."""
    _, account, token, invitation_id = await _invited(session, call, outbox)
    an_admin = await _person(session, "admin")
    may = {"permissions": ["user.invite"]}

    listed = await call(an_admin, "GET", ADMIN_URL, **may)
    one = await call(an_admin, "GET", f"{ADMIN_URL}/{invitation_id}", **may)
    made = await call(an_admin, "POST", ADMIN_URL, _invite("new@example.com"), **may)

    assert (listed.status_code, one.status_code, made.status_code) == (403, 403, 403)
    assert account.email not in listed.text and account.email not in one.text


async def test_a_token_is_never_part_of_a_routes_path(session, call, outbox):
    """A path is written to the request log and the error log as it is, so the token
    travels in the body. The older forms with the token in the path are gone."""
    _, account, token, _ = await _invited(session, call, outbox)

    old_validate = await call(None, "GET", f"{PUBLIC_URL}/{token}/validate")
    old_accept = await call(account, "POST", f"{PUBLIC_URL}/{token}/accept")
    old_decline = await call(None, "POST", f"{PUBLIC_URL}/{token}/decline", {"reason": "x"})

    assert {old_validate.status_code, old_accept.status_code, old_decline.status_code} <= {
        404,
        405,
    }
    assert await _platform_roles(session, account) == set()
    (row,) = await _rows(session, account.email)
    assert row.status == "pending"


async def test_only_a_super_admin_can_revoke_or_resend(session, call, outbox):
    _, account, token, invitation_id = await _invited(session, call, outbox)
    an_admin = await _person(session, "admin")

    assert (await call(an_admin, "DELETE", f"{ADMIN_URL}/{invitation_id}", {})).status_code == 403
    assert (
        await call(an_admin, "POST", f"{ADMIN_URL}/{invitation_id}/resend", {})
    ).status_code == 403
    (row,) = await _rows(session, account.email)
    assert row.status == "pending" and row.invitation_token == token
