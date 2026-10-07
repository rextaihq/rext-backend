"""
Content Generation Node (Agent-Based)

Generates SEO-optimized content using the content agent.
Streams tokens and tool calls to the frontend via LangGraph's custom stream
so the user sees the agent work in real time (like GPT).
"""

import json
import logging
import re

from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.config import get_stream_writer

from src.api.config import settings
from src.flow.engines.agent.content_agent import create_content_agent
from src.flow.engines.content.generation.brand_placement_policy import (
    build_brand_structural_injection,
    resolve_article_brand_policy,
    resolve_placement_instruction,
)
from src.flow.engines.content.generation.cta_labels import strip_cta_labels
from src.flow.engines.content.generation.entity_research import (
    format_official_facts_for_prompt,
    research_official_facts,
)
from src.flow.engines.content.generation.evidence_placement_policy import (
    resolve_evidence_placement_policy,
)
from src.flow.engines.content.generation.focus_keyword import resolve_focus_keyword
from src.flow.engines.content.generation.keyword_density import (
    build_density_prompt_instruction,
)
from src.flow.engines.content.generation.onpage_seo import enforce_onpage_seo
from src.flow.engines.content.generation.outline import _fetch_known_entities
from src.flow.engines.content.generation.outline_structure import (
    faq_section_heading,
    format_guidance_for_prompt,
    format_structure_for_prompt,
    resolve_guidance_blocks,
    resolve_outline_structure,
)
from src.flow.engines.content.generation.provider_unavailable import StoppedAfterCharge
from src.flow.engines.content.generation.repair_content import enforce_subheadings_for_spec
from src.flow.engines.content.generation.requirements_spec import (
    brand_kept_out_of_cta,
    brand_named_in,
    build_requirements_spec,
    excluded_brand_of,
    resolve_outline_cta,
)
from src.flow.engines.content.generation.structured_body import (
    UNPLACED_LINKS_KEY,
    assemble_structured_payload,
    build_structured_content_model,
    uses_structured_body,
)
from src.flow.engines.content.generation.subheading_seo import (
    build_subheading_prompt_instruction,
)
from src.flow.engines.content.generation.title_subject import describe_subject_lock
from src.flow.engines.content.generation.validation import (
    merge_link_inventory,
    protected_links,
)
from src.flow.engines.content.generation.word_count_utils import compute_word_target_band
from src.flow.model.provider_outage import provider_outage
from src.flow.model.structure.contents import get_generated_content_model
from src.flow.model.structure.outlines.render import extract_outline_faqs
from src.flow.model.structure.outlines.schema_org import (
    format_schema_guidance_for_prompt,
)
from src.flow.states.rext import REXT
from src.services.content_cluster_mapping_service import (
    cluster_heading_map_without_keywords,
    clusters_without_keywords,
    format_cluster_heading_map_for_prompt,
)
from src.utils.credit_manager import (
    STAGE_CREDITS,
    InsufficientCreditsError,
    _emit_credit_event,
    can_afford_stage,
    consume_stage_credits,
)
from src.utils.image_placeholder import build_placeholder_marker

logger = logging.getLogger(__name__)

# Domains/markers that only ever show up when the model invents an image URL
# instead of leaving it blank — the outline's image_suggestions never carry a
# real asset URL, only the single generate_image tool call does.
_PLACEHOLDER_IMAGE_MARKERS = (
    "example.com",
    "example.org",
    "example.net",
    "placeholder.com",
    "via.placeholder",
    "dummyimage.com",
    "yourdomain.com",
    "your-domain.com",
    "domain.com",
    "image-url-here",
    "url-here",
    "your-image-url",
)
_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)")


def _is_placeholder_image_url(url: object) -> bool:
    """True if ``url`` looks like a hallucinated/placeholder image link rather than a real asset."""
    if not isinstance(url, str) or not url.strip():
        return False
    lowered = url.strip().lower()
    if not lowered.startswith(("http://", "https://")):
        return True
    return any(marker in lowered for marker in _PLACEHOLDER_IMAGE_MARKERS)


def _strip_placeholder_images(content_dict: dict) -> None:
    """Remove hallucinated image URLs (e.g. example.com) from generated content, in place.

    The model is only ever handed a real URL for the single tool-generated
    featured image; any other 'images' entry it fabricates a url for is a
    hallucination and must never reach WordPress (it would be uploaded as
    the featured image, or 404 as a broken inline image).
    """
    images = content_dict.get("images")
    if isinstance(images, list):
        for entry in images:
            if isinstance(entry, dict) and _is_placeholder_image_url(entry.get("url")):
                logger.warning(
                    "Stripping placeholder/hallucinated image url from 'images' field: %s",
                    entry.get("url"),
                )
                entry["url"] = None

    for field in ("body_markdown", "introduction"):
        text = content_dict.get(field)
        if not isinstance(text, str) or not text:
            continue

        def _drop_if_placeholder(match: "re.Match") -> str:
            if _is_placeholder_image_url(match.group(1)):
                logger.warning(
                    "Stripping placeholder/hallucinated image markdown from %s: %s",
                    field,
                    match.group(1),
                )
                return ""
            return match.group(0)

        cleaned = _MARKDOWN_IMAGE_RE.sub(_drop_if_placeholder, text)
        if cleaned != text:
            content_dict[field] = re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _short_text(value: object, limit: int = 700) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _format_keyword_clusters_for_generation(keyword_clusters: list[dict]) -> str:
    if not keyword_clusters:
        return "No approved keyword clusters available."

    lines = []
    for cluster in keyword_clusters[:5]:
        mapping = cluster.get("outline_mapping") or {}
        scores = cluster.get("quality_scores") or {}
        heading = (
            cluster.get("recommended_heading")
            or mapping.get("suggested_heading")
            or cluster.get("cluster_name")
        )
        placement = mapping.get("heading_level") or cluster.get("outline_placement", "H2")
        intent = cluster.get("main_intent", "")
        page_type = cluster.get("likely_serp_page_type", "")
        overall = scores.get("overall", cluster.get("overall_score", ""))
        intent_score = scores.get("intent_match", cluster.get("intent_match_score", ""))
        serp_score = scores.get("serp_overlap", cluster.get("serp_overlap_score", ""))
        content_fit = scores.get(
            "content_type_fit",
            cluster.get("content_type_fit_score", ""),
        )
        keywords = [
            str(item.get("keyword", "")).strip()
            for item in (cluster.get("keywords") or [])[:5]
            if item.get("keyword")
        ]
        lines.append(
            "\n".join(
                [
                    f"- {heading}",
                    f"  Placement: {placement}",
                    f"  Intent/Page type: {intent} / {page_type}",
                    f"  Keywords: {', '.join(keywords)}",
                    f"  Scores: overall={overall}, intent={intent_score}, "
                    f"SERP={serp_score}, content_fit={content_fit}",
                ]
            )
        )
    return "\n".join(lines)


def _outline_sections(outline: dict) -> list[dict]:
    sections = outline.get("sections") or []
    if sections:
        return sections

    content_structure = outline.get("content_structure") or {}
    sections = content_structure.get("sections") or []
    return sections if isinstance(sections, list) else []


