import asyncio
import logging
from uuid import UUID

from langchain_core.messages import HumanMessage

from src.flow.engines.content.generation.focus_keyword import (
    FOCUS_KEYWORD_STATE_KEY,
    pin_focus_keyword,
    resolve_focus_keyword,
)
from src.flow.engines.content.generation.outline_depth import hold_main_sections
from src.flow.model.llm_manager import load_model
from src.flow.model.provider_outage import (
    STEP_FAILED,
    UNREADABLE_ANSWER,
    ProviderOutage,
    ProviderUnavailable,
    provider_outage,
)
from src.flow.model.runaway import ainvoke_watched, ran_away
from src.flow.model.structure.outlines import (
    get_outline_display_name,
    get_outline_model,
    normalize_content_type,
)
from src.flow.prompts.human.outline import (
    get_outline_prompt,
    outline_subsection_rule,
    subsection_request,
)
from src.flow.states.rext import REXT
from src.services.content_cluster_mapping_service import (
    build_cluster_heading_map,
    format_cluster_heading_map_for_prompt,
)
from src.utils.credit_manager import deduct_credits
from src.utils.stage_timing import timed_stage

logger = logging.getLogger(__name__)


async def _bulk_sync_workspace(workspace_id) -> None:
    """Run bulk CMS sync using LangGraph async db context."""
    if not workspace_id:
        return
    try:
        from src.api.database.async_database import get_pooled_langgraph_db_context
        from src.services.cms_status_service import CMSStatusService
        from src.utils.loop_bridge import run_on_main_loop

        async def _sync():
            async with get_pooled_langgraph_db_context() as db:
                svc = CMSStatusService(db)
                return await svc.bulk_sync_workspace(UUID(str(workspace_id)))

        result = await run_on_main_loop(_sync())
        logger.info(f"[OutlineSync] CMS sync complete: {result}")

    except Exception as e:
        logger.warning(f"[OutlineSync] CMS sync failed (non-fatal): {e}")


async def _rank_personas_for_outline(
    outline: dict,
    workspace_id,
    *,
    topic: str | None = None,
    search_intent: str | None = None,
    content_type: str | None = None,
) -> tuple[str | None, list[dict]]:
    """Score every workspace persona against this outline, best fit first.

    Returns ``(recommended_persona_id, recommendations)``. The recommendation is
    a default the user can change or clear in the outline step — it is never the
    final word, so a scoring failure costs a helpful default and nothing else.
    It's the best fit whose stated expertise covers the subject, or None when no
    persona's does (rext-control#559); the recommendations list them all.
    """
    if not workspace_id or not outline:
        return None, []
    try:
        from sqlalchemy import select as sa_select

        from src.api.database.async_database import get_pooled_langgraph_db_context
        from src.api.models.knowledge_models.persona_model import Persona
        from src.flow.engines.content.generation.persona_relevance import (
            rank_personas,
            recommend_persona,
        )
        from src.utils.loop_bridge import run_on_main_loop

        async def _query_personas():
            async with get_pooled_langgraph_db_context() as db:
                result = await db.execute(
                    sa_select(Persona)
                    .where(Persona.workspace_id == workspace_id)
                    .order_by(Persona.created_at.desc())
                )
                return list(result.scalars().all())

        personas = await run_on_main_loop(_query_personas())
        if not personas:
            return None, []

        ranked = rank_personas(
            personas,
            topic=topic or outline.get("title"),
            title=outline.get("title"),
            search_intent=search_intent,
            content_type=content_type,
        )
        recommendations = [relevance.to_dict() for relevance in ranked]
        recommended_id = recommend_persona(ranked)
        recommended = next((r for r in ranked if r.persona_id == recommended_id), None)
        # The persona's id, not its name: drafted personas are real people.
        logger.info(
            "[PersonaSelect] recommended=%r score=%s of %d persona(s) for topic=%r "
            "intent=%r content_type=%r",
            recommended_id,
            recommended.score if recommended else None,
            len(ranked),
            topic,
            search_intent,
            content_type,
        )
        return recommended_id, recommendations

    except Exception as e:
        logger.warning(f"[PersonaSelect] failed (non-fatal): {e}")
        return None, []


