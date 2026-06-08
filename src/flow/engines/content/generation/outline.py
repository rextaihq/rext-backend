import asyncio
import logging
from uuid import UUID

from src.flow.states.rext import REXT
from src.flow.model.structure.outlines import (
    get_outline_model,
    get_outline_display_name,
    normalize_content_type,
)
from src.flow.model.llm_manager import load_model
from src.flow.prompts.human.outline import get_outline_prompt

logger = logging.getLogger(__name__)



async def _bulk_sync_workspace(workspace_id) -> None:
    """Dispatch bulk CMS sync to main event loop via run_coroutine_threadsafe."""
    if not workspace_id:
        return
    try:
        from src.utils import loop_registry
        main_loop = loop_registry.get()
        if not main_loop:
            logger.warning("[OutlineSync] Main loop not registered — skipping CMS sync.")
            return

        from src.api.database.async_database import AsyncSessionLocal
        from src.services.cms_status_service import CMSStatusService

        async def _do():
            async with AsyncSessionLocal() as db:
                svc = CMSStatusService(db)
                result = await svc.bulk_sync_workspace(UUID(str(workspace_id)))
                await db.commit()
                logger.info(f"[OutlineSync] CMS sync complete: {result}")

        future = asyncio.run_coroutine_threadsafe(_do(), main_loop)
        await asyncio.to_thread(future.result)  # wait without blocking bg event loop

    except Exception as e:
        logger.warning(f"[OutlineSync] CMS sync failed (non-fatal): {e}")


async def _fetch_internal_links(outline: dict, workspace_id) -> list:
    """Return semantically related published content links for this outline."""
    if not workspace_id or not outline:
        return []
    try:
        from src.services.content_embedding_service import ContentEmbeddingService
        from src.api.models.content_models.publishing_result import ContentPublishingResult, PublishingStatus
        from src.api.models.content_models.content import Content as ContentModel
        from src.api.database.async_database import SyncSessionLocal
        from sqlalchemy import select

        query = (outline.get("focus_keyphrase") or outline.get("title") or "").strip()
        if not query:
            return []

        svc = ContentEmbeddingService(db=None)
        candidates = await svc.search_related_content(
            workspace_id=UUID(str(workspace_id)),
            query=query,
            limit=50,
        )
        score_map = {UUID(c["content_id"]): c.get("similarity_score", 0.0) for c in candidates if c.get("content_id")}

        def _fetch_rows():
            db = SyncSessionLocal()
            try:
                return db.execute(
                    select(ContentPublishingResult, ContentModel.title)
                    .join(ContentModel, ContentModel.id == ContentPublishingResult.content_id)
                    .where(
                        ContentPublishingResult.status == PublishingStatus.PUBLISHED,
                        ContentPublishingResult.external_url.isnot(None),
                        ContentPublishingResult.external_url.notlike("%?p=%"),
                        ContentModel.workspace_id == UUID(str(workspace_id)),
                        ContentModel.deleted_at.is_(None),
                    )
                ).all()
            finally:
                db.close()

        rows = await asyncio.to_thread(_fetch_rows)

        best: dict[UUID, dict] = {}
        for pub, title in rows:
            cid = pub.content_id
            ex = best.get(cid)
            if not ex or (pub.status == PublishingStatus.PUBLISHED and ex["pub"].status != PublishingStatus.PUBLISHED):
                best[cid] = {"pub": pub, "title": title}

        links = sorted(
            [
                {
                    "title": v["title"],
                    "url": v["pub"].external_url,
                    "score": round(score_map.get(k, 0.0), 4),
                    "status": v["pub"].status,
                }
                for k, v in best.items() if v["pub"].external_url
            ],
            key=lambda x: x["score"],
            reverse=True,
        )

        logger.info(f"[InternalLinks] {len(links)} candidate(s) attached to outline.")
        return links

    except Exception as e:
        logger.warning(f"[InternalLinks] Fetch failed (non-fatal): {e}")
        return []


