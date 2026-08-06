"""Standalone, on-demand SERP-based competitor discovery for a workspace.

Decoupled from workspace creation/refresh — this is a dedicated trigger for
re-running/backfilling competitor discovery independently, invoked from
`POST /workspaces/{id}/competitors/discover` and tracked via SSE using the
operation_id it returns. Results are read back separately via
`GET /workspaces/{id}/competitors`.
"""
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.knowledge_models.knowledge_model import BrandVoice
from src.services.sse_service import (
    emit_pipeline_complete,
    emit_step_failure,
    emit_step_start,
    emit_step_success,
)
from src.utils.helper import _looks_blocked, web_page_scraper
from src.utils.logger import logger

SCOPE = "competitors"


async def run_competitor_discovery_for_workspace(
    *,
    db: AsyncSession,
    operation_id: str,
    workspace_id: UUID,
    user_id: UUID,
    url: str,
) -> None:
    try:
        await emit_step_start(
            operation_id=operation_id, scope=SCOPE, step="scrape",
            message=f"Scraping {url}", progress=10, user_id=user_id,
        )

        _, results = await web_page_scraper(urls=[url])
        first_success = next((r for r in results or [] if getattr(r, "success", False)), None)
        content = getattr(first_success, "markdown", "") if first_success else ""
        html = getattr(first_success, "html", "") if first_success else ""

        if not content.strip() or _looks_blocked(content):
            logger.warning(
                "Competitor discovery: site content too thin/blocked",
                extra={"workspace_id": str(workspace_id), "operation_id": operation_id, "url": url},
            )
            await emit_step_failure(
                operation_id=operation_id, scope=SCOPE, step="scrape",
                message="Site content was too thin to analyze (the site may be blocking automated crawlers)",
                error="blocked_or_empty_content", user_id=user_id,
            )
            return

        await emit_step_success(
            operation_id=operation_id, scope=SCOPE, step="scrape",
            message="Scrape complete", progress=30, user_id=user_id,
        )

        from src.utils.credit_manager import (
            STAGE_CREDITS, InsufficientCreditsError,
            consume_stage_credits, _emit_credit_event,
        )

        try:
            await consume_stage_credits(user_id, STAGE_CREDITS["competitor_discovery"], "competitor_discovery")
        except InsufficientCreditsError as e:
            _emit_credit_event(e.available, e.stage, e.required, step="credits.exhausted")
            await emit_step_failure(
                operation_id=operation_id, scope=SCOPE, step="competitor_discovery",
                message="Insufficient credits for competitor discovery",
                error="insufficient_credits", user_id=user_id,
            )
            return

        await emit_step_start(
            operation_id=operation_id, scope=SCOPE, step="competitor_discovery",
            message="Discovering competitor domains via search data", progress=35, user_id=user_id,
        )

        from src.flow.engines.competitors.pipeline import discover_competitors
        from src.flow.engines.competitors.site_content import crawl_offering_subpages

        offering_content = await crawl_offering_subpages(html, url)
        combined_content = content[:6000]
        if offering_content:
            combined_content = f"{combined_content}\n---\n{offering_content}"
        combined_content = combined_content[:9000]

        analysis = await discover_competitors(business_content=combined_content, own_domain=url)

        result = await db.execute(select(BrandVoice).where(BrandVoice.workspace_id == workspace_id))
        brand_voice: Optional[BrandVoice] = result.scalar_one_or_none()
        if brand_voice is None:
            brand_voice = BrandVoice(workspace_id=workspace_id)
            db.add(brand_voice)
        brand_voice.competitor_analysis = analysis
        # Caller wraps `db` in get_async_db_context(), which commits on clean
        # exit / rolls back on exception — flush only, don't commit here.
        await db.flush()

        from src.flow.engines.competitors.pipeline import select_top_competitors

        top_competitors = select_top_competitors(analysis)

        await emit_step_success(
            operation_id=operation_id, scope=SCOPE, step="competitor_discovery",
            message="Competitor discovery completed",
            payload={"business_competitors": len(analysis.get("business_competitors", []))},
            progress=95, user_id=user_id,
        )
        await emit_pipeline_complete(
            operation_id=operation_id, scope=SCOPE,
            message="Competitor discovery completed successfully",
            payload={
                "workspace_id": str(workspace_id),
                "competitor_analysis": analysis,
                "top_competitors": top_competitors,
            },
            user_id=user_id,
        )
    except Exception as exc:  # noqa: BLE001 - log, notify, and propagate for caller logging
        logger.error(
            "Competitor discovery failed",
            extra={"workspace_id": str(workspace_id), "operation_id": operation_id, "error": str(exc)},
            exc_info=True,
        )
        await emit_step_failure(
            operation_id=operation_id, scope=SCOPE, step="competitor_discovery",
            message=f"Competitor discovery failed: {exc}", error=str(exc), user_id=user_id,
        )
        raise