async def _fetch_brand_voice_promotion(outline: dict, workspace_id) -> dict | None:
    """Return brand voice promotion recommendation for this outline topic.

    Searches the brand voice embedding for semantic relevance to the outline
    topic and returns a dict suitable for embedding in the outline interrupt.
    Falls back to a non-recommended entry if no embedding exists but brand
    voice is present in the DB.
    """
    if not workspace_id or not outline:
        return None
    try:
        from sqlalchemy import select as sa_select

        from src.api.database.async_database import get_pooled_langgraph_db_context
        from src.api.models.knowledge_models.knowledge_model import BrandVoice
        from src.api.models.workspace_models.workspace_model import WorkspaceModel
        from src.services.brand_voice_embedding_service import BrandVoiceEmbeddingService
        from src.utils.loop_bridge import run_on_main_loop

        query = (outline.get("focus_keyphrase") or outline.get("title") or "").strip()

        async def _fetch_brand_row():
            async with get_pooled_langgraph_db_context() as db:
                row = await db.execute(
                    sa_select(BrandVoice, WorkspaceModel.name, WorkspaceModel.url)
                    .join(WorkspaceModel, WorkspaceModel.id == BrandVoice.workspace_id)
                    .where(BrandVoice.workspace_id == UUID(str(workspace_id)))
                )
                return row.first()

        row = await run_on_main_loop(_fetch_brand_row())
        if row is None:
            brand_data = None
            workspace_name = None
            workspace_url = None
        else:
            bv, wname, wurl = row
            brand_data = {
                "brand_name": bv.brand_name or "",
                "about": bv.about or "",
                "selling_position": bv.selling_position or "",
            }
            workspace_name = wname
            workspace_url = wurl
        if brand_data is None:
            return None

        # The workspace name is an internal, user-chosen label (e.g. "My Test
        # Workspace") — it has no guaranteed relation to the actual brand and must
        # never be presented as the brand identity. bv.brand_name (set explicitly by
        # the user, or auto-extracted from the scraped site) is the only trustworthy
        # source. workspace_url (the site the workspace represents) is the only value
        # that may be used as a hyperlink target for the promo.
        brand_name = brand_data["brand_name"] or workspace_name or "Brand"
        if not brand_data["brand_name"]:
            logger.info(
                "[BrandPromo] No explicit brand_name set for workspace %s — "
                "falling back to workspace name '%s'",
                workspace_id,
                workspace_name,
            )
        brand_url = workspace_url or ""

        if not query:
            return {
                "brand_name": brand_name,
                "brand_url": brand_url,
                "about": brand_data["about"],
                "selling_position": brand_data["selling_position"],
                "score": 0.0,
                "recommended": False,
            }

        svc = BrandVoiceEmbeddingService()
        result = await svc.search_brand_voice_relevance(
            workspace_id=UUID(str(workspace_id)),
            query=query,
        )

        if result:
            result["brand_name"] = result.get("brand_name") or brand_name
            # The embedding store never carries a URL — always source it from the
            # workspace record so a stale/mismatched value can't leak into content.
            result["brand_url"] = brand_url
            logger.info(
                f"[BrandPromo] score={result['score']} recommended={result['recommended']} "
                f"brand='{result['brand_name']}' url='{brand_url}'"
            )
            return result

        # Embedding not yet created — return non-recommended fallback
        return {
            "brand_name": brand_name,
            "brand_url": brand_url,
            "about": brand_data["about"],
            "selling_position": brand_data["selling_position"],
            "score": 0.0,
            "recommended": False,
        }

    except Exception as e:
        logger.warning(f"[BrandPromo] Fetch failed (non-fatal): {e}")
        return None


def _display_name_from_domain(domain: str) -> str:
    """'ahrefs.com' -> 'Ahrefs'. A derivation, never an invention.

    Competitors are stored as bare domains, but a comparison names PRODUCTS, so
    the domain's registrable label is surfaced as the human name. Capitalisation
    is left to the model beyond a simple title-case: the point is to hand it a
    real entity to anchor on, and the domain travels alongside so it can tell
    which company is meant.
    """
    host = (domain or "").strip().lower()
    for prefix in ("https://", "http://", "www."):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    host = host.split("/")[0]
    label = host.split(".")[0] if "." in host else host
    return label.replace("-", " ").title() if label else ""