def _format_outline_for_generation(outline: dict, content_type: str = "") -> str:
    if not outline:
        return "No approved outline available."

    lines = []
    # Scalar metadata only. `search_intent` used to be listed here, but on the
    # schemas that model it as a nested object `_short_text` stringified the raw
    # dict, so the prompt carried a literal Python repr
    # ("{'intent_type': 'informational', 'user_goal': [...]}"). It is a guidance
    # block and is rendered properly by format_guidance_for_prompt below.
    for label, key in (
        ("Title", "title"),
        ("Brief", "brief"),
        ("Tone", "tone"),
        ("Content goal", "content_goal"),
    ):
        value = outline.get(key)
        if value and not isinstance(value, (dict, list)):
            lines.append(f"{label}: {_short_text(value, 500)}")

    audience = outline.get("target_audience") or outline.get("audience")
    if audience:
        if isinstance(audience, list):
            audience = ", ".join(str(item) for item in audience[:8])
        lines.append(f"Audience: {_short_text(audience, 400)}")

    keywords = outline.get("keywords_to_include") or outline.get("semantic_keywords") or []
    if keywords:
        lines.append("Keywords: " + ", ".join(str(item) for item in keywords[:20]))

    sections = _outline_sections(outline)
    if sections:
        lines.append("Sections:")
        for index, section in enumerate(sections[:8], start=1):
            heading = section.get("heading") or section.get("title") or section.get("name") or ""
            purpose = (
                section.get("purpose") or section.get("description") or section.get("summary") or ""
            )
            lines.append(f"{index}. {_short_text(heading, 120)}")
            if purpose:
                lines.append(f"   Purpose: {_short_text(purpose, 220)}")
            key_points = section.get("key_points") or section.get("points") or []
            for point in key_points[:4]:
                lines.append(f"   - {_short_text(point, 180)}")
    else:
        # Most commercial/transactional/navigational schemas (best-tools,
        # landing-page, comparison, brand-page, sales-page, ...) have no flat
        # `sections` list — their real structural plan (hero, rankings,
        # benefits, offer, ...) lives in type-specific nested fields.
        #
        # This is resolved straight from the content type's Pydantic outline
        # model paired with the live approved outline (outline_structure.py),
        # NOT from `_render`. `_render` is a display projection built before
        # human review: it dropped `hero` for every page type, so a landing
        # page was planned with no hero at all — which is why an approved
        # brand mention had nowhere to sit at the top and kept sliding to the
        # bottom of the article. requirements_spec._expected_sections resolves
        # from the same function, so the plan the model is given and the
        # structure validation checks for cannot diverge.
        conversion_goal = outline.get("conversion_goal")
        if conversion_goal:
            lines.append(f"Conversion goal: {conversion_goal}")
        blocks = resolve_outline_structure(outline, content_type)
        if blocks:
            lines.append(
                "Structural Plan (from the approved outline — follow this structure and order):"
            )
            lines.append(format_structure_for_prompt(blocks))

    key_facts = outline.get("key_facts") or outline.get("facts") or []
    if key_facts:
        lines.append("Required facts:")
        for fact in key_facts[:6]:
            if isinstance(fact, dict):
                fact_text = _short_text(fact.get("text") or fact.get("claim") or "", 220)
                source_url = fact.get("source_url") or fact.get("url")
                if source_url:
                    lines.append(f"- {fact_text} (source: {source_url})")
                elif fact_text:
                    lines.append(f"- {fact_text}")
            else:
                lines.append(f"- {_short_text(fact, 220)}")

    approved_faqs = extract_outline_faqs(outline)
    if approved_faqs:
        faq_heading = faq_section_heading(outline, content_type)
        where = (
            f'in the section "{faq_heading}", the outline\'s FAQ section (add no other FAQ section)'
            if faq_heading
            else "in the FAQ section"
        )
        lines.append(
            f"Approved FAQs (MUST all appear verbatim/near-verbatim {where} — do not invent replacements):"
        )
        for faq in approved_faqs:
            lines.append(f"- Q: {_short_text(faq['question'], 220)}")
            if faq.get("answer"):
                lines.append(f"  A: {_short_text(faq['answer'], 400)}")

    return "\n".join(lines) if lines else "Approved outline has no compact fields."


async def _charge_delivered_image(content_state: dict, user_id, workspace_id) -> dict:
    """Charge the featured image's credit once the image is in the article.

    Once per run (image_credit_deducted), like the upfront stages. A run that can't
    pay was told not to generate one; if the balance still fell short meanwhile, or
    the charge failed, the image stays in the article and nobody is charged for it.
    """
    if content_state.get("image_credit_deducted"):
        return content_state
    stage = "featured_image"
    try:
        await consume_stage_credits(user_id, STAGE_CREDITS[stage], stage, workspace_id=workspace_id)
    except InsufficientCreditsError:
        logger.warning("generate_content: featured image delivered without its credit")
        return content_state
    except Exception:
        logger.exception("generate_content: charging the featured image failed")
        return content_state
    return {**content_state, "image_credit_deducted": True}


