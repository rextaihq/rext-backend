import json
import logging
from uuid import UUID

from langchain_core.runnables import RunnableConfig

from src.flow.engines.content.generation.cta_labels import strip_cta_labels
from src.flow.states.rext import REXT
from src.services.check_wording import user_detail
from src.services.content_checklist import CONTENT_CHECKS_KEY, build_checklist

logger = logging.getLogger(__name__)


class ArticleNotSaved(RuntimeError):
    """The finished article couldn't be stored: the run ends as a failure, never as a success
    that left nothing in the library (G55). Its message is the one a person may see."""


def _as_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _check_rows(checks) -> list[dict]:
    # The saved detail is the reader's line (check_wording); the check's own detail is
    # written for the repair step and stays in the run's state.
    return [
        {
            "name": c.get("name"),
            "severity": c.get("severity"),
            "detail": user_detail(c.get("name"), c.get("detail")),
        }
        for c in checks or []
        if isinstance(c, dict)
    ]


def _rechecked_after_humanizing() -> set[str]:
    """The names of the checks the post-humanize pass runs again (each check
    reports the name its function carries after "check_")."""
    from src.flow.engines.content.generation.validation import FINAL_VALIDATE_CHECKS

    return {fn.__name__.removeprefix("check_") for fn in FINAL_VALIDATE_CHECKS}


def _validation_summary(review: dict) -> dict | None:
    """The validator's verdict on the article as saved.

    The post-humanize check, when there is one, decides for the checks it runs
    again. It runs only a subset, so a failure the pre-humanize gate gave up on
    in a check it does not rerun (required sections, internal links, the CTA)
    is carried forward rather than dropped; without a final check, the gate's
    own verdict stands (its gave_up means its repairs ran out).
    """
    pre = review.get("validation") or {}
    final = review.get("final_validation") or {}
    result = final or pre
    if not result:
        return None
    issues = _check_rows(result.get("failed_checks"))
    warnings = _check_rows(result.get("warnings"))
    gave_up = bool(result.get("gave_up"))
    if final and pre:
        rechecked = _rechecked_after_humanizing()
        carried = [
            row for row in _check_rows(pre.get("failed_checks")) if row["name"] not in rechecked
        ]
        issues += carried
        gave_up = gave_up or bool(carried)
    return {
        "passed": not issues,
        "gave_up": gave_up,
        "stage": result.get("stage"),
        "issues": issues,
        "warnings": warnings,
    }


def _claims_to_verify(state: REXT, content_state: dict) -> list[dict]:
    """Factual claims in the final text that nothing the run verified supports.

    The validator reports these as one repair instruction; this re-runs the same
    deterministic finder on the text actually saved (after humanizing and the
    last repair) so the checklist can list them one by one. Never raises.
    """
    try:
        from src.flow.engines.content.generation.claim_integrity import find_unsupported_claims
        from src.flow.engines.content.generation.focus_keyword import resolve_focus_keyword
        from src.flow.engines.content.generation.requirements_spec import build_requirements_spec

        final = content_state.get("final_content") or {}
        spec = build_requirements_spec(
            content_state.get("outline") or {},
            content_state.get("content_type", ""),
            resolve_focus_keyword(state),
            content_state.get("selected_topic") or "",
            generation_meta=content_state.get("generation_meta") or {},
        )
        # The same three fields check_unsupported_claims scans.
        text = "\n".join(
            str(final.get(field) or "")
            for field in ("meta_description", "introduction", "body_markdown")
        )
        claims = find_unsupported_claims(text, spec.get("claim_evidence") or {})
        return [
            {"category": c.category, "sentence": c.sentence, "unsupported": c.span} for c in claims
        ]
    except Exception:  # noqa: BLE001 - the checklist never breaks a save
        logger.exception("persist_content: could not list the claims to verify")
        return []