def _format_known_entities(brand_name: str, competitor_domains: list) -> str:
    """The real, named entities this workspace already knows about.

    Comparison-style outlines are generated from a topic, SERP domains and
    keyword clusters — none of which contain a product name. Given nothing real
    to compare, the model invented entities ("Agency A", "Agency B") and every
    later stage faithfully wrote an article about companies that do not exist.
    This block is the fix at the source: real names in, no need to invent.
    """
    lines: list[str] = []
    if brand_name:
        lines.append(f"- {brand_name} (this workspace's own brand)")
    for domain in competitor_domains[:8]:
        if not isinstance(domain, str) or not domain.strip():
            continue
        display = _display_name_from_domain(domain)
        lines.append(f"- {display} ({domain.strip()})" if display else f"- {domain.strip()}")
    return "\n".join(lines) if lines else "None available."


async def _fetch_known_entities(workspace_id) -> tuple[str, list]:
    """(brand_name, competitor_domains) for this workspace, for the prompt above.

    Deliberately separate from `_fetch_brand_voice_promotion`, which cannot be
    reused here: that one runs AFTER generation because it scores the brand's
    relevance against the finished outline's keyphrase. These names are needed
    BEFORE, to shape what the outline names in the first place. Non-fatal — an
    outline without them is exactly as good as it was before this existed.
    """
    if not workspace_id:
        return "", []
    try:
        from sqlalchemy import select as sa_select

        from src.api.database.async_database import get_pooled_langgraph_db_context
        from src.api.models.knowledge_models.knowledge_model import BrandVoice
        from src.utils.loop_bridge import run_on_main_loop

        async def _fetch_row():
            async with get_pooled_langgraph_db_context() as db:
                result = await db.execute(
                    sa_select(BrandVoice.brand_name, BrandVoice.competitors).where(
                        BrandVoice.workspace_id == UUID(str(workspace_id))
                    )
                )
                return result.first()

        row = await run_on_main_loop(_fetch_row())
        if row is None:
            return "", []
        brand_name, competitors = row
        return (brand_name or "").strip(), list(competitors or [])
    except Exception as e:
        logger.warning(f"[KnownEntities] Fetch failed (non-fatal): {e}")
        return "", []


# The workspace's reader and offer, as the outline prompt shows them (FB2.17,
# revnix/rext-control#698): enough to steer the plan, never the whole profile.
_PROFILE_TEXT_CHARS = 500
_PROFILE_ITEM_CHARS = 120
_PROFILE_LIST_ITEMS = 6


def _profile_text(value, limit: int = _PROFILE_TEXT_CHARS) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _profile_list(value) -> list[str]:
    """A profile list (strings, or objects such as {"name": …, "description": …}) as short lines."""
    items: list[str] = []
    for item in value if isinstance(value, list) else []:
        if isinstance(item, dict):
            item = " — ".join(str(v) for v in item.values() if isinstance(v, str) and v.strip())
        text = _profile_text(item, _PROFILE_ITEM_CHARS)
        if text:
            items.append(text)
    return items[:_PROFILE_LIST_ITEMS]


async def _fetch_workspace_profile(workspace_id) -> dict:
    """Who this workspace writes for and what it offers, from its brand voice profile: the
    customer profile, target audience, about, selling position and content pillars.

    The outline used only the brand name and the competitors from it, so plans were written for
    a generic reader. Non-fatal: an empty profile leaves the outline as it was.
    """
    if not workspace_id:
        return {}
    try:
        from sqlalchemy import select as sa_select

        from src.api.database.async_database import get_pooled_langgraph_db_context
        from src.api.models.knowledge_models.knowledge_model import BrandVoice
        from src.utils.loop_bridge import run_on_main_loop

        async def _fetch_row():
            async with get_pooled_langgraph_db_context() as db:
                result = await db.execute(
                    sa_select(
                        BrandVoice.customer_profile,
                        BrandVoice.target_audience,
                        BrandVoice.about,
                        BrandVoice.selling_position,
                        BrandVoice.content_pillar,
                    ).where(BrandVoice.workspace_id == UUID(str(workspace_id)))
                )
                return result.first()

        row = await run_on_main_loop(_fetch_row())
        if row is None:
            return {}
        customer_profile, target_audience, about, selling_position, content_pillar = row
        return {
            "customer_profile": _profile_text(customer_profile),
            "target_audience": _profile_list(target_audience),
            "about": _profile_text(about),
            "selling_position": _profile_text(selling_position),
            "content_pillars": _profile_list(content_pillar),
        }
    except Exception as e:
        logger.warning(f"[WorkspaceProfile] Fetch failed (non-fatal): {e}")
        return {}


