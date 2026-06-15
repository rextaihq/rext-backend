import asyncio
import logging

from langchain_community.callbacks.manager import get_openai_callback
from src.flow.model.llm_manager import load_model
from src.utils.cost_logger import log_llm_call
from uuid import UUID

from src.flow.states.rext import REXT
from src.flow.model.structure.outlines import (
    get_outline_display_name,
    get_outline_model,
    normalize_content_type,
)
from src.flow.prompts.human.outline import get_outline_prompt
from src.flow.states.rext import REXT
from src.services.content_cluster_mapping_service import (
    build_cluster_heading_map,
    format_cluster_heading_map_for_prompt,
)

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


async def _select_persona_for_outline(outline: dict, workspace_id) -> str | None:
    """Ask the LLM which persona best fits this outline topic. Returns persona ID string or None."""
    if not workspace_id or not outline:
        return None
    try:
        from src.api.models.knowledge_models.persona_model import Persona
        from src.api.database.async_database import SyncSessionLocal
        from sqlalchemy import select as sa_select

        def _fetch():
            db = SyncSessionLocal()
            try:
                result = db.execute(
                    sa_select(Persona)
                    .where(Persona.workspace_id == workspace_id)
                    .order_by(Persona.created_at.desc())
                )
                return list(result.scalars().all())
            finally:
                db.close()

        personas = await asyncio.to_thread(_fetch)
        if not personas:
            return None
        if len(personas) == 1:
            return str(personas[0].id)

        topic = outline.get("title") or outline.get("focus_keyphrase") or ""
        keyphrase = outline.get("focus_keyphrase") or ""
        keywords = ", ".join((outline.get("keywords_to_include") or [])[:5])

        persona_list = "\n".join(
            f"{i+1}. {p.full_name or p.name} | {p.professional_title or 'expert'} | expertise: {p.areas_of_expertise or 'N/A'}"
            for i, p in enumerate(personas)
        )

        prompt = (
            f"Article topic: {topic}\n"
            f"Focus keyphrase: {keyphrase}\n"
            f"Keywords: {keywords}\n\n"
            f"Available author personas:\n{persona_list}\n\n"
            f"Which persona number (1-{len(personas)}) is the best author for this article based on their expertise? "
            f"Reply with just the number."
        )

        llm = load_model(max_tokens=5)
        with get_openai_callback() as cb:
            response = await llm.ainvoke(prompt)
        log_llm_call("persona_selection", "gpt-4o-mini", cb.prompt_tokens, cb.completion_tokens)
        raw = (response.content if isinstance(response.content, str) else "").strip()
        idx = int("".join(c for c in raw if c.isdigit()) or "1") - 1
        idx = max(0, min(idx, len(personas) - 1))
        selected = personas[idx]
        logger.info(f"[PersonaSelect] picked '{selected.name}' (idx={idx}) for topic '{topic}'")
        return str(selected.id)

    except Exception as e:
        logger.warning(f"[PersonaSelect] failed (non-fatal): {e}")
        return None


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


def _cluster_keywords_for_prompt(cluster: dict) -> str:
    return ", ".join(
        str(keyword.get("keyword", "")).strip()
        for keyword in (cluster.get("keywords") or [])[:8]
        if keyword.get("keyword")
    )


def _cluster_context_for_prompt(cluster: dict) -> str:
    scores = cluster.get("quality_scores") or {}
    mapping = cluster.get("outline_mapping") or {}
    tracked_scores = {
        "intent_match",
        "serp_overlap",
        "content_type_fit",
        "cluster_strength",
        "overall",
    }
    score_text = ", ".join(
        f"{key}={value}"
        for key, value in scores.items()
        if key in tracked_scores
    )
    heading = cluster.get("recommended_heading") or mapping.get(
        "suggested_heading",
        "",
    )
    placement = mapping.get("heading_level") or cluster.get("outline_placement", "H2")
    page_type = cluster.get("likely_serp_page_type", "")
    return (
        f"- Cluster: {cluster.get('cluster_name')}\n"
        f"  Natural heading: {heading}\n"
        f"  Placement: {placement}\n"
        f"  Intent: {cluster.get('main_intent', '')} | SERP page type: {page_type}\n"
        f"  Supporting Keywords: {_cluster_keywords_for_prompt(cluster)}\n"
        f"  Scores: {score_text or cluster.get('overall_score', '')}\n"
        f"  Rationale: {cluster.get('rationale', '')}"
    )


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

    asyncio.create_task(_bulk_sync_workspace(workspace_id))

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
    logger.info("Keyword Clusters: %s", keyword_clusters)
    clusters_context = "None"
    if keyword_clusters:
        clusters_context = "\n".join(
            [
                _cluster_context_for_prompt(c)
                for c in keyword_clusters
            ]
        )

    cluster_heading_map = content_state.get("cluster_heading_map")
    if not cluster_heading_map:
        cluster_heading_map = build_cluster_heading_map(
            keyword_clusters=keyword_clusters,
            topic=topic,
            content_type=content_type,
            questions=questions,
        )
    logger.info("Cluster Heading Map: %s", cluster_heading_map)
    cluster_heading_map_context = format_cluster_heading_map_for_prompt(cluster_heading_map)
    

    # 3. Generate outline
    try:
        # 1. Select the correct Pydantic model for this content type
        model_schema = get_outline_model(content_type)
    
        outline_model = load_model(max_tokens=8192).with_structured_output(
            model_schema
        )
      
        prompt_template = get_outline_prompt()

        messages = prompt_template.format_messages(
            content_type=content_type,
            topic=topic,
            related_topics=", ".join(related_topics),
            questions="\n".join(f"- {q}" for q in questions),
            competitors_context="\n".join(competitors_context),
            intent_distribution=intent_distribution,
            keyword_clusters=clusters_context,
            cluster_heading_map=cluster_heading_map_context,
            rejected_reason=outline_rejected_reason,
            previous_outline=outline_state,
        )

        # 🔒 Fail-fast guard
        for m in messages:
            assert "{topic}" not in m.content, "Prompt variables not interpolated"

        logger.info("Outline prompt formatted successfully")

        with get_openai_callback() as cb:
            generated_outline = await outline_model.ainvoke(messages)
        log_llm_call("outline_generation", "gpt-4o-mini", cb.prompt_tokens, cb.completion_tokens)
        outline_dict = generated_outline.model_dump()
    

        
        # Persist the selected topic as the outline title
        outline_dict["title"] = topic
        outline_dict["schema_type"] = get_outline_display_name(content_type) or "Blog"
        outline_dict["cluster_heading_map"] = cluster_heading_map

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

        # Fetch internal links + select best persona — run in parallel
        internal_links, selected_persona_id = await asyncio.gather(
            _fetch_internal_links(outline_dict, workspace_id),
            _select_persona_for_outline(outline_dict, workspace_id),
        )
        outline_dict["internal_links"] = internal_links
        outline_dict["selected_persona_id"] = selected_persona_id

        logger.info("Outline generated successfully")

        return {
            "content": {
                "cluster_heading_map": cluster_heading_map,
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