async def persist_content(state: REXT, config: RunnableConfig) -> dict:
    """Auto-save the finished article to the Content library as a draft.

    Runs as the final node so a generation the user backgrounded (or never
    watched) still lands in the library without a manual Save. Idempotent by
    langgraph_thread_id — re-runs update the same row instead of duplicating.
    A save that fails ends the run as a failure (ArticleNotSaved): a run that
    "succeeded" with nothing saved lost the article without a word.
    """
    content_state = state.get("content") or {}
    # The saved copy (and so the WordPress export) never carries an outline CTA label
    # line, whichever node last wrote the article.
    final = strip_cta_labels(
        content_state.get("final_content") or {},
        content_state.get("outline"),
        stage="persist_content",
    )
    # The user-selected title is the single source of truth for what is saved.
    # final_content.title should already equal it (every mutating node re-locks
    # it), but persistence is the last write, so it reads the selection itself.
    title = content_state.get("selected_topic") or final.get("title")
    body_markdown = final.get("body_markdown")
    if not (title and body_markdown):
        logger.warning("persist_content: missing title/body; skipping save")
        return {}

    serp = state.get("serp_payload") or {}
    user_id = serp.get("user_id")
    workspace_id = serp.get("workspace_id")
    thread_id = (config.get("configurable") or {}).get("thread_id")
    if not (user_id and workspace_id and thread_id):
        logger.warning("persist_content: missing user/workspace/thread; skipping save")
        return {}

    try:
        workspace_uuid = UUID(str(workspace_id))
        user_uuid = UUID(str(user_id))
        thread_uuid = UUID(str(thread_id))
    except (TypeError, ValueError):
        logger.warning("persist_content: non-UUID user/workspace/thread; skipping save")
        return {}

    review = content_state.get("review") or {}
    on_page = (
        review.get("on_page_metrics") if isinstance(review.get("on_page_metrics"), dict) else {}
    )
    readability = (
        review.get("readability_metrics")
        if isinstance(review.get("readability_metrics"), dict)
        else {}
    )
    trust = review.get("trust_score") if isinstance(review.get("trust_score"), dict) else {}

    from src.api.database.async_database import get_pooled_langgraph_db_context
    from src.api.schema.content_schema import ContentCreate, ContentSEODataSchema

    # The pinned user query wins over anything on the payload. The previous
    # order put `primary_keyword` first, which is a model-written field, so a
    # model-invented phrase could still be persisted as the focus keyphrase even
    # after generate_content had corrected `focus_keyphrase` itself.
    from src.flow.engines.content.generation.focus_keyword import resolve_focus_keyword
    from src.services.content_service import ContentService
    from src.utils.loop_bridge import run_on_main_loop

    focus_keyphrase = (
        resolve_focus_keyword(state)
        or final.get("focus_keyphrase")
        or final.get("primary_keyword")
        or serp.get("query")
        or ""
    )

    content_checks = {
        "validation": _validation_summary(review),
        "claims_to_verify": _claims_to_verify(state, content_state),
    }

    seo_data = ContentSEODataSchema(
        meta_title=title,
        meta_description=final.get("meta_description") or "",
        focus_keyphrase=focus_keyphrase,
        # Measured deterministically by the quality gate / on-page scoring
        # (keyword_density.py). The column already existed and was never
        # populated, so the UI had no density to show.
        keyphrase_density=_as_float(final.get("keyphrase_density")),
        secondary_keywords=final.get("secondary_keywords") or [],
        seo_score=_as_float(on_page.get("seo_health_score")),
        readability_score=_as_float(
            readability.get("flesch_reading_ease") or readability.get("score")
        ),
        trust_score=_as_float(trust.get("score")),
        # The on-page analysis, plus what the validator found, for the checklist
        # (src/services/content_checklist.py reads both back).
        seo_details=json.dumps({**on_page, CONTENT_CHECKS_KEY: content_checks}, default=str),
    )

    category_val = final.get("category")
    if isinstance(category_val, list):
        category_val = ", ".join(str(c) for c in category_val if c)
    elif category_val:
        category_val = str(category_val)
    else:
        category_val = None

    # The author persona the user kept or chose in the outline step. Saved on the
    # row so publishing (and every later republish) credits the same author; a
    # cleared persona stays cleared.
    persona_uuid = None
    outline_state = content_state.get("outline") or {}
    selected_persona_id = outline_state.get("selected_persona_id")
    if selected_persona_id:
        try:
            persona_uuid = UUID(str(selected_persona_id))
        except (TypeError, ValueError):
            logger.warning(
                "persist_content: ignoring non-UUID selected_persona_id %r", selected_persona_id
            )

    payload = ContentCreate(
        title=title,
        status="draft",
        content_language="English",
        introduction=final.get("introduction") or final.get("meta_description") or "",
        body_markdown=body_markdown,
        body_html=final.get("body_html") or final.get("html_content") or "",
        tags=final.get("tags") or [],
        category=category_val,
        seo_data=seo_data,
        langgraph_thread_id=thread_uuid,
        persona_id=persona_uuid,
    )

    try:

        async def _persist():
            async with get_pooled_langgraph_db_context() as db:
                service = ContentService(db)
                return await service.create_content(workspace_uuid, user_uuid, payload)

        content = await run_on_main_loop(_persist())
        logger.info("persist_content: saved article %s for thread %s", content.id, thread_id)
    except Exception as exc:
        logger.exception("persist_content: failed to save generated article")
        raise ArticleNotSaved("The article couldn't be saved to your library.") from exc

    from src.services.notification_helper import notify_now

    await notify_now(
        user_id=user_uuid,
        pref_flag="gen_completed",
        message=f'"{title}" has finished generating.',
        payload={"content_id": str(content.id), "thread_id": str(thread_uuid)},
        workspace_id=workspace_uuid,
    )

    # The same checklist the saved article's API response carries, for the
    # generation view that is still showing this run.
    checklist = build_checklist(
        readability_score=seo_data.readability_score, seo_details=seo_data.seo_details
    )
    return {"content": {"review": {"checklist": checklist}}}
