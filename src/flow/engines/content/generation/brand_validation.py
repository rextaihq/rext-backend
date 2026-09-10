"""Decode-time brand validation for the generated content model.

The brand rules already reach the writer twice — as prompt prose and as schema
directives — and are enforced after generation by `validate_content` ->
`repair_content`. This module adds a third point: the model's own Pydantic
validation, so a response that ignores the approved promotion is caught at the
moment it is decoded and corrected inside the same agent turn, rather than only
after a full validate/repair round trip.

Why raising here is safe
------------------------
`create_content_agent` wraps the generated model in
`ToolStrategy(model, handle_errors=True)`. A `ValidationError` there is not a
crash: LangChain converts it to `StructuredOutputValidationError`, decides to
retry, and hands the message back to the model as a `ToolMessage`. No Pydantic
error can reach the caller.

What makes it *bounded* is the budget below. Without one, a rule the model cannot
satisfy would retry until the graph's `recursion_limit` killed the run — every
attempt regenerating a very long article. So the budget is small, explicit, and
**self-disarming**: once spent, the validator returns the content unchanged
forever after and the existing repair loop takes over with its own
`MAX_REPAIR_ATTEMPTS`. Enforcement is added, never traded away.

The default is no budget at all, so a caller that has not opted in — tests, any
other code path that builds one of these models — never sees a raise.

No rules are defined here. The checks are `validation.py`'s, the policy is
`brand_placement_policy.py`'s, and the correction text is the same structural
anchor the prompt and schema already carry.
"""

from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager
from typing import Any, Callable, Optional

from src.flow.model.structure.contents.base import blocks_to_body_markdown

logger = logging.getLogger(__name__)

# Remaining in-agent retries, as a one-element list so the validator can spend
# from it without rebinding the ContextVar. A ContextVar rather than a module
# global because articles generate concurrently: ContextVars are task-local and
# propagate into the child asyncio tasks LangGraph runs the agent in, so one
# article's budget can never be spent by another's.
#
# `None` means "not opted in" — the validator observes and logs, and never raises.
_RETRY_BUDGET: contextvars.ContextVar[Optional[list[int]]] = contextvars.ContextVar(
    "brand_retry_budget", default=None
)

# Checks whose failure is worth a regeneration. Both come from validation.py; the
# order is the order the model should fix them in — being absent matters more
# than being in the wrong place.
_ENFORCED_CHECKS = ("check_brand_presence", "check_brand_placement_policy")


@contextmanager
def brand_retry_budget(attempts: int = 1):
    """Allow the brand validator to reject up to `attempts` responses.

    Outside this context the validator never raises, which is what keeps the
    behaviour opt-in: only the generation node grants a budget, and it grants a
    small one.
    """
    token = _RETRY_BUDGET.set([max(0, attempts)])
    try:
        yield
    finally:
        _RETRY_BUDGET.reset(token)


async def with_brand_retry_budget(attempts: int, stream):
    """Wrap an agent event stream so the brand validator may reject `attempts` responses.

    A wrapper rather than a `with` block around the consuming loop purely to keep
    the change at the call site to one line — the budget is set before the first
    event is pulled and reset once the stream is exhausted or raises, which is
    exactly the window the agent runs in.
    """
    token = _RETRY_BUDGET.set([max(0, attempts)])
    try:
        async for event in stream:
            yield event
    finally:
        _RETRY_BUDGET.reset(token)


def _spend_budget() -> bool:
    """True if a rejection is still affordable (and consumes it)."""
    budget = _RETRY_BUDGET.get()
    if not budget or budget[0] <= 0:
        return False
    budget[0] -= 1
    return True


