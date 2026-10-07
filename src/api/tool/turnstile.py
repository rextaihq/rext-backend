"""
The free AI tools' bot check (G87): the rext.ai site's tool forms send a Cloudflare Turnstile token
in the request's JSON body (`turnstile_token`), and a tool that calls a model has Cloudflare verify
it before the call is counted or run. The tools without a model need no token.

- TURNSTILE_SECRET_KEY unset (local, the tests, until production has its key): no check. The server
  says so once as it starts.
- A missing or refused token: 403, with a message the site's tool pages show as it is. A token is
  good for one call, so the site's widget fetches a new one for the next.
- Cloudflare not answering (a timeout, a network error, a 5xx), or refusing the server's own
  secret: the call goes ahead (fail open), and the log says so. The per-visitor limit and the
  day's budget (limits.py) still bound what a bot can spend.
"""

import json
import time
from typing import Dict, Optional

import httpx
from fastapi import HTTPException, Request, status

from src.api.config import get_settings
from src.utils.logger import logger

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TOKEN_FIELD = "turnstile_token"
TIMEOUT_SECONDS = 3.0
# Cloudflare's tokens are at most 2,048 characters; anything longer is refused unasked.
MAX_TOKEN_LENGTH = 2048
REFUSED_MESSAGE = "We couldn't verify this request. Please reload the page and try again."
# Cloudflare's error codes that mean the server's setup is wrong, not the visitor's token.
SERVER_ERRORS = {"missing-input-secret", "invalid-input-secret", "internal-error"}
# The log says a fail-open case at most this often per kind, not once per call.
LOG_EVERY_SECONDS = 600

# Built once, at import: building a TLS context reads the CA bundle from disk, which would block the
# serving loop if each call did it.
_SSL_CONTEXT = httpx.create_ssl_context()
_logged_at: Dict[str, float] = {}


def _log_now(kind: str) -> bool:
    now = time.monotonic()
    if now - _logged_at.get(kind, float("-inf")) < LOG_EVERY_SECONDS:
        return False
    _logged_at[kind] = now
    return True


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(verify=_SSL_CONTEXT, timeout=TIMEOUT_SECONDS)


def _refused() -> HTTPException:
    exc = HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=REFUSED_MESSAGE)
    # A bot turned away is the check working, not an error: no Error Logs row for each one.
    exc.suppress_error_log = True
    return exc


async def _token(request: Request) -> Optional[str]:
    try:
        body = json.loads(await request.body() or b"null")
    except ValueError:
        return None
    token = body.get(TOKEN_FIELD) if isinstance(body, dict) else None
    return token if isinstance(token, str) and token else None


async def token_bytes(request: Request) -> int:
    """The bytes a well-formed token's field takes in the body, `,"turnstile_token":"..."`. None of
    it reaches a prompt, so the input limit and the worst-case cost leave it out."""
    token = await _token(request)
    if not token or len(token) > MAX_TOKEN_LENGTH:
        return 0
    return len(token.encode()) + len(TOKEN_FIELD) + len(',"":""')


async def verify_turnstile(request: Request, remote_ip: Optional[str]) -> None:
    """Refuse the call (403) unless Cloudflare accepts its token. `remote_ip` is the visitor's
    address when the server can trust it, which Cloudflare checks the token against."""
    secret = get_settings().TURNSTILE_SECRET_KEY
    if not secret:
        return
    token = await _token(request)
    if token is None or len(token) > MAX_TOKEN_LENGTH:
        raise _refused()
    form = {"secret": secret, "response": token}
    if remote_ip:
        form["remoteip"] = remote_ip
    try:
        async with _client() as client:
            response = await client.post(SITEVERIFY_URL, data=form)
        if response.status_code >= 500:
            raise httpx.HTTPStatusError("server error", request=response.request, response=response)
        result = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        if _log_now("unanswered"):
            logger.warning(
                f"Free tools: Cloudflare Turnstile didn't answer ({type(exc).__name__}), so the "
                "calls go ahead unchecked; the visitor limits and the budget still apply"
            )
        return
    if isinstance(result, dict) and result.get("success") is True:
        return
    codes = set(result.get("error-codes") or []) if isinstance(result, dict) else set()
    if codes & SERVER_ERRORS:
        if _log_now("server"):
            logger.error(
                "Free tools: Cloudflare Turnstile refused the server's setup "
                f"({', '.join(sorted(codes))}), so the calls go ahead unchecked: check "
                "TURNSTILE_SECRET_KEY"
            )
        return
    raise _refused()
