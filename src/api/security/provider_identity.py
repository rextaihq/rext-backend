"""Who a Google or GitHub sign-in is, as the provider says.

A sign-in with a provider ends with a call that carries the provider's access token. This module
asks the provider about that token and answers with the account's id and its email as the
provider gives them, and with whether the provider vouches for that email. The sign-in is built
on that answer: what the request's body names is compared with it, never taken in its place.

- Google: one call to its token-information endpoint, which also names the app the token was made
  for: it must be ours (GOOGLE_SIGN_IN_CLIENT_ID).
- GitHub: its token check, made with our app's own sign-in (GITHUB_SIGN_IN_CLIENT_ID and
  GITHUB_SIGN_IN_CLIENT_SECRET), which answers only for a token made for our app; then the
  account's email addresses. An address counts only when GitHub marks it verified.

A token made for another app is never accepted, so the app's ids must be set: without them the
provider is not asked and the sign-in is not decided (see checked_sign_in for "report").

Nothing here logs a token, an email or an account id.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from src.api.config import get_settings
from src.utils.logger import logger

GOOGLE_TOKEN_INFO = "https://oauth2.googleapis.com/tokeninfo"
GITHUB_TOKEN_CHECK = "https://api.github.com/applications/{client_id}/token"
GITHUB_EMAILS = "https://api.github.com/user/emails"

# A sign-in waits on these calls: a provider that is slow is not waited for. One limit for the
# whole asking, however many calls it takes.
PROVIDER_TIMEOUT_SECONDS = 6.0
# An account's addresses are read a hundred at a time, to this many pages.
GITHUB_EMAIL_PAGES = 5

PROVIDERS = ("google", "github")


@dataclass(frozen=True)
class ProviderIdentity:
    """An account as its provider describes it."""

    account_id: str
    email: Optional[str]
    # The provider says this address belongs to the account's owner.
    email_verified: bool
    # Every address the provider vouches for (GitHub accounts can hold several).
    verified_emails: tuple[str, ...] = ()


class ProviderRefused(Exception):
    """The provider doesn't accept the token, or it was made for another app."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ProviderUnavailable(Exception):
    """The provider could not be asked: no answer in time, an error of its own, or our app's
    ids for it are not set here."""


def provider_label(provider: Any) -> str:
    """A provider's name for a log line: one that is asked, or "unknown". Never the raw text of
    a request."""
    name = _lower(provider)
    return name if name in PROVIDERS else "unknown"


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=PROVIDER_TIMEOUT_SECONDS)


async def _ask(client: httpx.AsyncClient, method: str, url: str, **kwargs: Any) -> httpx.Response:
    try:
        response = await client.request(method, url, **kwargs)
    except httpx.HTTPError as exc:
        raise ProviderUnavailable(type(exc).__name__) from exc
    if response.status_code >= 500 or response.status_code == 429:
        raise ProviderUnavailable(f"status {response.status_code}")
    if response.status_code == 403 and (
        response.headers.get("x-ratelimit-remaining") == "0"
        or "retry-after" in response.headers
        or "rate limit" in response.text.lower()
    ):
        # GitHub answers a spent rate limit with 403 as well as 429, and its second kind of
        # limit with neither header, only its words: not a word on the token.
        raise ProviderUnavailable("the provider's rate limit")
    return response


def _json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise ProviderUnavailable("an answer that is not JSON") from exc


def _lower(value: Any) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


async def _google(client: httpx.AsyncClient, access_token: str) -> ProviderIdentity:
    expected = (get_settings().GOOGLE_SIGN_IN_CLIENT_ID or "").strip()
    if not expected:
        raise ProviderUnavailable("GOOGLE_SIGN_IN_CLIENT_ID is not set")
    # Sent in the body, so the token is in no address a proxy or a log would keep.
    response = await _ask(client, "POST", GOOGLE_TOKEN_INFO, data={"access_token": access_token})
    if response.status_code != 200:
        raise ProviderRefused("the token is not accepted")
    told = _json(response)
    if not isinstance(told, dict):
        raise ProviderUnavailable("an answer of another shape")

    # Google's token information comes in two shapes, by the version that answers: `aud`, `azp`,
    # `sub` and `email_verified`, or `audience`, `issued_to`, `user_id` and `verified_email`.
    # The app that asked for the token (`azp` / `issued_to`) is the one that counts when Google
    # names it; a token another client asked for is not ours even if it is addressed to us.
    asked_by = told.get("azp") or told.get("issued_to")
    made_for = asked_by or told.get("aud") or told.get("audience")
    if made_for != expected:
        raise ProviderRefused("the token was made for another app")

    account_id = str(told.get("sub") or told.get("user_id") or "").strip()
    if not account_id:
        raise ProviderRefused("the token names no account")
    email = _lower(told.get("email")) or None
    vouched = told.get("email_verified", told.get("verified_email"))
    verified = bool(email) and str(vouched).lower() == "true"
    return ProviderIdentity(
        account_id=account_id,
        email=email,
        email_verified=verified,
        verified_emails=(email,) if email and verified else (),
    )