def build_brand_spec_slice(outline: dict, content_type: str) -> Optional[dict]:
    """The brand-only part of the requirements spec, or None when not applicable.

    A slice rather than the whole spec on purpose. The model this feeds is cached
    and reused across articles of the same content type and brand, so anything
    article-specific left in the closure (word counts, expected sections, the
    approved link list) would be read stale on the next article. The three keys
    below are all the brand checks read, and all of them are keyed by the cache
    signature.
    """
    from src.flow.engines.content.generation.requirements_spec import build_requirements_spec

    try:
        spec = build_requirements_spec(outline, content_type)
    except Exception:
        logger.exception(
            "brand_validation: could not build requirements spec for content_type=%s; "
            "decode-time brand validation disabled for this article.",
            content_type,
        )
        return None

    if not spec.get("brand_context"):
        return None
    return {
        "brand_context": spec.get("brand_context"),
        "brand_placement": spec.get("brand_placement"),
        "brand_placement_policy": spec.get("brand_placement_policy"),
    }


def _blocking_failure(payload: dict, spec: dict) -> Optional[dict]:
    """The first blocking brand failure in `payload`, or None.

    Imported lazily: validation.py imports structured_body at module level, and
    structured_body is what attaches this validator, so a module-level import
    here would close the cycle.

    Only `blocking` failures count. `check_brand_placement_policy` deliberately
    returns `warning` for softer cases (a body-only type whose mention drifted
    into the introduction), and `repair_content` acts only on blocking failures —
    retrying a whole article over something the rest of the pipeline tolerates
    would spend the budget on a stylistic nit.
    """
    from src.flow.engines.content.generation import validation as _validation

    for check_name in _ENFORCED_CHECKS:
        check: Callable[[dict, Any], dict] = getattr(_validation, check_name, None)
        if check is None:  # pragma: no cover - guards a rename in validation.py
            logger.warning("brand_validation: %s not found in validation.py; skipping.", check_name)
            continue
        try:
            result = check(payload, spec)
        except Exception:
            # A check that blows up must not fail the article. Skip it and let
            # the post-generation run of the same check report properly.
            logger.exception("brand_validation: %s raised; treating as passed.", check_name)
            continue
        if not result.get("passed") and result.get("severity") == "blocking":
            return result
    return None


def build_brand_validator(
    blocks: list,
    spec: dict,
    content_type: str,
    brand_name: str,
) -> Callable:
    """A `mode="after"` validator enforcing this article's brand requirements.

    Assembles the generated blocks with the same helper the payload assembler
    uses, so what is graded here is exactly what would be published — there is no
    second view of the article that could disagree.
    """
    from src.flow.engines.content.generation.brand_placement_policy import (
        build_brand_structural_injection,
    )

    def _validate_brand(self):
        try:
            ordered = [(b.key, getattr(self, b.key, None)) for b in blocks]
            payload = {
                "introduction": getattr(self, "introduction", "") or "",
                "body_markdown": blocks_to_body_markdown(ordered),
            }
            failure = _blocking_failure(payload, spec)
        except Exception:
            # Validation is a safety net, never a tripwire: if it cannot run, the
            # article proceeds and the post-generation checks still apply.
            logger.exception("brand_validation: validator failed; accepting content as-is.")
            return self

        if failure is None:
            return self

        if not _spend_budget():
            # Budget spent, or none granted. Accept the content and let
            # validate_content -> repair_content handle it with the full article
            # in hand — it is better at placement edits than a blind retry, and
            # it has its own bounded attempt count.
            logger.warning(
                "brand_validation: %s still failing for content_type=%s and no retry budget "
                "remains; passing to the repair loop. Detail: %s",
                failure.get("name"),
                content_type,
                failure.get("detail"),
            )
            return self

        anchor = build_brand_structural_injection(content_type, brand_name)
        logger.info(
            "brand_validation: rejecting response for content_type=%s (%s); requesting a retry.",
            content_type,
            failure.get("name"),
        )
        raise ValueError(
            f"BRAND REQUIREMENT NOT MET — {failure.get('detail')} "
            f"{anchor.strip()} "
            f"Rewrite the affected section so this is satisfied, and change nothing else."
        )

    return _validate_brand