async def generate_content(state: REXT) -> dict:
    """
    Generates SEO-optimized content using the content agent.

    The agent can invoke tools (e.g. DuckDuckGo web search) to verify facts
    and statistics before producing the final structured output.

    Args:
        state: REXT state containing outline and context

    Returns:
        dict: Updated state with generated content
    """
    content_state = state.get("content", {})

    try:
        # 1️⃣ Get content state, topic, and content type
        topic = content_state.get("selected_topic", "")
        content_type = content_state.get("content_type", "article")

        if not topic:
            logger.error("No topic found in state")
            return {
                "content": {
                    **content_state,
                    "error": "No topic found in state",
                }
            }

        logger.info(f"Generating content for: {topic} (content type: {content_type})")

        outline = content_state.get("outline", {})
        if not outline:
            logger.warning("No outline found in state. Proceeding without it.")
        outline_str = _format_outline_for_generation(outline, content_type)
        # The keywords the user took out at the outline gate leave the cluster notes too:
        # they were built before the gate and still list every phrase as coverage to give.
        removed_keywords = [
            str(k).strip() for k in outline.get("removed_keywords") or [] if str(k).strip()
        ]
        cluster_heading_map = cluster_heading_map_without_keywords(
            outline.get("cluster_heading_map") or content_state.get("cluster_heading_map", {}),
            removed_keywords,
        )

        logger.info(f"Outline extracted: {outline_str[:20]}...")

        # 2️⃣ Prepare Reference Content (If any)
        page_content = ""
        meta_data = {}

        # 3️⃣ Focus keyword — the user's own query, not a model-chosen phrase.
        # Previously this was keywords_to_include[0] (whatever the outline model
        # happened to rank first), while the finished payload was stamped with
        # the user's keyword at the end of this function. The article was
        # therefore optimized for one phrase and reported as being about
        # another, which is what left the real focus keyphrase under-used.
        keywords_to_include = (
            outline.get("keywords_to_include") or outline.get("semantic_keywords") or []
        )
        focus_keyword = resolve_focus_keyword(state)
        primary_keyword = focus_keyword or (
            keywords_to_include[0] if keywords_to_include else topic
        )

        # The focus keyphrase has its own exact-count rule (the density block below); the other
        # approved keywords are secondary: each once, naturally (FB2.18, rext-control#699).
        secondary_keywords = [
            str(k).strip()
            for k in keywords_to_include
            if str(k).strip() and str(k).strip().casefold() != primary_keyword.casefold()
        ]
        keyword_requirements = ""
        # The cluster rule below says "only the clusters"; a keyword the user added is in no
        # cluster, so the rule names the user's keywords as allowed whenever there are any.
        approved_keywords_rule = ""
        if secondary_keywords:
            keyword_requirements = (
                "\nKEYWORD REQUIREMENTS:\n"
                f'- Focus keyphrase: "{primary_keyword}" — its exact-phrase rule is given below.\n'
                f"- Secondary keywords the user approved: {', '.join(secondary_keywords)}\n"
                "- Use each secondary keyword at least once: in a sentence where it fits naturally, or in a subheading. Never stack several in one sentence, and never repeat one to fill space.\n"
                "- The user approved these keywords themselves: use each one even when no keyword cluster lists it.\n"
                "- Prefer exact phrase matches when natural. If a long phrase is awkward, use a close natural variant that preserves the same meaning and word order.\n"
                "- Do not invent unrelated keywords or introduce new keyword themes.\n"
            )
            approved_keywords_rule = (
                " The secondary keywords the user approved (KEYWORD REQUIREMENTS below) are allowed "
                "and required as well, whether or not a cluster lists them."
            )
        if removed_keywords:
            keyword_requirements += (
                f"\nKEYWORDS THE USER REMOVED: {', '.join(removed_keywords)}\n"
                "- Do not target these phrases: no new heading built on one, and no sentence written to fit one in. A heading of the approved outline that already contains one stays exactly as approved.\n"
            )

        # 4️⃣ Extract SEO & SERP Insights (CRITICAL)
        seo_result = state.get("seo_result", {})
        keyword_clusters = clusters_without_keywords(
            seo_result.get("keyword_clusters", []), removed_keywords
        )
        keyword_clusters_context = _format_keyword_clusters_for_generation(keyword_clusters)
        cluster_heading_map_context = (
            format_cluster_heading_map_for_prompt(cluster_heading_map)
            if cluster_heading_map
            else "No cluster heading map available."
        )
        serp_backlinks = seo_result.get("serp_backlinks", {})
        serp_normalized = state.get("serp_normalized", {})

        # SEO Metrics
        backlink_volume = serp_backlinks.get("backlinks", 0)
        referring_domains = serp_backlinks.get("referring_domains", 0)
        intent = serp_backlinks.get("main_intent", "Informational")

        # SERP Data
        top_results = serp_normalized.get("normalize_results", [])[:5]
        questions = serp_normalized.get("questions", [])
        related_topics = serp_normalized.get("related_topics", [])
        # Format Competitor & SEO Insights
        competitor_list = []
        for res in top_results:
            competitor_list.append(
                f"- {res.get('title', '')} (Position {res.get('position', '?')}): "
                f"{_short_text(res.get('snippet', ''), 260)}"
            )
        serp_insights = "\n".join(competitor_list)
        seo_signals = (
            f"SEO SIGNALS:\n"
            f"- Primary Intent: {intent}\n"
            f"- Average Backlink Volume: {backlink_volume}\n"
            f"- Referring Domains: {referring_domains}\n"
            f"- People Also Ask (Questions): {', '.join(questions[:5])}\n"
            f"- Related SEO Topics: {', '.join(related_topics[:10])}\n"
        )

        competitor_insights = f"TOP SERP COMPETITORS:\n{serp_insights}\n\n{seo_signals}"

        # 5️⃣ Extract Tone & Metadata
        tone = outline.get("tone", "Professional")
        target_word_count = outline.get("target_word_count", 2000)
        # Percentage-only tolerance — a flat floor (e.g. 200) is a 40% overshoot
        # allowance on a 500-word target but negligible on a 3000-word one.
        #
        # The ceiling comes from the same band check_word_count_band and
        # humanize_content use. It was a separate 15% here while the gate used
        # 12%, so a writer following the prompt could land outside the band the
        # article is graded against.
        _, max_word_count = compute_word_target_band(target_word_count)
        logger.info(f"Tone: {tone}")

        # Exact-phrase + occurrence-count instruction, generated from the same
        # policy check_keyword_density enforces — so the target the writer is
        # given and the band it will be graded against cannot drift apart.
        # Derived from target_word_count rather than the (not yet written) final
        # length; the gate re-derives it from the actual length afterward.
        density_instruction = build_density_prompt_instruction(
            keyphrase=primary_keyword,
            target_word_count=target_word_count,
            content_type=content_type,
        )
        # H2/H3 length + keyphrase-distribution rules, generated from the same
        # module check_subheading_keyphrase / check_subheading_length enforce.
        subheading_instruction = build_subheading_prompt_instruction(
            primary_keyword, outline.get("keyphrase_synonyms") or []
        )

        # Extract key_facts and image_suggestions from the outline
        key_facts = outline.get("key_facts", []) or []
        image_suggestions = outline.get("image_suggestions", []) or []

        key_facts_str = ""
        if key_facts:
            facts_lines = "\n".join(
                (
                    f"  - {f.get('text', str(f))}"
                    + (f" (source: {f['source_url']})" if f.get("source_url") else "")
                    if isinstance(f, dict)
                    else f"  - {f}"
                )
                for f in key_facts
            )
            key_facts_str = f"\nKEY FACTS TO INCLUDE IN CONTENT:\n{facts_lines}\n"

        # Content-type-aware citation style. Fixes a concrete, reported
        # failure mode: 2-3 external links dumped as a bare list at the end
        # of the article instead of woven into the sentence that makes the
        # claim they support. See evidence_placement_policy.py.
        evidence_policy = resolve_evidence_placement_policy(content_type)
        evidence_str = (
            f"\n========================\n"
            f"CITATION STYLE FOR THIS CONTENT TYPE\n"
            f"========================\n"
            f"{evidence_policy['guidance']}\n"
            f"Recommended citation count for this content type: up to {evidence_policy['max_recommended_citations']}. "
            f"More than that dilutes the piece — cite the strongest evidence, not everything you found.\n"
        )

        # Guidance the reviewer approved that shapes HOW the article is written
        # (E-E-A-T signals, engagement plan, topical cluster, intent, reference
        # list). These previously reached nothing: they are excluded from the
        # structural plan by design, and nothing else read them, so an approved
        # E-E-A-T plan provably could not affect the article.
        guidance_str = format_guidance_for_prompt(resolve_guidance_blocks(outline, content_type))
        if guidance_str:
            guidance_str += "\n\n"

        # schema.org types for the JSON-LD block. Without this the writer
        # defaulted to "Article" for all 34 content types.
        schema_org_str = format_schema_guidance_for_prompt(outline, content_type) + "\n\n"

        image_suggestions_str = ""
        if image_suggestions:
            img_lines = "\n".join(
                (
                    f"  - Section '{img.get('section', '?')}': "
                    f"{img.get('description', '')} | "
                    f"alt: {img.get('alt_text_template', '')}"
                    if isinstance(img, dict)
                    else f"  - {img}"
                )
                for img in image_suggestions
            )
            image_suggestions_str = (
                f"\nIMAGE PLACEMENT GUIDE (populate the 'images' output field):\n{img_lines}\n"
                f"For each image suggestion above, add an entry to the 'images' field with:\n"
                f"  alt_text: SEO-optimized alt text based on the template\n"
                f"  context: what the image shows\n"
                f"  placement: which section it belongs to\n"
                f"  url: leave this null/empty — you do NOT have a real image for these. "
                f"NEVER invent, guess, or use a placeholder URL (e.g. example.com) for it.\n"
            )

        # Only point at the placement guide when one was actually rendered.
        # Outlines no longer plan images, so without this guard the prompt
        # referred the writer to a block that isn't there. Alt text is still
        # required — that instruction lives on the `images` field description.
        images_instruction = (
            "Populate the 'images' output field using the image placement guide above.\n"
            if image_suggestions_str
            else "For any image you reference, add an entry to the 'images' output field with "
            "SEO-optimized alt_text (include the focus keyphrase in at least one), the "
            "section it belongs to, and a null url — never invent an image URL.\n"
        )

        # 6️⃣ Build internal links block from outline state
        internal_links = outline.get("internal_links") or []
        internal_links_str = ""
        if internal_links:
            link_lines = "\n".join(
                f"  - [{lnk.get('title', lnk.get('url', ''))}]({lnk.get('url', '')})  [status={lnk.get('status', '').upper()}  score={lnk.get('score', 0):.2f}]"
                for lnk in internal_links
            )
            internal_links_str = (
                f"\n========================\n"
                f"LINKS TO EMBED — ZERO EXCEPTIONS, ALL MUST APPEAR\n"
                f"========================\n"
                f"There are {len(internal_links)} link(s) below. Every single one MUST appear as an inline hyperlink inside the article body — written into the section field (or introduction) where it fits, not into a separate field. Missing even one is a failure.\n\n"
                f"{link_lines}\n\n"
                f"HOW TO EMBED — MANDATORY PROCESS:\n"
                f"Before writing, assign each link to the section where it fits best topically.\n"
                f"Weave it into an existing sentence as natural anchor text — do NOT create a throwaway sentence just to hold the link.\n"
                f"  GOOD: '...which is why [AI's role in patient care](url) is reshaping how hospitals operate.'\n"
                f"  GOOD: '...tools like [our guide on AI innovations](url) document how fast this landscape moves.'\n"
                f"  BAD:  'Read more: [title](url)' — only acceptable if the article has zero topical overlap with the link, which is rare.\n\n"
                f"ANCHOR TEXT LANGUAGE — CRITICAL: NEVER write 'internal link', 'internal resource', 'internal page', or any word that signals same-site origin to the reader. Anchor text must read as natural, topically relevant prose.\n"
                f"  BAD: 'check out this internal resource', 'see our internal guide on X'\n"
                f"  GOOD: '...as explored in [our breakdown of X](url)...', '...detailed in [this guide to Y](url)...'\n\n"
                f"SELF-CHECK before submitting: count the links above. Confirm that exact count of URLs appear inside the section text you wrote. If any are missing — add them before submitting.\n"
            )

        # 7️⃣ Build brand promotion block from outline state (product-led marketing)
        brand_promo_str = ""
        final_brand_reminder = ""
        if outline.get("promote_brand"):
            promo = outline.get("brand_voice_promotion") or {}
            brand_name = promo.get("brand_name") or "the brand"
            brand_url = (promo.get("brand_url") or "").strip()
            about = promo.get("about") or ""
            selling_pos = promo.get("selling_position") or ""

            if brand_url:
                link_instructions = (
                    f"- The ONLY approved URL for this mention is: {brand_url}\n"
                    f"- Hyperlink the mention exactly once: [{brand_name}]({brand_url}), woven into a sentence as natural anchor text — not appended, not bare.\n"
                    f"- Do NOT reuse a search-result URL, an internal link URL, or any other URL for this brand mention — {brand_url} is the only correct target.\n"
                )
                good_example = f"  GOOD: '...tools like [{brand_name}]({brand_url}) <a benefit stated in the About/selling-position text above>.'\n"
            else:
                link_instructions = (
                    f"- No verified URL is available for {brand_name} — mention it by name only, as plain text.\n"
                    f"- Do NOT hyperlink {brand_name}. Do NOT invent a URL for it. Do NOT attach a search-result or internal-link URL to this mention — those belong to their own citations only.\n"
                )
                good_example = f"  GOOD: '...tools like {brand_name} <a benefit stated in the About/selling-position text above>.'\n"

            # Research-derived, per-content-type PLM (product-led marketing)
            # placement policy — a blog earns one soft mid-body mention while
            # a sales page can lead above the fold, and a glossary should
            # almost never carry one at all. See brand_placement_policy.py
            # for the full intensity/placement/guardrail table across all 34
            # content types, and check_brand_placement_policy /
            # check_brand_factual_grounding (validation.py) for the
            # deterministic checks that verify this actually happened.
            # The content type's policy at the prominence the user chose for
            # this article (brand_prominence on the approved outline).
            policy = resolve_article_brand_policy(content_type, outline)
            multi_mention_ok = policy["intensity"] in ("high", "maximal")
            # Who asks for several mentions: the format itself (a sales page,
            # a comparison) or the user, who chose a prominent mention.
            chosen_prominent = policy.get("prominence") == "prominent"
            mention_basis = (
                "The prominent mention the user chose"
                if chosen_prominent
                else "This content type's format"
            )
            central_line = (
                f"- The user chose a PROMINENT mention: {brand_name} is central to this article "
                f"(see PLACEMENT below) — it is not a single throwaway aside here.\n"
                if chosen_prominent
                else f"- This content type's format is BUILT around {brand_name} (see PLACEMENT "
                f"below) — it is not a single throwaway aside here.\n"
            )

            # Which of the two placement strings applies is a property of the
            # policy, resolved centrally so the prompt and the schema-level
            # directive (brand_schema_context.py) cannot state different
            # placements for the same article.
            placement_text, placement_is_forced = resolve_placement_instruction(policy)
            if placement_is_forced:
                placement_instruction = (
                    f"- PLACEMENT (exception — this content type normally carries NO product promotion, "
                    f"but it was explicitly approved for this specific article anyway): {placement_text}\n"
                )
            else:
                placement_instruction = f"- PLACEMENT: {placement_text}\n"
            guardrail_instruction = f"- FORMAT GUARDRAIL: {policy['guardrail']}\n"
            # For ranked-list types (best-tools, product-roundup, comparison,
            # alternatives), point at the CONCRETE list from the Structural
            # Plan above rather than leaving "put it first" as free-floating
            # prose disconnected from the actual outline structure.
            ranked_list_injection = build_brand_structural_injection(
                content_type, brand_name, policy
            )

            if multi_mention_ok:
                mention_count_instruction = (
                    f"- {mention_basis} calls for {brand_name} to appear more than once, per the "
                    f"PLACEMENT guidance above (e.g. hero + body, or throughout a comparison/review) — this is "
                    f"one of the few formats where that's appropriate; still every mention must be genuine and specific, never filler repetition.\n"
                )
                # A brief explanatory clause is fine for a single soft aside
                # (low/moderate intensity types), but a hero/high-intensity
                # placement is not "the name is present" — it must read as
                # genuine marketing copy: concrete, specific benefits, not
                # just an identifier attached to someone else's sentence.
                integration_depth_instruction = (
                    f"- INTEGRATION DEPTH — CRITICAL: naming {brand_name} is not enough. Wherever the PLACEMENT "
                    f"guidance calls for it (hero, headline, featured entry, etc.), write real, specific "
                    f"value-proposition copy — concrete benefits, outcomes, or capabilities drawn from the "
                    f"About/selling-position text above, in full sentences, not a single trailing clause. A hero "
                    f"section built around {brand_name} should read like genuine marketing copy for it, not a "
                    f"passing reference to it inside a sentence about something else.\n"
                )
            else:
                mention_count_instruction = f"- Make at most ONE mention in the whole article. Only skip the mention entirely if you have checked every section and genuinely none relate to {brand_name} — this should be rare, not your default; a forced or irrelevant plug is worse than no mention, but omitting an approved mention that does fit is also a failure.\n"
                integration_depth_instruction = (
                    "- Give it real substance, not just a name-drop: attach a specific, concrete benefit or "
                    "outcome (drawn from the About/selling-position text above) to the mention — not a vague "
                    "qualifier like 'a great tool' or 'this platform helps.'\n"
                )

            # Retrieval in AI answer engines works on passages, not whole
            # documents: a self-contained claim in the opening sentences of a
            # section is extractable and citable, while the same claim buried in
            # that section's fourth paragraph — surrounded by context it depends
            # on — is not. Quantified claims are the strongest lever available
            # here, which is also what makes the mention read as substantive to a
            # human rather than as filler.
            extractability_instruction = (
                f"- EXTRACTABLE PLACEMENT — CRITICAL: put the {brand_name} mention in the FIRST one or two "
                f"sentences of whichever section carries it, not buried in a later paragraph of that section. "
                f"Write it as a self-contained statement that still makes sense read on its own, out of "
                f"context: name {brand_name}, say what it does, and attach a concrete outcome or specific "
                f"capability from the About/selling-position text — a number or timeframe ONLY if that text "
                f"states one; never invent a figure to make the mention quantified. A reader (or an AI "
                f"answer engine) who sees only that sentence should come away knowing what {brand_name} is and "
                f"why it matters here.\n"
            )

            brand_promo_str = (
                f"\n========================\n"
                f"PRODUCT-LED MENTION — {brand_name} — REQUIRED, USER-APPROVED\n"
                f"========================\n"
                f"Brand: {brand_name}\n"
                + (f"About: {about}\n" if about else "")
                + (f"Selling position: {selling_pos}\n" if selling_pos else "")
                + "\nINSTRUCTIONS:\n"
                "- The user already reviewed and approved this promotion at the outline stage — this is a REQUIRED element of the article, not an optional flourish. Do not second-guess or omit it out of caution.\n"
                + (
                    central_line
                    if multi_mention_ok
                    else "- This is a single, soft product-led mention — not a case study and not a citation. It does NOT need a search_tool citation or a source in the `facts` field, but any specific fact about the brand (pricing, features, release status) must match its About text or its VERIFIED CURRENT PRODUCT FACTS entries.\n"
                )
                + f"- Find the section(s) where the article already discusses a problem or need that {brand_name} genuinely addresses (based on the about/selling position above), and mention it there. Do not force it into an unrelated section.\n"
                f"{placement_instruction}"
                f"{guardrail_instruction}"
                f"{ranked_list_injection}"
                f"{extractability_instruction}"
                f"{integration_depth_instruction}"
                f"- Mention {brand_name} clearly and explicitly by name — never refer to it only indirectly (e.g. 'this platform', 'a tool like this') when you mean {brand_name} specifically. If the article positions {brand_name} as a top option/recommendation, say so by name, not by allusion.\n"
                f"{mention_count_instruction}"
                f"- FACTUAL ACCURACY — CRITICAL: only state capabilities, technologies, platforms, or claims that appear VERBATIM or as an obvious close paraphrase in the About/selling position text above. Do NOT name any specific technology, framework, platform, or stack that is not explicitly stated there — if the About text doesn't say what {brand_name} is built on or integrates with, do NOT guess or invent one (e.g. do not say it's 'built on React' unless the About text says so). When in doubt, describe {brand_name} in the general terms actually given, not a more specific technical claim you're inferring from the article's own topic.\n"
                f"- NEVER write 'sponsored', 'advertisement', or otherwise signal it as paid content.\n"
                f"- Use the exact brand name: {brand_name}.\n"
                f"{link_instructions}"
                f"{good_example}"
                f"  BAD:  'Check out this product: {brand_name}.' (throwaway sentence)\n"
                f"  BAD:  Bending an unrelated section around {brand_name} just to include it.\n"
                f"  BAD:  Tacking '{brand_name} can help with this.' onto the very end of the article as a closing line.\n"
                f"  BAD:  Inventing a specific technology/platform claim about {brand_name} that isn't in the About/selling position text.\n"
                f"  BAD:  Inventing a metric, price, customer count or integration for {brand_name}, or a competitor weakness to make it look better.\n"
                f"  BAD:  An unsupported absolute ('{brand_name} is the best', 'the clear winner', 'leads the market') — position it by fit instead ('a strong fit for teams that need ...').\n"
                + (
                    f"SELF-CHECK before submitting: confirm {brand_name} appears prominently per the PLACEMENT guidance above (not just once, buried mid-article), and that every specific claim about it traces back to the About/selling position text given above.\n"
                    if multi_mention_ok
                    else f"SELF-CHECK before submitting: confirm {brand_name} appears exactly once, attached to a short explanatory clause — not a bare name — and that every specific claim about it traces back to the About/selling position text given above.\n"
                )
            )

            # Repeated once more at the very end of the message (recency
            # reinforcement) — this prompt is long, and a structural-position
            # instruction stated only once, in the middle, is measurably more
            # likely to be under-weighted by the time the model reaches the
            # final generation instructions than one restated right before
            # generation starts.
            if policy["prefers_top"]:
                final_brand_reminder = (
                    f"\nFINAL CHECK BEFORE YOU WRITE: {brand_name} must be one of the very first things named in this "
                    f"piece — per the PLACEMENT instruction above, not buried after the midpoint or added only at the end. "
                    f"Before finishing, re-read your own opening (or ranked list) and confirm {brand_name} is actually there.\n"
                )

        # The user chose NO mention (rext-control#700). Skipping the promotion block alone left the
        # writer free to name the brand, and the outline, generated before the choice, may already
        # name it in a product list or the call to action.
        excluded = excluded_brand_of(outline, title=topic, keyphrase=primary_keyword)
        if excluded and not outline.get("promote_brand"):
            excluded_name = excluded["brand_name"]
            brand_promo_str = (
                f"\n========================\n"
                f"BRAND EXCLUSION — REQUIRED\n"
                f"========================\n"
                f"The user chose NO mention of {excluded_name}. Do not name {excluded_name}, or link to "
                f"its site (the internal links you were given above stay), anywhere: not in the title, "
                f"the introduction, the body, a heading, a list, the FAQs, the call to action or its "
                f"link, the meta title or the meta description. Where the "
                f"outline names {excluded_name} (a product list, a comparison, the call to action), "
                f"write that part without it: name another real product where a list needs one, or "
                f"none. This overrides any instruction to follow the outline's wording exactly.\n"
            )
            final_brand_reminder = (
                f"\nFINAL CHECK BEFORE YOU WRITE: {excluded_name} appears nowhere in what you write, "
                f"including the call to action and the meta description.\n"
            )

        # 7️⃣b Build CTA block, only if the approved outline declares one for this content type
        outline_cta = resolve_outline_cta(outline)
        cta_str = ""
        cta_brand = brand_kept_out_of_cta(outline)
        if outline_cta and cta_brand and brand_named_in(outline_cta["text"], cta_brand):
            # The outline's call to action names a brand the user's choice keeps out of a call to
            # action (None, or Subtle's one body mention): its exact text would contradict that.
            cta_str = (
                f"\n========================\n"
                f"CALL-TO-ACTION — REQUIRED\n"
                f"========================\n"
                f'The approved outline defines this CTA: "{outline_cta["text"]}"\n'
                f"It names {cta_brand}, but the user's choice keeps {cta_brand} out of the call to "
                f"action. Populate the 'cta' output field ({{text, url, placement}}) with the same "
                f"intent in your own words, WITHOUT naming {cta_brand} or linking to its site, and make "
                f"sure that same text also appears verbatim as an actual call-to-action inside "
                f"body_markdown or the introduction.\n"
            )
        elif outline_cta:
            cta_link_rule = (
                f"Its link must not point to {cta_brand}'s site: the user's choice keeps "
                f"{cta_brand} out of the call to action.\n"
                if cta_brand
                else ""
            )
            cta_str = (
                f"\n========================\n"
                f"CALL-TO-ACTION — REQUIRED\n"
                f"========================\n"
                f'The approved outline defines this CTA: "{outline_cta["text"]}"\n'
                f"Populate the 'cta' output field ({{text, url, placement}}) using this exact CTA text "
                f"(or a close natural variant preserving the same meaning), and make sure that same "
                f"text also appears verbatim as an actual call-to-action inside body_markdown or the introduction.\n"
                f"{cta_link_rule}"
            )

        # 7️⃣c Title + subject lock.
        #
        # The user picked this exact title at the topic-selection step; it is
        # the article's final H1 and page title, and nothing downstream may
        # reword it. The subject lock is derived from the title itself (see
        # title_subject.describe_subject_lock) so the instruction names the
        # actual entity class the title promises -- "the title is about
        # agencies, write about agencies" -- rather than a generic plea to stay
        # on topic that a model can satisfy while still writing about tools.
        title_lock_str = (
            f"\n========================\n"
            f"TITLE — FIXED, USER-SELECTED\n"
            f"========================\n"
            f'The user selected this exact title: "{topic}"\n'
            f"- Output it VERBATIM in the `title` field. Character for character.\n"
            f"- Do NOT reword, shorten, lengthen, re-case, re-punctuate or "
            f"'improve' it for SEO. It is already SEO-validated.\n"
            f"- Do NOT write a different H1 at the top of body_markdown.\n"
            f"- Output the same exact string in `meta_title`. Neither field may differ from it.\n"
            f"{describe_subject_lock(topic)}\n"
            f"========================\n\n"
        )

        # 8️⃣ Build the human message for the agent
        # (system prompt is already embedded in the agent
        human_message_content = (
            f"Content Type: {content_type}\n"
            f"Topic: {topic}\n\n"
            f"{title_lock_str}"
            f"Primary Keyword: {primary_keyword}\n"
            f"Target Word Count: {target_word_count}-{max_word_count} words (stay within this range — do not go meaningfully under or over)\n\n"
            f"COMPETITIVE LANDSCAPE:\n"
            f"{competitor_insights}\n"
            f"- Go deeper than these competitors\n"
            f"- Cover gaps they missed\n"
            f"- Offer a unique angle/perspective\n\n"
            f"Approved Outline:\n{outline_str}\n\n"
            # Placed immediately adjacent to the Structural Plan above (not
            # after several unrelated sections) — for prefers_top content
            # types this instruction directly references and edits that
            # structure ("add it as the first entry in the list above"), and
            # long-context instruction-following is measurably weaker when a
            # structural edit instruction is separated from what it edits by
            # a lot of intervening, unrelated content.
            f"{brand_promo_str}"
            f"{cta_str}"
            f"Approved Keyword Clusters:\n{keyword_clusters_context}\n\n"
            f"Cluster-to-Heading Map:\n{cluster_heading_map_context}\n\n"
            f"{guidance_str}"
            f"{key_facts_str}"
            f"{evidence_str}"
            f"{image_suggestions_str}"
            f"{internal_links_str}"
            f"{schema_org_str}"
            f"Reference / Source Content:\n{page_content}\n\n"
            f"Meta_data:\n{meta_data}\n\n"
            f"Tone:\n{tone}\n\n"
            f"Generate complete SEO-optimized content following the outline.\n"
            f"STRUCTURE FIDELITY — CRITICAL: follow the EXACT structure, section order, and headings given in "
            f"the 'Approved Outline' section above (including its Hero Angle and Structural Plan, when present) "
            f"— do not invent a different structure, reorder sections, merge them, or skip any listed there.\n"
            f"CRITICAL KEYWORD INSTRUCTION: Use only the approved keyword clusters above."
            f"{approved_keywords_rule} "
            f"The cluster-to-heading map assigns KEYWORDS to sections — it does not define the sections "
            f"themselves. Place each cluster's keywords into whichever Structural Plan section covers that "
            f"topic; do NOT create a new section, rename one, or reorder them to match a suggested heading. "
            f"Where the two disagree, the Structural Plan wins. Do not add rejected or mixed-intent keyword themes.\n"
            f"{keyword_requirements}"
            f"{density_instruction}"
            f"{subheading_instruction}"
            f"Incorporate ALL key facts listed above verbatim in the relevant sections — except a key fact with no "
            f"source, which is an unverified planning note: confirm it with search_tool or leave it out.\n"
            f"Embed ALL links listed above — and every citation link — inside the article prose as natural anchor text, "
            f"written into the section it supports (when the output has section fields, write links inside those "
            f"sections' markdown; the article body is assembled from them). Never label them as 'internal' to the reader.\n"
            f"LINK REL ATTRIBUTE RULE: in the 'internal_links' output field, leave 'rel' empty/null (internal links are DoFollow). "
            f"In the 'outbound_links' output field, set 'rel' to 'nofollow' unless the link is a verified partner/citation you have a specific reason to keep followed — "
            f"in that case use 'sponsored' instead of 'nofollow'.\n"
            f"Populate the 'facts' output field with each fact used (text + source_url).\n"
            f"FACTUAL INTEGRITY: every price, plan, statistic, version, feature, integration, release status and "
            f"competitor fact must come from the VERIFIED CURRENT PRODUCT FACTS block (when present), a search_tool "
            f"result, the approved brand text, or the author profile — "
            f"figures in the outline or the competitor snippets above are planning hints, not verified facts. "
            f"If you cannot verify one, leave it out or make the point without it; never guess a value.\n"
            f"{images_instruction}"
            f"Ensure you outperform the competitors listed above.\n"
            f"{final_brand_reminder}"
        )

        # 7️⃣ Create the content agent
        logger.info("Creating content agent...")
        serp_payload = state.get("serp_payload", {})
        user_id = serp_payload.get("user_id")
        workspace_id = serp_payload.get("workspace_id")

        # Deduct the content stages before agent invoke (once, upfront). Guarded
        # by credits_deducted so a checkpoint-driven resume of this node (e.g.
        # after a transient failure later in the function) doesn't deduct twice.
        # The featured image is charged only once it is delivered (below).
        if not content_state.get("credits_deducted"):
            for _stage in ("content_drafting", "humanization", "deep_research"):
                try:
                    await consume_stage_credits(
                        user_id, STAGE_CREDITS[_stage], _stage, workspace_id=workspace_id
                    )
                except InsufficientCreditsError as _e:
                    _emit_credit_event(
                        _e.available, _e.stage, _e.required, step="credits.exhausted"
                    )
                    return {
                        "content": {
                            **content_state,
                            "error": "insufficient_credits",
                            "error_code": "insufficient_credits",
                        }
                    }
        content_state = {**content_state, "credits_deducted": True}

        # One requirements spec for this node — brand context for research here,
        # subheading enforcement and link protection below.
        spec = build_requirements_spec(outline, content_type, focus_keyword, topic)

        # Own counters (search count, image task, search results) instead of
        # letting create_content_agent fabricate them — this node needs them
        # after the agent returns, both to resolve the image inline (below)
        # and to hand validate_content real citation ground truth via
        # generation_meta.searched_results.
        counters = {"search": [0], "image_task": None, "search_results": []}

        # The image is charged on delivery, so check now that the run can pay for
        # it: without the credit the writer gets the manual-upload placeholder
        # instead of a paid image nobody is charged for.
        if (
            settings.AI_IMAGE_GENERATION_ENABLED
            and not content_state.get("image_credit_deducted")
            and not await can_afford_stage(user_id, "featured_image", workspace_id=workspace_id)
        ):
            counters["image_allowed"] = False
            logger.info(
                "generate_content: no credit left for the featured image; not generating it"
            )

        # Current facts from the official sites of the brand and every product the
        # outline names, fetched before writing. The calls count against the SAME
        # search budget as the writer's search_tool (the shared counter), so the
        # article's total Tavily calls stay within SEARCH_HARD_CAP. The records lead
        # the writer's message and seed searched_results, so citation/claim
        # validation and repair treat them as ground truth. Never raises.
        _, competitor_domains = await _fetch_known_entities(workspace_id)
        official_facts = await research_official_facts(
            outline, spec.get("brand_context"), competitor_domains, counters["search"]
        )
        counters["search_results"].extend(official_facts)
        human_message_content = (
            format_official_facts_for_prompt(official_facts) + human_message_content
        )

        generated_model = get_generated_content_model(content_type)

        # Structured body (allow-listed content types only). The article's
        # sections become typed fields derived from the APPROVED OUTLINE, so
        # structure is guaranteed by constrained decoding instead of requested in
        # prose and pattern-matched afterwards. `body_markdown` is reassembled
        # from those blocks below, so everything downstream is unchanged.
        #
        # Any failure to derive falls back to today's generation rather than
        # breaking the run — an underivable structure degrades, it does not stop
        # production.
        structured_blocks = None
        if uses_structured_body(content_type):
            derived = build_structured_content_model(outline, content_type, generated_model)
            if derived is not None:
                generated_model, structured_blocks = derived
            else:
                logger.info(
                    "generate_content: structured body unavailable for content_type=%s; "
                    "using unstructured generation.",
                    content_type,
                )
        agent = await create_content_agent(
            content_type=content_type,
            user_id=user_id,
            counters=counters,
            response_format=ToolStrategy(generated_model, handle_errors=True),
        )
        agent_input = {
            "messages": [HumanMessage(content=human_message_content)],
            "serp_payload": {
                **serp_payload,
                "user_id": user_id,
                "workspace_id": workspace_id,
            },
            "content": {
                "outline": outline,
                "selected_topic": topic,
                "content_type": content_type,
                "keyword_clusters": keyword_clusters,
                "cluster_heading_map": cluster_heading_map,
            },
        }

        # 8️⃣ Stream agent events → forward tokens & tool calls to frontend
        write = get_stream_writer()
        final_messages = []
        # Typed Pydantic model instance if the agent returns one.
        structured_output = None

        # The schema name used by ToolStrategy for the artificial structured-output tool
        _STRUCTURED_OUTPUT_TOOL_NAME = generated_model.__name__
        # Internal sub-tools that should not appear as separate UI events
        _INTERNAL_TOOL_NAMES = {"tavily_search_results_json", "tavily_search"}

        # Instead we match the root completion by run_id.
        agent_root_run_id: str | None = None

        # Track query from tool_start keyed by run_id; emitted once on tool_end
        _pending_tool_queries: dict[str, str] = {}

        async for event in agent.astream_events(
            agent_input,
            version="v2",
            config={"recursion_limit": 50},
        ):
            kind = event["event"]
            tool_name = event.get("name", "")
            event_run_id = event.get("run_id", "")

            # Capture the root run_id from the very first chain-start event
            if kind == "on_chain_start" and agent_root_run_id is None:
                agent_root_run_id = event_run_id

            # Token-by-token LLM output
            elif kind == "on_chat_model_stream":
                chunk = event["data"].get("chunk")
                if chunk:
                    raw = chunk.content
                    if isinstance(raw, str):
                        token = raw
                    elif isinstance(raw, list):
                        token = "".join(
                            p.get("text", "")
                            for p in raw
                            if isinstance(p, dict) and p.get("type") == "text"
                        )
                    else:
                        token = ""

                    # ToolStrategy emits structured output as tool-call argument
                    # fragments (not as plain content). Capture those so the frontend
                    # can do live JSON field extraction (e.g. body_markdown appears
                    # character-by-character instead of dumping all at once).
                    if not token:
                        for tc in chunk.tool_call_chunks or []:
                            if tc.get("args"):
                                token += tc["args"]

                    if token:
                        write({"type": "token", "content": token})

            # on_chat_model_end: ToolStrategy never invokes the fake structured-output tool —
            # it parses args directly inside the model node. So on_tool_start never fires
            # for it. The structured content is in data.output.tool_calls[].args here.
            elif kind == "on_chat_model_end":
                output_msg = event["data"].get("output")
                if output_msg is not None and hasattr(output_msg, "tool_calls"):
                    for tc in output_msg.tool_calls:
                        if tc.get("name") == _STRUCTURED_OUTPUT_TOOL_NAME:
                            try:
                                structured_output = generated_model(**tc["args"])
                                logger.debug(
                                    "Captured %s from on_chat_model_end",
                                    generated_model.__name__,
                                )
                            except Exception as e:
                                logger.warning(
                                    "Structured output parse failed: %s | arg keys: %s",
                                    e,
                                    list(tc.get("args", {}).keys()),
                                )

            # Real tool call started — emit immediately for live UI, store query for tool_end
            elif (
                kind == "on_tool_start"
                and tool_name != _STRUCTURED_OUTPUT_TOOL_NAME
                and tool_name not in _INTERNAL_TOOL_NAMES
            ):
                tool_input = event["data"].get("input")
                logger.info(
                    "on_tool_start: name=%s input_type=%s input=%r",
                    tool_name,
                    type(tool_input).__name__,
                    tool_input,
                )
                if isinstance(tool_input, str):
                    query = tool_input
                elif isinstance(tool_input, dict):
                    str_vals = [str(v) for v in tool_input.values() if v and str(v).strip()]
                    query = max(str_vals, key=len) if str_vals else ""
                else:
                    query = str(tool_input) if tool_input else ""
                _pending_tool_queries[event_run_id] = query
                write(
                    {
                        "type": "tool_start",
                        "id": event_run_id,
                        "name": tool_name,
                        "query": query,
                    }
                )

            # Real tool call finished — emit single event with query + results
            elif (
                kind == "on_tool_end"
                and tool_name != _STRUCTURED_OUTPUT_TOOL_NAME
                and tool_name not in _INTERNAL_TOOL_NAMES
            ):
                raw_output = event["data"].get("output", "")
                logger.info(
                    "on_tool_end: name=%s output_type=%s",
                    tool_name,
                    type(raw_output).__name__,
                )
                query = _pending_tool_queries.pop(event_run_id, "")

                # Normalise to a list of result dicts regardless of output format
                results = []
                if isinstance(raw_output, list):
                    results = raw_output
                elif hasattr(raw_output, "content"):
                    try:
                        parsed = json.loads(raw_output.content)
                        results = parsed if isinstance(parsed, list) else [parsed]
                    except Exception:
                        results = [{"body": str(raw_output.content)[:360]}]
                elif isinstance(raw_output, str):
                    try:
                        parsed = json.loads(raw_output)
                        results = parsed if isinstance(parsed, list) else [parsed]
                    except Exception:
                        results = [{"body": raw_output[:360]}]
                elif isinstance(raw_output, dict):
                    results = [raw_output]

                # Detect hard-cap block: single dict with "error" key containing "cap"
                if (
                    len(results) == 1
                    and isinstance(results[0], dict)
                    and "cap" in results[0].get("error", "").lower()
                ):
                    write(
                        {
                            "type": "tool_end",
                            "id": event_run_id,
                            "name": tool_name,
                            "query": query,
                            "blocked": True,
                        }
                    )
                    continue

                count = len(results)
                lines = []
                for item in results[:3]:
                    if isinstance(item, dict):
                        title = item.get("title", "")
                        body = item.get("body", item.get("snippet", item.get("content", "")))
                        if title:
                            lines.append(f"• {title}: {str(body)[:120]}")
                        elif body:
                            lines.append(f"• {str(body)[:120]}")
                    elif isinstance(item, str):
                        lines.append(f"• {item[:120]}")
                snippet = (
                    "\n".join(lines) if lines else (str(raw_output)[:360] if raw_output else "")
                )

                write(
                    {
                        "type": "tool_end",
                        "id": event_run_id,
                        "name": tool_name,
                        "query": query,
                        "count": count,
                        "output": snippet,
                    }
                )

            # Prefer the final chain-end state for the structured output.
            elif kind == "on_chain_end":
                out = event["data"].get("output", {})
                if isinstance(out, generated_model):
                    structured_output = out
                elif isinstance(out, dict):
                    sr = out.get("structured_response")
                    if isinstance(sr, generated_model):
                        structured_output = sr
                    elif isinstance(sr, dict) and sr:
                        try:
                            structured_output = generated_model(**sr)
                        except Exception:
                            pass
                    if "messages" in out and not final_messages:
                        final_messages = out["messages"]

        # 9️⃣ Extract structured content from the agent output
        content_dict = None

        if structured_output is not None:
            content_dict = structured_output.model_dump()
        else:
            # Last-resort fallback: parse JSON from the last AIMessage
            for msg in reversed(final_messages):
                if isinstance(msg, AIMessage) and msg.content:
                    try:
                        content_dict = json.loads(msg.content)
                        break
                    except (json.JSONDecodeError, TypeError):
                        continue

        if not content_dict:
            raise ValueError("Content agent returned no structured output")

        # Collapse the generated section blocks into `body_markdown` and drop the
        # block fields, so from here on the payload has exactly the shape every
        # downstream stage already expects. Validation, repair, humanization,
        # EEAT/on-page/readability scoring, persistence and the WordPress
        # publisher are all unchanged by structured generation.
        unplaced_links: list[dict] = []
        if structured_blocks:
            content_dict = assemble_structured_payload(content_dict, structured_blocks)
            unplaced_links = content_dict.pop(UNPLACED_LINKS_KEY, None) or []

        # The outline's CTA fields steer the text; a line that only prints one as a
        # label ("**Primary CTA:** Explore Features") never stays in the article.
        content_dict = strip_cta_labels(content_dict, outline, stage="generate_content")

        # Content-level on-page SEO invariants, applied deterministically:
        # the user-selected title is restored verbatim if the writer drifted,
        # and the exact focus keyphrase is guaranteed on the title, meta
        # description and introduction. Same call runs at the end of every node
        # that can mutate final_content (repair, humanize, final validate), so
        # there is one implementation of the rule rather than four.
        content_dict = enforce_onpage_seo(
            content_dict,
            selected_title=topic,
            focus_keyphrase=focus_keyword,
            stage="generate_content",
        )

        # H2/H3 subheadings: keyphrase distribution + length. Headings-only
        # rewrite, applied to the assembled body so it covers every content
        # type the same way. No model call when compliant; never raises.
        content_dict = await enforce_subheadings_for_spec(
            content_dict,
            spec,
            stage="generate_content",
        )

        # Strip any hallucinated placeholder image URLs (e.g. example.com) the
        # model may have invented for outline image_suggestions entries — only
        # the generate_image tool call produces a real, usable URL.
        _strip_placeholder_images(content_dict)

        # Resolve the featured image inline. This needs the in-process asyncio
        # Task from `counters` — that can't cross a LangGraph node boundary
        # (checkpointing would need to serialize it), so it must happen here,
        # in the same node/event-loop scope where the tool created it, rather
        # than in a later node.
        image_task = counters.get("image_task")
        if image_task is not None:
            try:
                image_url = await image_task
            except Exception:
                logger.exception(
                    "generate_content: image task raised an error; skipping image injection."
                )
                image_url = None
            if image_url and str(image_url).startswith("http"):
                alt = f"Featured image for {topic}"
                content_dict["body_markdown"] = f"![{alt}]({image_url})\n\n" + (
                    content_dict.get("body_markdown") or ""
                )
                images_list = list(content_dict.get("images") or [])
                images_list.insert(
                    0,
                    {
                        "url": image_url,
                        "alt_text": alt,
                        "context": "AI-generated featured image for the article.",
                        "placement": "introduction",
                    },
                )
                content_dict["images"] = images_list
                logger.info("generate_content: image injected -> %s", image_url)
                content_state = await _charge_delivered_image(content_state, user_id, workspace_id)
            else:
                logger.info(
                    "generate_content: image task returned no valid URL; skipping injection."
                )
        else:
            # Image generation is disabled (see settings.AI_IMAGE_GENERATION_ENABLED)
            # — no task was ever started. If the tool still reserved a placeholder
            # (planning ran, just not the paid model call), embed a manual-upload
            # marker at the same spot the real image would have gone, so the user
            # can fill it in from the editor. Never a real image URL — the marker
            # is stripped by every publish call site if left unresolved.
            placeholder = counters.get("image_placeholder")
            if placeholder:
                alt = placeholder.get("alt_text") or f"Featured image for {topic}"
                marker = build_placeholder_marker(alt, placeholder.get("placeholder_id", ""))
                content_dict["body_markdown"] = f"{marker}\n\n" + (
                    content_dict.get("body_markdown") or ""
                )
                images_list = list(content_dict.get("images") or [])
                images_list.insert(
                    0,
                    {
                        "url": None,
                        "alt_text": alt,
                        "context": placeholder.get("context")
                        or "Suggested featured image — awaiting manual upload.",
                        "placement": placeholder.get("placement", "introduction"),
                        "placeholder_id": placeholder.get("placeholder_id"),
                        "status": "pending_manual_upload",
                    },
                )
                content_dict["images"] = images_list
                logger.info(
                    "generate_content: image generation disabled — embedded manual-upload placeholder id=%s",
                    placeholder.get("placeholder_id"),
                )

        logger.info(f"Content generated successfully: {content_dict.get('title', '')}")

        # Soft, log-only signal here — validate_content (the real deterministic
        # gate, run as a separate LangGraph node right after this one) is what
        # actually blocks/repairs a missing or misattributed brand mention.
        if outline.get("promote_brand"):
            promo_brand_name = (
                (outline.get("brand_voice_promotion") or {}).get("brand_name") or ""
            ).strip()
            if promo_brand_name:
                combined_text = f"{content_dict.get('introduction', '')}\n\n{content_dict.get('body_markdown', '')}"
                if promo_brand_name.lower() not in combined_text.lower():
                    logger.warning(
                        "Approved brand mention '%s' is missing from final generated content. Topic: %s",
                        promo_brand_name,
                        topic,
                    )

        # Soft enforcement: warn when agent produced no sourced facts (evidence block was skipped)
        facts = content_dict.get("facts") or []
        sourced = [f for f in facts if (f.get("source_url") if isinstance(f, dict) else False)]
        if not sourced:
            logger.warning(
                "Content agent returned 0 sourced facts -- agent may have skipped EVIDENCE block. "
                "All third-party claims in this article are unverified. Topic: %s",
                topic,
            )

        # The protected-link baseline every later stage is checked against: the
        # valid, relevant links this article carries now, plus any valid link the
        # writer produced that could not be placed during structured assembly.
        # The latter is recorded rather than silently lost, so validation names
        # it (with its anchor and original sentence) and repair can place it.
        search_results = counters.get("search_results") or []
        link_spec = spec
        link_inventory = merge_link_inventory(
            protected_links(content_dict, link_spec, search_results),
            protected_links(content_dict, link_spec, search_results, candidates=unplaced_links),
        )
        logger.info(
            "generate_content: protected links=%d (unplaced by structured assembly=%d)",
            len(link_inventory),
            len(unplaced_links),
        )

        # Return structured content. searched_results is the real Tavily
        # ground truth for downstream citation-provenance checks
        # (validate_content/repair_content) — without it, a fabricated or
        # altered citation URL is indistinguishable from a real one.
        return {
            "content": {
                **content_state,
                "outline": outline,
                "final_content": {
                    **content_dict,
                    "status": "generated",
                    "rejected_reason": "",
                },
                "generation_meta": {
                    "searched_results": search_results,
                    "link_inventory": link_inventory,
                    # Ground truth for first-person experience claims — see
                    # claim_integrity.build_claim_evidence.
                    "author_profile": counters.get("author_profile") or "",
                    # The persona's tone and the brand's voice, kept by the
                    # humanize pass (article_voice.py).
                    "article_voice": counters.get("article_voice") or {},
                },
                "status": "content_generated",
            }
        }

    except Exception as e:
        # The AI provider unavailable ends the run with its notice (stop_on_outage, G75.1). The notice
        # keeps the marks of the stages charged above, so a retry on this thread doesn't charge them again.
        if provider_outage(e) is not None:
            raise StoppedAfterCharge(content_state) from e
        logger.exception(f"Error generating content: {str(e)}")
        return {
            "content": {
                **content_state,
                "error": "We couldn't generate the requested content right now. Please try again.",
            }
        }
