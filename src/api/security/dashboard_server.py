"""Whether a call comes from the dashboard's own server (rext-control#892).

The dashboard's server completes a Google or GitHub sign-in by calling
`POST /api/v1/user/oauth/login` once the provider has answered it. It sends a key with that
call, `DASHBOARD_SERVER_KEY`, in the header `X-Rext-Dashboard-Key`; both services hold the
same value.

- A call with the key is the dashboard's server speaking. It is counted by the rate limiter
  per provider account, so people signing in at the same time do not share one allowance.
- A call without it is counted by its address, as every call was before.
- With `REQUIRE_DASHBOARD_SERVER_KEY` on, a call without the key is refused.

The key is compared in constant time and never logged. A key shorter than
`MIN_KEY_LENGTH` counts as not set.
"""

import hashlib
import hmac

from fastapi import Request

from src.api.config import get_settings
from src.api.middleware.exceptions import RextAuthorizationException
from src.api.middleware.rate_limiter import key_for_logs
from src.utils.ip_allowlist import limiter_client_host
from src.utils.logger import logger

DASHBOARD_SERVER_HEADER = "X-Rext-Dashboard-Key"
MIN_KEY_LENGTH = 32

REFUSED = "Signing in with Google or GitHub is only possible from the Rext app."


def _configured_key() -> str | None:
    key = (get_settings().DASHBOARD_SERVER_KEY or "").strip()
    return key if len(key) >= MIN_KEY_LENGTH else None


def came_from_the_dashboards_server(request: Request) -> bool:
    """True when the call carries the key the dashboard's server holds."""
    expected = _configured_key()
    given = request.headers.get(DASHBOARD_SERVER_HEADER) or ""
    if not expected or not given:
        return False
    return hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))


async def _provider_account(request: Request) -> str | None:
    """The provider account a sign-in call names, as a short hash; None when it names none."""
    try:
        body = await request.json()  # cached by the framework: the route still reads it
        provider = str(body.get("provider") or "").strip().lower()
        account = str(body.get("provider_account_id") or "").strip()
    except Exception:  # noqa: BLE001 - a body that isn't JSON is the route's to refuse
        return None
    if not provider or not account:
        return None
    return hashlib.sha256(f"{provider}:{account}".encode()).hexdigest()[:16]


async def dashboard_sign_in_gate(request: Request) -> None:
    """Runs before the sign-in route's rate limit and decides how the call is counted."""
    if came_from_the_dashboards_server(request):
        account = await _provider_account(request)
        if account:
            request.state.rate_limit_identity = f"oauth:{account}"
        return

    caller = key_for_logs(f"ip:{limiter_client_host(request)}")
    if get_settings().REQUIRE_DASHBOARD_SERVER_KEY:
        if _configured_key() is None:
            logger.error(
                "REQUIRE_DASHBOARD_SERVER_KEY is on and DASHBOARD_SERVER_KEY is not set (or is "
                "under %d characters): every Google and GitHub sign-in is refused",
                MIN_KEY_LENGTH,
            )
        logger.warning(
            "Google or GitHub sign-in call without the dashboard's key: refused (%s)", caller
        )
        raise RextAuthorizationException(message=REFUSED)

    logger.info(
        "Google or GitHub sign-in call without the dashboard's key: counted by its address (%s)",
        caller,
    )
