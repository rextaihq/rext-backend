"""
An AI provider outage: the account out of credits, a rate limit, its servers failing or out of reach,
or its key refused (G75, revnix/rext-control#611).

On 2026-10-07 staging's OpenAI account ran out of credits: every free tool answered 500, and nothing
told a person. Each of these errors is one condition here, a ProviderOutage, so that:
- a free tool answers 503 with a Retry-After and "busy, try again" instead of a 500;
- the team hears of it once an hour per provider and kind, through an error-level log, which Sentry
  turns into an event, instead of once per failed request or not at all.

The provider's own exceptions are recognised wherever they surface, including when another error
wraps them, so no call site has to change how it calls the model.
"""

import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Optional

import openai
import sentry_sdk

logger = logging.getLogger(__name__)

# What a caller is told, and when to try again.
BUSY_MESSAGE = "This tool is busy right now; try again in a few minutes."
RETRY_AFTER_SECONDS = 300

# One alert per provider and kind in this interval; every other occurrence is a warning.
ALERT_INTERVAL_SECONDS = 3600

INSUFFICIENT_QUOTA = "insufficient_quota"
RATE_LIMITED = "rate_limited"
SERVER_ERROR = "server_error"
UNREACHABLE = "unreachable"
KEY_REJECTED = "key_rejected"
# Said by a step itself (ProviderUnavailable), not read from a provider's error: the model's
# answer couldn't be used after a second attempt (a runaway or a cut-off, src.flow.model.runaway),
# or the step failed with nothing to hand on. The run ends with the notice; nobody is alerted.
UNREADABLE_ANSWER = "unreadable_answer"
STEP_FAILED = "step_failed"


@dataclass(frozen=True)
class ProviderOutage:
    provider: str
    kind: str
    detail: str


class ProviderUnavailable(Exception):
    """Raised where code wants to say so itself; provider_outage reads it like the provider's own errors."""

    def __init__(self, outage: ProviderOutage):
        super().__init__(f"{outage.provider} is unavailable ({outage.kind}): {outage.detail}")
        self.outage = outage


# A provider's message can name the key (masked but for its end) and the organisation: neither goes in a log line.
_SECRETISH = re.compile(r"\b(?:sk|org|proj)-[\w*-]+")


def _detail(error: BaseException) -> str:
    return _SECRETISH.sub("[redacted]", str(error))[:300]


# An empty account: OpenAI's type for it, and the code it sent on 2026-10-07 ("You have no credits remaining").
_QUOTA_CODES = {INSUFFICIENT_QUOTA, "credit_balance_exhausted"}


def _error_codes(error: openai.APIError) -> set:
    """The error's code and type, wherever the body carries them (top level or under "error")."""
    body = error.body if isinstance(error.body, dict) else {}
    nested = body.get("error") if isinstance(body.get("error"), dict) else {}
    found = {error.code, getattr(error, "type", None)}
    for part in (body, nested):
        found |= {part.get("code"), part.get("type")}
    return {c for c in found if isinstance(c, str)}


def _kind(error: BaseException) -> Optional[str]:
    if isinstance(error, openai.RateLimitError):
        return INSUFFICIENT_QUOTA if _error_codes(error) & _QUOTA_CODES else RATE_LIMITED
    if isinstance(error, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return KEY_REJECTED
    if isinstance(error, openai.APIStatusError) and error.status_code >= 500:
        return SERVER_ERROR
    if isinstance(error, openai.APIConnectionError):  # a timeout is one too
        return UNREACHABLE
    return None


def provider_outage(error: BaseException, provider: str = "OpenAI") -> Optional[ProviderOutage]:
    """The outage an error is, or wraps (its cause and context, a few levels deep); None for any other error."""
    seen = set()
    current: Optional[BaseException] = error
    while current is not None and id(current) not in seen and len(seen) < 8:
        seen.add(id(current))
        if isinstance(current, ProviderUnavailable):
            return current.outage
        kind = _kind(current)
        if kind is not None:
            return ProviderOutage(provider=provider, kind=kind, detail=_detail(current))
        current = current.__cause__ or current.__context__
    return None


_last_alert: dict = {}
_alert_lock = threading.Lock()


def report_provider_outage(outage: ProviderOutage) -> bool:
    """Alert the team, at most once an hour per provider and kind; True when this call alerted."""
    key = (outage.provider, outage.kind)
    now = time.monotonic()
    with _alert_lock:
        last = _last_alert.get(key)
        if last is not None and now - last < ALERT_INTERVAL_SECONDS:
            logger.warning("%s is unavailable (%s); alerted already", outage.provider, outage.kind)
            return False
        _last_alert[key] = now
    with sentry_sdk.new_scope() as scope:
        scope.set_tag("provider", outage.provider)
        scope.set_tag("provider_error", outage.kind)
        logger.error(
            "AI provider unavailable: %s (%s). Free tools answer 503 and runs stop until it's back. %s",
            outage.provider,
            outage.kind,
            outage.detail,
        )
    return True