async def _github(client: httpx.AsyncClient, access_token: str) -> ProviderIdentity:
    settings = get_settings()
    client_id = (settings.GITHUB_SIGN_IN_CLIENT_ID or "").strip()
    client_secret = (settings.GITHUB_SIGN_IN_CLIENT_SECRET or "").strip()
    if not client_id or not client_secret:
        raise ProviderUnavailable("GITHUB_SIGN_IN_CLIENT_ID and _SECRET are not set")
    api = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}

    # GitHub's own check of a token, asked as our app: it answers only for a token that was made
    # for our app, and says whose it is.
    response = await _ask(
        client,
        "POST",
        GITHUB_TOKEN_CHECK.format(client_id=client_id),
        auth=(client_id, client_secret),
        headers=api,
        json={"access_token": access_token},
    )
    if response.status_code in (401, 403):
        # Our app's own sign-in was not accepted: nothing can be asked until it is set right.
        raise ProviderUnavailable("our app's sign-in was not accepted by GitHub")
    if response.status_code == 422:
        # GitHub's answer when it holds this check back as asked too often: no word on the token.
        raise ProviderUnavailable("GitHub is holding the token check back")
    if response.status_code != 200:
        raise ProviderRefused("the token is not accepted")
    checked = _json(response)
    account = checked.get("user") if isinstance(checked, dict) else None
    if not isinstance(account, dict) or not account.get("id"):
        raise ProviderRefused("the token names no account")
    headers = {**api, "Authorization": f"Bearer {access_token}"}

    # The account's addresses, when the token may read them. Without that, no address is
    # vouched for: the account can still sign in by its id, and is linked to nothing by email.
    primary: Optional[str] = None
    verified: list[str] = []
    for page in range(1, GITHUB_EMAIL_PAGES + 1):
        listed = await _ask(
            client, "GET", GITHUB_EMAILS, headers=headers, params={"per_page": 100, "page": page}
        )
        entries = _json(listed) if listed.status_code == 200 else None
        if not isinstance(entries, list):
            break
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("verified"):
                continue
            address = _lower(entry.get("email"))
            if not address:
                continue
            verified.append(address)
            if entry.get("primary"):
                primary = address
        if len(entries) < 100:
            break
    email = primary or (verified[0] if verified else None)
    return ProviderIdentity(
        account_id=str(account["id"]),
        email=email or _lower(account.get("email")) or None,
        email_verified=email is not None,
        verified_emails=tuple(verified),
    )


async def provider_identity(provider: str, access_token: Optional[str]) -> ProviderIdentity:
    """The account behind `access_token`, asked of `provider`.

    Raises ProviderRefused when the provider doesn't accept the token (or there is none, or the
    provider is not one that is asked), and ProviderUnavailable when it could not be asked.
    """
    name = _lower(provider)
    if name not in PROVIDERS:
        raise ProviderRefused("not a provider that is asked")
    token = (access_token or "").strip()
    if not token:
        raise ProviderRefused("no token to ask about")

    async def asked() -> ProviderIdentity:
        async with _client() as client:
            if name == "google":
                return await _google(client, token)
            return await _github(client, token)

    try:
        return await asyncio.wait_for(asked(), timeout=PROVIDER_TIMEOUT_SECONDS)
    except asyncio.TimeoutError as exc:
        raise ProviderUnavailable("no answer in time") from exc


@dataclass(frozen=True)
class CheckedSignIn:
    """What a provider sign-in goes ahead with."""

    # The provider under its one name ("google", "github"), however the request spelled it.
    provider: str
    account_id: str
    email: str
    # An existing account is linked by its email only when this is true.
    email_verified: bool


async def checked_sign_in(
    provider: str,
    claimed_account_id: str,
    claimed_email: str,
    access_token: Optional[str],
) -> CheckedSignIn:
    """The account id and email a provider sign-in uses: the provider's own.

    The request's `claimed_account_id` must be the one the provider names for the token. The
    email is the claimed one when the provider vouches for it for this account, otherwise the
    provider's own for the account, and it counts as verified only on the provider's word. An
    account is created, or linked to an existing user by email, only on a verified one.

    With PROVIDER_SIGN_IN_CHECK set to "report", a sign-in the check would refuse is logged and
    goes ahead on what the request says, as before the check existed: for watching the check on
    real sign-ins before it decides them.

    Raises ProviderRefused or ProviderUnavailable (never in "report").
    """
    reporting = get_settings().PROVIDER_SIGN_IN_CHECK == "report"
    claimed = CheckedSignIn(
        provider=_lower(provider),
        account_id=claimed_account_id,
        email=_lower(claimed_email),
        email_verified=True,
    )
    try:
        identity = await provider_identity(provider, access_token)
        if identity.account_id != str(claimed_account_id).strip():
            raise ProviderRefused("the token belongs to another account than the one named")
    except (ProviderRefused, ProviderUnavailable) as exc:
        if not reporting:
            raise
        logger.warning(
            "A provider sign-in would be refused by the provider check (reporting only)",
            extra={
                "provider": provider_label(provider),
                "reason": str(exc),
                "kind": type(exc).__name__,
            },
        )
        return claimed

    email = _lower(claimed_email)
    if email and email in identity.verified_emails:
        return CheckedSignIn(
            provider=_lower(provider),
            account_id=identity.account_id,
            email=email,
            email_verified=True,
        )
    if reporting:
        # Enforcing, this address would not count as the account's confirmed one (another
        # address than the provider's, or one it has not confirmed). Reporting says so and goes
        # on as before the check existed.
        logger.warning(
            "A provider sign-in names an email the provider does not vouch for (reporting only)",
            extra={"provider": provider_label(provider)},
        )
        return claimed
    # No address the provider vouches for: the account can still sign in where it is already
    # linked (that goes by its id), and nothing is created or linked on an address unvouched.
    return CheckedSignIn(
        provider=_lower(provider),
        account_id=identity.account_id,
        email=identity.email or email,
        email_verified=bool(identity.email) and identity.email_verified,
    )
