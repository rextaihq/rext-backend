"""A Google or GitHub sign-in is the account its provider says it is.

The sign-in call carries the provider's access token. The provider is asked about it, and the
account's id and email come from that answer: what the request names is compared with it, never
taken in its place. An account is linked or opened only on an email the provider vouches for.
The providers are stood in for by a transport; nothing leaves the machine.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from src.api.middleware.exceptions import RextAuthenticationException
from src.api.security import provider_identity
from src.api.security.provider_identity import (
    ProviderRefused,
    ProviderUnavailable,
    checked_sign_in,
)
from src.services.oauth_service import OAuthService

OUR_APP = "our-app.apps.googleusercontent.com"
TOKEN = "the-token-the-provider-gave"


@pytest.fixture
def providers(monkeypatch):
    """Google and GitHub as a transport: what each answers, and what each was asked."""
    world = SimpleNamespace(
        google={
            "aud": OUR_APP,
            "azp": OUR_APP,
            "sub": "108000000000000000001",
            "email": "Ana@Example.com",
            "email_verified": "true",
        },
        google_status=200,
        github_user={"id": 4242, "login": "ana", "email": None},
        github_status=200,
        github_emails=[
            {"email": "ana@example.com", "primary": True, "verified": True},
            {"email": "work@example.com", "primary": False, "verified": True},
            {"email": "old@example.com", "primary": False, "verified": False},
        ],
        github_emails_status=200,
        asked=[],
        fails=None,
        settings=SimpleNamespace(
            GOOGLE_SIGN_IN_CLIENT_ID=OUR_APP,
            GITHUB_SIGN_IN_CLIENT_ID="our-github-app",
            GITHUB_SIGN_IN_CLIENT_SECRET="our-github-app-secret",
            PROVIDER_SIGN_IN_CHECK="enforce",
        ),
    )

    def respond(request: httpx.Request) -> httpx.Response:
        world.asked.append(request)
        if world.fails is not None:
            raise world.fails
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(world.google_status, json=world.google)
        if request.url.path == "/applications/our-github-app/token":
            # GitHub's own check of a token, asked as our app: 404 for a token not made for it.
            return httpx.Response(world.github_status, json={"user": world.github_user})
        return httpx.Response(world.github_emails_status, json=world.github_emails)

    monkeypatch.setattr(
        provider_identity,
        "_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    )
    monkeypatch.setattr(provider_identity, "get_settings", lambda: world.settings)
    return world


# Google


@pytest.mark.asyncio
async def test_a_google_sign_in_is_the_account_google_names(providers):
    signed_in = await checked_sign_in("google", "108000000000000000001", "ana@example.com", TOKEN)

    assert signed_in.account_id == "108000000000000000001"
    assert (signed_in.email, signed_in.email_verified) == ("ana@example.com", True)
    # The token travels in the body, in no address a log would keep.
    (asked,) = providers.asked
    assert asked.method == "POST" and TOKEN not in str(asked.url)


@pytest.mark.asyncio
async def test_another_persons_email_in_the_request_is_not_taken(providers):
    # The token is Ana's; the request names someone else's address.
    signed_in = await checked_sign_in(
        "google", "108000000000000000001", "victim@example.com", TOKEN
    )

    assert signed_in.email == "ana@example.com"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"google_status": 400}, "not accepted"),
        ({"google": {"aud": "another-app", "azp": "another-app", "sub": "1"}}, "another app"),
        ({"google": {"aud": OUR_APP, "email": "ana@example.com"}}, "names no account"),
    ],
)
async def test_a_google_token_that_is_not_ours_to_trust_is_refused(providers, change, reason):
    for name, value in change.items():
        setattr(providers, name, value)

    with pytest.raises(ProviderRefused, match=reason):
        await checked_sign_in("google", "108000000000000000001", "ana@example.com", TOKEN)


@pytest.mark.asyncio
async def test_an_account_id_the_token_does_not_belong_to_is_refused(providers):
    with pytest.raises(ProviderRefused, match="another account"):
        await checked_sign_in("google", "999999999999999999999", "ana@example.com", TOKEN)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "unset"),
    [
        ("google", "GOOGLE_SIGN_IN_CLIENT_ID"),
        ("github", "GITHUB_SIGN_IN_CLIENT_ID"),
        ("github", "GITHUB_SIGN_IN_CLIENT_SECRET"),
    ],
)
async def test_without_our_apps_ids_the_provider_is_not_asked(providers, provider, unset):
    # A token can't be told ours from another app's without them, so nothing is decided.
    setattr(providers.settings, unset, None)

    with pytest.raises(ProviderUnavailable, match="not set"):
        await checked_sign_in(provider, "4242", "ana@example.com", TOKEN)
    assert providers.asked == []


@pytest.mark.asyncio
async def test_an_email_google_has_not_confirmed_is_not_vouched_for(providers):
    providers.google = {**providers.google, "email_verified": "false"}

    signed_in = await checked_sign_in("google", "108000000000000000001", "ana@example.com", TOKEN)

    assert (signed_in.email, signed_in.email_verified) == ("ana@example.com", False)


# GitHub


@pytest.mark.asyncio
async def test_a_github_sign_in_takes_its_primary_confirmed_email(providers):
    signed_in = await checked_sign_in("github", "4242", "someone@else.example", TOKEN)

    assert (signed_in.account_id, signed_in.email, signed_in.email_verified) == (
        "4242",
        "ana@example.com",
        True,
    )
    # First GitHub's own check, asked as our app with the token in the body; then the addresses.
    check, addresses = providers.asked
    assert check.method == "POST" and check.headers["authorization"].startswith("Basic ")
    assert TOKEN not in str(check.url)
    assert addresses.headers["authorization"] == f"Bearer {TOKEN}"


@pytest.mark.asyncio
async def test_a_second_confirmed_github_email_may_be_the_one_named(providers):
    signed_in = await checked_sign_in("github", "4242", "Work@Example.com", TOKEN)

    assert (signed_in.email, signed_in.email_verified) == ("work@example.com", True)


@pytest.mark.asyncio
async def test_an_unconfirmed_github_email_is_never_the_one_used(providers):
    signed_in = await checked_sign_in("github", "4242", "old@example.com", TOKEN)

    assert signed_in.email == "ana@example.com"


@pytest.mark.asyncio
async def test_a_github_token_that_may_not_read_emails_vouches_for_none(providers):
    providers.github_emails_status = 404
    providers.github_user = {"id": 4242, "login": "ana", "email": "public@example.com"}

    signed_in = await checked_sign_in("github", "4242", "ana@example.com", TOKEN)

    # It can still sign in where it is linked (by its id); nothing is opened on this address.
    assert (signed_in.account_id, signed_in.email_verified) == ("4242", False)


@pytest.mark.asyncio
async def test_a_github_token_not_made_for_our_app_is_refused(providers):
    # Another app's token for the same person: GitHub's check, asked as our app, answers 404.
    providers.github_status = 404

    with pytest.raises(ProviderRefused, match="not accepted"):
        await checked_sign_in("github", "4242", "ana@example.com", TOKEN)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_our_own_github_sign_in_refused_decides_nothing(providers, status):
    providers.github_status = status

    with pytest.raises(ProviderUnavailable, match="our app's sign-in"):
        await checked_sign_in("github", "4242", "ana@example.com", TOKEN)


# Either


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "token", "reason"),
    [
        ("google", None, "no token"),
        ("google", "   ", "no token"),
        ("facebook", TOKEN, "not a provider"),
    ],
)
async def test_nothing_to_ask_about_is_refused(providers, provider, token, reason):
    with pytest.raises(ProviderRefused, match=reason):
        await checked_sign_in(provider, "1", "ana@example.com", token)
    assert providers.asked == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "trouble",
    [httpx.ConnectTimeout("no answer"), httpx.ConnectError("no route"), 503, 429],
)
async def test_a_provider_that_cannot_be_asked_is_not_a_refusal(providers, trouble):
    if isinstance(trouble, int):
        providers.google_status = trouble
    else:
        providers.fails = trouble

    with pytest.raises(ProviderUnavailable):
        await checked_sign_in("google", "108000000000000000001", "ana@example.com", TOKEN)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"google_status": 400},
        {"fails": httpx.ConnectTimeout("no answer")},
        {"google": {"aud": OUR_APP, "sub": "another-account", "email": "x@example.com"}},
    ],
)
async def test_reporting_only_lets_the_sign_in_through_and_says_so(providers, change, caplog):
    providers.settings.PROVIDER_SIGN_IN_CHECK = "report"
    for name, value in change.items():
        setattr(providers, name, value)

    with caplog.at_level("WARNING"):
        signed_in = await checked_sign_in(
            "google", "108000000000000000001", "Ana@Example.com", TOKEN
        )

    # What the request named, as before the check existed; the log has the reason and no more.
    assert (signed_in.account_id, signed_in.email) == ("108000000000000000001", "ana@example.com")
    assert "reporting only" in caplog.text
    assert TOKEN not in caplog.text and "ana@example.com" not in caplog.text.lower()


# The two routes that take a provider account from a request


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("trouble", "status"),
    [(ProviderRefused("the token is not accepted"), 401), (ProviderUnavailable("timeout"), 503)],
)
async def test_the_routes_answer_a_refusal_and_a_silent_provider_apart(
    monkeypatch, trouble, status
):
    from src.api.routes.users import auth as routes

    monkeypatch.setattr(routes, "checked_sign_in", AsyncMock(side_effect=trouble))
    asked = SimpleNamespace(
        provider="google", provider_account_id="1", provider_email="a@example.com", access_token="t"
    )

    with pytest.raises(Exception) as refused:
        await routes._as_the_provider_says(asked)

    assert refused.value.status_code == status


def test_signing_in_and_linking_both_ask_the_provider():
    import inspect

    from src.api.routes.users import auth as routes

    # Each builds on the checked account, never on the body's id.
    for route in (routes.oauth_login, routes.link_oauth):
        source = inspect.getsource(inspect.unwrap(route))
        assert "_as_the_provider_says(oauth_data)" in source
        assert "provider_account_id=oauth_data.provider_account_id" not in source


@pytest.mark.asyncio
async def test_the_whole_asking_has_one_limit(providers, monkeypatch):
    import asyncio

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.2)
        return httpx.Response(200, json={"user": providers.github_user})

    monkeypatch.setattr(
        provider_identity,
        "_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(slow)),
    )
    # Two calls of 0.2 s each are over a limit of 0.3 s, though neither is by itself.
    monkeypatch.setattr(provider_identity, "PROVIDER_TIMEOUT_SECONDS", 0.3)

    with pytest.raises(ProviderUnavailable, match="no answer in time"):
        await checked_sign_in("github", "4242", "ana@example.com", TOKEN)


@pytest.mark.parametrize(
    ("named", "logged"),
    [("google", "google"), (" GitHub ", "github"), ("ana@example.com\nINFO forged", "unknown")],
)
def test_a_log_line_names_a_provider_we_ask_or_unknown(named, logged):
    assert provider_identity.provider_label(named) == logged


# What the sign-in does with it


def _service_finding(*, linked, user):
    """The service over a stand-in session: no link for this provider account unless `linked`,
    and `user` as the user holding the email."""
    answers = [linked, user]
    db = AsyncMock()
    db.add = Mock()
    db.asked = []

    async def execute(statement, *_, **__):
        db.asked.append(str(statement))
        found = answers.pop(0) if answers else None
        return SimpleNamespace(
            scalar_one_or_none=lambda: found,
            scalars=lambda: SimpleNamespace(
                first=lambda: found,
                all=lambda: found if isinstance(found, list) else ([found] if found else []),
            ),
        )

    db.execute = execute
    return OAuthService(db), db


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_user", [SimpleNamespace(id="someone"), None])
async def test_nothing_is_linked_or_opened_on_an_unconfirmed_email(existing_user):
    service, db = _service_finding(linked=None, user=existing_user)

    with pytest.raises(RextAuthenticationException, match="has not confirmed this email"):
        await service.oauth_login_or_register(
            provider="github",
            provider_account_id="4242",
            provider_email="ana@example.com",
            provider_name="Ana",
            email_verified=False,
        )

    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_an_existing_user_is_found_by_email_in_any_case(monkeypatch):
    registered = SimpleNamespace(
        id="ana", email="Ana@example.com", login_count=0, last_login_at=None, is_active=True
    )
    service, db = _service_finding(linked=None, user=registered)
    # The link is as far as this looks: what follows it (sessions, tokens) is the service's own.
    monkeypatch.setattr(db, "flush", AsyncMock(side_effect=RuntimeError("far enough")))

    with pytest.raises(RuntimeError, match="far enough"):
        await service.oauth_login_or_register(
            provider="google",
            provider_account_id="108000000000000000001",
            provider_email="ana@example.com",
            provider_name="Ana",
            email_verified=True,
        )

    # "Ana@example.com" registered by hand is the same person: the link is made, no second user.
    assert "lower(users.email)" in db.asked[1]
    (linked,) = (call.args[0] for call in db.add.call_args_list)
    assert linked.user_id == "ana"


def _user(id, email):
    return SimpleNamespace(id=id, email=email)


@pytest.mark.parametrize(
    ("stored", "picked"),
    [
        ([], None),
        ([("ana", "Ana@example.com")], "ana"),
        # Two addresses that differ by case only: the one written exactly as the provider's.
        ([("old", "Ana@example.com"), ("exact", "ana@example.com")], "exact"),
    ],
)
def test_the_user_an_email_belongs_to(stored, picked):
    users = [_user(*one) for one in stored]

    found = OAuthService._the_one_with_this_email(users, "ana@example.com")

    assert (found.id if found else None) == picked


def test_two_users_by_case_and_neither_exact_is_nobodys_to_pick():
    users = [_user("one", "Ana@example.com"), _user("two", "ANA@example.com")]

    with pytest.raises(RextAuthenticationException, match="More than one account"):
        OAuthService._the_one_with_this_email(users, "ana@example.com")


@pytest.mark.asyncio
async def test_googles_other_shape_of_answer_is_read_too(providers):
    providers.google = {
        "issued_to": OUR_APP,
        "audience": OUR_APP,
        "user_id": "108000000000000000001",
        "email": "ana@example.com",
        "verified_email": True,
    }

    signed_in = await checked_sign_in("google", "108000000000000000001", "ana@example.com", TOKEN)

    assert (signed_in.email, signed_in.email_verified) == ("ana@example.com", True)


@pytest.mark.asyncio
@pytest.mark.parametrize("header", [{"x-ratelimit-remaining": "0"}, {"retry-after": "30"}])
async def test_githubs_spent_rate_limit_is_not_a_word_on_the_token(providers, monkeypatch, header):
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"user": providers.github_user})
        return httpx.Response(403, headers=header, json={"message": "rate limit"})

    monkeypatch.setattr(
        provider_identity,
        "_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(respond)),
    )

    # Not "this account has no confirmed email": the addresses could not be asked for.
    with pytest.raises(ProviderUnavailable, match="rate limit"):
        await checked_sign_in("github", "4242", "ana@example.com", TOKEN)


# The call that carries the dashboard's key says so


@pytest.mark.asyncio
async def test_a_call_with_the_dashboards_key_leaves_a_line_that_holds_no_key(monkeypatch, caplog):
    from src.api.security import dashboard_server

    key = "k" * 40
    monkeypatch.setattr(dashboard_server, "came_from_the_dashboards_server", lambda request: True)
    monkeypatch.setattr(
        dashboard_server, "_provider_account", AsyncMock(return_value="google:1080001")
    )
    request = SimpleNamespace(state=SimpleNamespace(), headers={"X-Rext-Dashboard-Key": key})

    with caplog.at_level("INFO"):
        await dashboard_server.dashboard_sign_in_gate(request)

    assert "with the dashboard's key: counted per account" in caplog.text
    assert key not in caplog.text and "1080001" not in caplog.text
    assert request.state.rate_limit_identity == "oauth:google:1080001"