async def generate_outline(state: REXT) -> dict:
    """Generate a content outline using an LLM.

    Uses the selected topic, content type, SERP context, competitor
    insights, and SEO intent data to produce a structured outline via
    LLM structured output. If the outline was previously rejected,
    the rejection reason is included in the prompt for revision.

    Args:
        state: REXT state containing ``content.selected_topic``,
            ``content.content_type``, ``serp_normalized``, ``seo_result``,
            ``competitors``, and optionally ``content.outline.rejected_reason``.

    Returns:
        dict: State update with ``content.outline`` and ``content.status``
        set to ``"planning"``, or error state on failure.
    """
    content_state = state.get("content", {})
    topic = content_state.get("selected_topic")
    content_type_raw = content_state.get("content_type", "article")
    content_type = normalize_content_type(content_type_raw) or "blog"

    if not topic:
        logger.error("No topic found in state")
        return {
            "content": {
                **content_state,
                "error": "No topic found in state",
            }
        }

    logger.info(
        "Generating outline for: %s (content type: %s -> %s)",
        topic,
        content_type_raw,
        content_type,
    )

    serp_payload = state.get("serp_payload", {})
    workspace_id = serp_payload.get("workspace_id")

    await _bulk_sync_workspace(workspace_id)

    serp_normalized = state.get("serp_normalized", {})
    seo_result = state.get("seo_result", {})
    serp_backlinks = seo_result.get("serp_backlinks", {})
    content_state = state.get("content", {})
    outline_state = content_state.get("outline", {})

    outline_rejected_reason = outline_state.get("rejected_reason", "None")

    # 2. Normalize SERP context for LLM
    related_topics = serp_normalized.get("related_topics", [])
    questions = serp_normalized.get("questions", [])

    competitors = state.get("competitors", [])[:5]
    competitors_context = [
        f"Domain: {c.get('domain')} | Intent: "
        + ", ".join(
            f"{k}:{v}"
            for k, v in (c.get("intent_distribution") or {}).items()
        )
        for c in competitors
    ]

    intent_distribution = serp_backlinks.get("main_intent", "Informational")
    print("Intent: ",intent_distribution)
    
    # 2b. Format Keyword Clusters for prompt (if available)
    keyword_clusters = seo_result.get("keyword_clusters", [])
    clusters_context = "None"
    if keyword_clusters:
        clusters_context = "\n".join([
            f"- Topic Bucket: {c.get('cluster_name')}\n  Supporting Keywords: {', '.join([k.get('keyword') for k in c.get('keywords', [])[:8]])}"
            for c in keyword_clusters
        ])
    

    # 3. Generate outline
    try:
        # 1. Select the correct Pydantic model for this content type
        model_schema = get_outline_model(content_type)
        print(f"model:schema: {model_schema}\n\n\n\n $$$$$$$$")
        outline_model = load_model(max_tokens=8192).with_structured_output(
            model_schema
        )
        print(f"outline_model: {outline_model}\n\n\n\n $$$$$$$$")
        prompt_template = get_outline_prompt()

        messages = prompt_template.format_messages(
            content_type=content_type,
            topic=topic,
            related_topics=", ".join(related_topics),
            questions="\n".join(f"- {q}" for q in questions),
            competitors_context="\n".join(competitors_context),
            intent_distribution=intent_distribution,
            keyword_clusters=clusters_context,
            rejected_reason=outline_rejected_reason,
            previous_outline=outline_state,
        )

        # 🔒 Fail-fast guard
        for m in messages:
            assert "{topic}" not in m.content, "Prompt variables not interpolated"

        logger.info("Outline prompt formatted successfully")

        generated_outline = await outline_model.ainvoke(messages)
        outline_dict = generated_outline.model_dump()
        print(f"outline_dict: {outline_dict}\n\n\n\n $$$$$$$$")

        
        # Persist the selected topic as the outline title
        outline_dict["title"] = topic
        outline_dict["schema_type"] = get_outline_display_name(content_type) or "Blog"

        # Set target_word_count — sum sections if present, else use model default
        sections = outline_dict.get("sections", [])
        if sections:
            outline_dict["target_word_count"] = sum(
                s.get("suggested_word_count") or 200 for s in sections
            )
        # else: model already set target_word_count (FAQ, HowTo, etc. define their own)

        # Attach generic render shape so frontend can display any outline type uniformly
        from src.flow.model.structure.outlines.render import normalize_outline
        outline_dict["_render"] = normalize_outline(outline_dict, content_type)

        # Fetch internal link candidates — all published in workspace, sorted by similarity
        outline_dict["internal_links"] = await _fetch_internal_links(outline_dict, workspace_id)

        logger.info("Outline generated successfully")

        return {
            "content": {
                "outline": {
                    **outline_dict,
                    "rejected_reason": "",
                    "status": "reviewing",
                },
                "status": "planning",
            }
        }

    except Exception as e:
        logger.exception("Error generating outline")
        return {
            "content": {
                "error": f"Generation failed: {str(e)}",
            }
        }