def _format_reader_and_offer(profile: dict) -> str:
    """The workspace's customers and offer, as the outline prompt reads them. The customers
    are who the site serves, not the article's reader: that is whoever searches the keyword
    (the prompt's rule 12), which is why the block doesn't say "who this is for"."""
    profile = profile or {}
    reader = [
        f"- Customer profile: {profile['customer_profile']}"
        if profile.get("customer_profile")
        else "",
        f"- Audiences: {'; '.join(profile['target_audience'])}"
        if profile.get("target_audience")
        else "",
    ]
    offer = [
        f"- About: {profile['about']}" if profile.get("about") else "",
        f"- What it offers: {profile['selling_position']}"
        if profile.get("selling_position")
        else "",
        f"- Content pillars: {'; '.join(profile['content_pillars'])}"
        if profile.get("content_pillars")
        else "",
    ]
    reader, offer = [line for line in reader if line], [line for line in offer if line]
    if not reader and not offer:
        return "None available."
    blocks = []
    if reader:
        blocks.append("WHO THE SITE SERVES:\n" + "\n".join(reader))
    if offer:
        blocks.append("WHAT THE BRAND OFFERS:\n" + "\n".join(offer))
    return "\n".join(blocks)


async def _fetch_internal_links(outline: dict, workspace_id) -> list:
    """Return semantically related published content links for this outline."""
    if not workspace_id or not outline:
        return []
    try:
        from sqlalchemy import select

        from src.api.database.async_database import get_pooled_langgraph_db_context
        from src.api.models.content_models.content import Content as ContentModel
        from src.api.models.content_models.publishing_result import (
            ContentPublishingResult,
            PublishingStatus,
        )
        from src.services.content_embedding_service import ContentEmbeddingService
        from src.utils.loop_bridge import run_on_main_loop

        query = (outline.get("focus_keyphrase") or outline.get("title") or "").strip()
        if not query:
            return []

        svc = ContentEmbeddingService(db=None)
        candidates = await svc.search_related_content(
            workspace_id=UUID(str(workspace_id)),
            query=query,
            limit=50,
        )
        score_map = {
            UUID(c["content_id"]): c.get("similarity_score", 0.0)
            for c in candidates
            if c.get("content_id")
        }

        async def _fetch_links():
            async with get_pooled_langgraph_db_context() as db:
                result = await db.execute(
                    select(ContentPublishingResult, ContentModel.title)
                    .join(ContentModel, ContentModel.id == ContentPublishingResult.content_id)
                    .where(
                        ContentPublishingResult.status == PublishingStatus.PUBLISHED,
                        ContentPublishingResult.external_url.isnot(None),
                        ContentPublishingResult.external_url.notlike("%?p=%"),
                        ContentModel.workspace_id == UUID(str(workspace_id)),
                        ContentModel.deleted_at.is_(None),
                    )
                )
                return result.all()

        rows = await run_on_main_loop(_fetch_links())

        best: dict[UUID, dict] = {}
        for pub, title in rows:
            cid = pub.content_id
            ex = best.get(cid)
            if not ex or (
                pub.status == PublishingStatus.PUBLISHED
                and ex["pub"].status != PublishingStatus.PUBLISHED
            ):
                best[cid] = {"pub": pub, "title": title}

        links = sorted(
            [
                {
                    "title": v["title"],
                    "url": v["pub"].external_url,
                    "score": round(score_map.get(k, 0.0), 4),
                    "status": v["pub"].status,
                }
                for k, v in best.items()
                if v["pub"].external_url
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
        f"{key}={value}" for key, value in scores.items() if key in tracked_scores
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


# What a regeneration is shown of the rejected outline: the plan the model wrote. The rest of
# the stored outline is the page's display copy of that plan, the heading map (in the prompt
# under its own heading) and what was looked up after it was written (links, personas, the
# brand's fit), plus the review's own marks: thousands of tokens the feedback never refers to.
_NOT_THE_PLAN = frozenset(
    {
        "_render",
        "cluster_heading_map",
        "internal_links",
        "persona_recommendations",
        "selected_persona_id",
        "brand_voice_promotion",
        "rejected_reason",
        "status",
        "iteration_count",
    }
)


def _previous_outline_for_prompt(outline_state: dict | None) -> dict:
    return {key: value for key, value in (outline_state or {}).items() if key not in _NOT_THE_PLAN}


# A step guide's whole body is its steps. On staging one How-To came back with one step and
# another with none (rext-control#603); the schema can't require them without failing the run,
# since structured output here isn't strict.
_MIN_STEPS = 3


def _summed_word_target(model_schema, sections: list) -> int:
    """The sections' word budgets added up, kept inside the outline schema's own limits on
    target_word_count (blog: 800 to 5,000). The sum replaces the target after validation, so
    without the clamp a 16-entry blog outline could ask the writer for 12,800 words (review
    round 3 of #890)."""
    total = sum(s.get("suggested_word_count") or 200 for s in sections if isinstance(s, dict))
    field = getattr(model_schema, "model_fields", {}).get("target_word_count")
    limits = getattr(field, "metadata", None) or []
    high = next((rule.le for rule in limits if getattr(rule, "le", None) is not None), None)
    low = next((rule.ge for rule in limits if getattr(rule, "ge", None) is not None), None)
    if high is not None:
        total = min(total, high)
    if low is not None:
        total = max(total, low)
    return total


_PILLAR = "pillar-content"

# What each step guide is built from, the least of it an outline can have, and what the second
# attempt is asked for. A tutorial is built from its required modules: its `steps` are an optional
# deeper breakdown, so their absence isn't a fault (review of #922).
_STRUCTURE = {
    "how-to-guide": (
        "steps",
        "step",
        _MIN_STEPS,
        f"{_MIN_STEPS}-10 steps, each with its title and description, in the order a reader "
        "takes them",
    ),
    "tutorial": (
        "modules",
        "module",
        1,
        "its modules, each with its title and what it teaches, in the order a learner takes them",
    ),
    # Pillar content is expected to have H3 subsections (outline_subsection_rule), and its schema
    # holds them, but the model often returns H2s only on this larger schema: two runs of two in
    # the staging proof (rext-control#603). Counted as H3 sections, not as a block of its own.
    _PILLAR: (
        "sections",
        "H3 subsection",
        1,
        "H3 subsections: wherever an H2 covers two or more distinct parts, each part as its own "
        'section with heading_level "H3", directly after that H2',
    ),
}


def _outline_sections(outline: dict) -> list:
    """An outline's sections, wherever its schema keeps them: a flat top-level `sections`, or
    nested under a container such as a blog's or a pillar's `structure.sections`."""
    sections = outline.get("sections")
    if isinstance(sections, list) and sections:
        return sections
    for container_key in ("structure", "content_structure"):
        container = outline.get(container_key)
        if isinstance(container, dict) and isinstance(container.get("sections"), list):
            return container["sections"]
    return []


def _structure_count(content_type: str, outline: dict) -> int:
    if content_type == _PILLAR:
        return sum(
            1
            for section in _outline_sections(outline)
            if isinstance(section, dict) and str(section.get("heading_level") or "").upper() == "H3"
        )
    key = _STRUCTURE[content_type][0]
    block = outline.get(key)
    if isinstance(block, dict):
        block = block.get(key)
    return len(block) if isinstance(block, list) else 0


def _thin_structure(
    content_type: str, outline: dict, reviewed: bool = False, fewer_subsections: bool = False
) -> str | None:
    """What a generated outline is missing that makes it unusable, or None.

    ``reviewed`` is a regeneration after a person's feedback: their own ask sets the length
    ("combine it into two steps"), so only an empty structure is thin then.
    ``fewer_subsections`` is that feedback asking for fewer H3s: a pillar outline without any
    is then what was asked for."""
    if content_type not in _STRUCTURE:
        return None
    if content_type == _PILLAR and fewer_subsections:
        return None
    _, name, least, _ = _STRUCTURE[content_type]
    if reviewed:
        least = 1
    count = _structure_count(content_type, outline)
    if count >= least:
        return None
    return f"had {count} {name}{'' if count == 1 else 's'}"


@deduct_credits("generate_outline")
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

    # Resolved once, here, because the outline is the first artifact every
    # downstream stage reads from: the generation prompt, the requirements spec,
    # the density gate, internal-link and brand-voice relevance search. Letting
    # the outline model choose its own focus_keyphrase (the schema asks for
    # "2-4 words recommended") meant the article was written for one phrase and
    # then labelled with another at the very end of generate_content.
    focus_keyword = resolve_focus_keyword(state)

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
        + ", ".join(f"{k}:{v}" for k, v in (c.get("intent_distribution") or {}).items())
        for c in competitors
    ]

    intent_distribution = serp_backlinks.get("main_intent", "Informational")

    # 2b. Format Keyword Clusters for prompt (if available)
    keyword_clusters = seo_result.get("keyword_clusters", [])
    logger.info("Keyword Clusters: %s", keyword_clusters)
    clusters_context = "None"
    if keyword_clusters:
        clusters_context = "\n".join([_cluster_context_for_prompt(c) for c in keyword_clusters])

    cluster_heading_map = content_state.get("cluster_heading_map")
    if not cluster_heading_map:
        cluster_heading_map = build_cluster_heading_map(
            keyword_clusters=keyword_clusters,
            topic=topic,
            content_type=content_type,
            questions=questions,
        )
    logger.info("Cluster Heading Map: %s", cluster_heading_map)
    # Outline generation runs under with_structured_output(<Type>Outline), so the
    # schema's block set is guaranteed regardless of what the cluster map suggests.
    # Heading suggestions are safe and useful HERE — they shape what each schema
    # section is about. Article generation gets the same data in coverage form
    # instead, because nothing constrains structure at that stage.
    cluster_heading_map_context = format_cluster_heading_map_for_prompt(
        cluster_heading_map, for_outline=True
    )

    # 3. Generate outline
    try:
        # 1. Select the correct Pydantic model for this content type
        model_schema = get_outline_model(content_type)

        outline_model = load_model(max_tokens=8192).with_structured_output(model_schema)

        prompt_template = get_outline_prompt()

        # Real named entities, resolved BEFORE generation so comparison-style
        # outlines name actual products instead of inventing stand-ins.
        (known_brand_name, known_competitor_domains), workspace_profile = await asyncio.gather(
            _fetch_known_entities(workspace_id), _fetch_workspace_profile(workspace_id)
        )
        known_entities = _format_known_entities(known_brand_name, known_competitor_domains)
        reader_and_offer = _format_reader_and_offer(workspace_profile)
        logger.info(
            "[KnownEntities] brand=%r competitors=%d for content_type=%s",
            known_brand_name,
            len(known_competitor_domains),
            content_type,
        )

        messages = prompt_template.format_messages(
            content_type=content_type,
            topic=topic,
            # The reader rule names "whoever types the Focus Keyword"; a title the user wrote
            # may not contain it, so the prompt states it.
            focus_keyword=focus_keyword or topic,
            related_topics=", ".join(related_topics),
            questions="\n".join(f"- {q}" for q in questions),
            competitors_context="\n".join(competitors_context),
            known_entities=known_entities,
            reader_and_offer=reader_and_offer,
            intent_distribution=intent_distribution,
            keyword_clusters=clusters_context,
            cluster_heading_map=cluster_heading_map_context,
            subsection_rule=outline_subsection_rule(
                content_type, content_type_raw, outline_rejected_reason
            ),
            rejected_reason=outline_rejected_reason,
            previous_outline=_previous_outline_for_prompt(outline_state),
        )

        # 🔒 Fail-fast guard
        for m in messages:
            assert "{topic}" not in m.content, "Prompt variables not interpolated"

        logger.info("Outline prompt formatted successfully")

        with timed_stage(
            "outline_model", regenerating=outline_rejected_reason not in (None, "", "None")
        ):
            generated_outline = await ainvoke_watched(
                outline_model, messages, stage="outline_model", schema=model_schema
            )
        outline_dict = generated_outline.model_dump()

        # Asked once more, only when the outline can't be written from (or, for pillar content,
        # has none of the subsections it is expected to have): one extra model call.
        reviewed = str(outline_rejected_reason or "None").strip().lower() not in ("", "none")
        thin = _thin_structure(
            content_type,
            outline_dict,
            reviewed=reviewed,
            fewer_subsections=subsection_request(outline_rejected_reason) == "fewer",
        )
        if thin:
            logger.warning("Outline %s for content_type=%s; asking once more", thin, content_type)
            retry_note = HumanMessage(
                content=(
                    f"A first attempt at this outline {thin}. A {content_type} needs "
                    f"{_STRUCTURE[content_type][3]}. Return the complete outline again with "
                    "every one filled."
                )
            )
            # The first outline stays unless the second is at least as full: a failed or thinner
            # second attempt never costs the run what it already had.
            try:
                with timed_stage("outline_model", regenerating=reviewed, attempt=2):
                    retried = (
                        await ainvoke_watched(
                            outline_model,
                            [*messages, retry_note],
                            stage="outline_model",
                            schema=model_schema,
                            attempts=1,  # itself the second attempt: four calls otherwise
                        )
                    ).model_dump()
            except Exception as error:
                # An outage is the run's to report (the handler below), not a reason to return,
                # and charge for, an outline already known to be thin.
                if provider_outage(error) is not None:
                    raise
                logger.warning(
                    "The second outline attempt failed; keeping the first", exc_info=True
                )
            else:
                gained = _structure_count(content_type, retried) - _structure_count(
                    content_type, outline_dict
                )
                # A pillar's second attempt was asked for subsections only: without any it is
                # no fuller than the first, which stays.
                if gained > 0 or (gained == 0 and content_type != _PILLAR):
                    outline_dict = retried

        # A first outline is held to its main sections and their budgets (outline_depth.py). A
        # regeneration after a person's feedback is theirs: "make it three sections" stands.
        if not reviewed:
            raised, lifted = hold_main_sections(outline_dict)
            if raised or lifted:
                logger.info(
                    "Outline held to its main sections: %s subsection(s) raised to H2, "
                    "%s budget(s) lifted, content_type=%s",
                    raised,
                    lifted,
                    content_type,
                )

        # Persist the selected topic as the outline title
        outline_dict["title"] = topic

        # Pin BEFORE _render, the internal-link/brand-voice relevance searches
        # and the return: all of those read focus_keyphrase, and each one
        # reading a different value is how the keyword used to drift.
        pin_focus_keyword(outline_dict, focus_keyword)
        outline_dict["schema_type"] = get_outline_display_name(content_type) or "Blog"
        outline_dict["cluster_heading_map"] = cluster_heading_map

        # Set target_word_count — sum sections if present, else use model default.
        # Schemas differ on where the section list lives: a flat top-level
        # `sections` (base-style), or nested under a container model such as
        # blog's `structure.sections`. Reading only the flat key meant blog
        # outlines never had their word budget recomputed and silently fell back
        # to the schema default regardless of how deep the plan actually was.
        sections = _outline_sections(outline_dict)
        if sections:
            outline_dict["target_word_count"] = _summed_word_target(model_schema, sections)
        # else: model already set target_word_count (FAQ, HowTo, etc. define their own)

        # Attach generic render shape so frontend can display any outline type uniformly
        from src.flow.model.structure.outlines.render import normalize_outline

        outline_dict["_render"] = normalize_outline(outline_dict, content_type)

        # Fetch internal links, rank personas, fetch brand promo — run in parallel.
        # The persona is ranked HERE rather than at extraction time because fit
        # is a property of the article (topic, title, intent, content type), not
        # of the workspace.
        with timed_stage("outline_lookups"):
            internal_links, persona_ranking, brand_voice_promotion = await asyncio.gather(
                _fetch_internal_links(outline_dict, workspace_id),
                _rank_personas_for_outline(
                    outline_dict,
                    workspace_id,
                    topic=topic,
                    search_intent=intent_distribution,
                    content_type=content_type,
                ),
                _fetch_brand_voice_promotion(outline_dict, workspace_id),
            )
        recommended_persona_id, persona_recommendations = persona_ranking
        outline_dict["internal_links"] = internal_links
        outline_dict["selected_persona_id"] = recommended_persona_id
        outline_dict["persona_recommendations"] = persona_recommendations
        outline_dict["brand_voice_promotion"] = brand_voice_promotion

        logger.info("Outline generated successfully")

        return {
            "content": {
                FOCUS_KEYWORD_STATE_KEY: focus_keyword,
                "cluster_heading_map": cluster_heading_map,
                "outline": {
                    **outline_dict,
                    "rejected_reason": "",
                    "status": "reviewing",
                    "iteration_count": outline_state.get("iteration_count", 0) + 1,
                },
                "status": "planning",
            }
        }

    except Exception as e:
        # The AI provider unavailable ends the run with its notice (stop_on_outage, G75.1).
        if provider_outage(e) is not None:
            raise
        logger.exception("Error generating outline")
        # No outline: the run ends with the same notice. It used to go on to the review step,
        # which opened on an empty outline (rext-control#697). Nothing has been charged: the
        # outline is charged only once it is written.
        raise ProviderUnavailable(
            ProviderOutage(
                provider="OpenAI",
                kind=UNREADABLE_ANSWER if ran_away(e) else STEP_FAILED,
                detail=type(e).__name__,
            )
        ) from e
