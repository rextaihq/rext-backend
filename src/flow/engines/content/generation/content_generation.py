"""
Content Generation Node (Agent-Based)

Generates SEO-optimized content using the content agent.
Streams tokens and tool calls to the frontend via LangGraph's custom stream
so the user sees the agent work in real time (like GPT).
"""

import json
import logging
import re

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.config import get_stream_writer

from src.flow.engines.agent.content_agent import create_content_agent
from src.flow.model.structure.contents import get_generated_content_model
from src.flow.model.structure.outlines.render import extract_outline_faqs
from src.flow.states.rext import REXT
from src.services.content_cluster_mapping_service import format_cluster_heading_map_for_prompt
from src.utils.credit_manager import STAGE_CREDITS, consume_stage_credits, InsufficientCreditsError, _emit_credit_event

logger = logging.getLogger(__name__)

# Domains/markers that only ever show up when the model invents an image URL
# instead of leaving it blank — the outline's image_suggestions never carry a
# real asset URL, only the single generate_image tool call does.
_PLACEHOLDER_IMAGE_MARKERS = (
    "example.com", "example.org", "example.net",
    "placeholder.com", "via.placeholder", "dummyimage.com",
    "yourdomain.com", "your-domain.com", "domain.com",
    "image-url-here", "url-here", "your-image-url",
)
_MARKDOWN_IMAGE_RE = re.compile(r'!\[[^\]]*\]\((https?://[^)\s]+)\)')


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
                    field, match.group(1),
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
    if sections:
        return sections

    render = outline.get("_render") or {}
    sections = render.get("sections") or []
    return sections if isinstance(sections, list) else []


def _format_outline_for_generation(outline: dict) -> str:
    if not outline:
        return "No approved outline available."

    lines = []
    for label, key in (
        ("Title", "title"),
        ("Brief", "brief"),
        ("Tone", "tone"),
        ("Search intent", "search_intent"),
        ("Content goal", "content_goal"),
    ):
        value = outline.get(key)
        if value:
            lines.append(f"{label}: {_short_text(value, 500)}")

    audience = outline.get("target_audience") or outline.get("audience")
    if audience:
        if isinstance(audience, list):
            audience = ", ".join(str(item) for item in audience[:4])
        lines.append(f"Audience: {_short_text(audience, 400)}")

    keywords = outline.get("keywords_to_include") or outline.get("semantic_keywords") or []
    if keywords:
        lines.append("Keywords: " + ", ".join(str(item) for item in keywords[:12]))

    sections = _outline_sections(outline)
    if sections:
        lines.append("Sections:")
        for index, section in enumerate(sections[:8], start=1):
            heading = section.get("heading") or section.get("title") or section.get("name") or ""
            purpose = (
                section.get("purpose")
                or section.get("description")
                or section.get("summary")
                or ""
            )
            lines.append(f"{index}. {_short_text(heading, 120)}")
            if purpose:
                lines.append(f"   Purpose: {_short_text(purpose, 220)}")
            key_points = section.get("key_points") or section.get("points") or []
            for point in key_points[:4]:
                lines.append(f"   - {_short_text(point, 180)}")

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
        lines.append(f"Approved FAQs (MUST all appear verbatim/near-verbatim in the FAQ section — do not invent replacements):")
        for faq in approved_faqs:
            lines.append(f"- Q: {_short_text(faq['question'], 220)}")
            if faq.get("answer"):
                lines.append(f"  A: {_short_text(faq['answer'], 400)}")

    return "\n".join(lines) if lines else "Approved outline has no compact fields."


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
        outline_str = _format_outline_for_generation(outline)
        cluster_heading_map = outline.get("cluster_heading_map") or content_state.get(
            "cluster_heading_map",
            {},
        )

        logger.info(f"Outline extracted: {outline_str[:20]}...")

        # 2️⃣ Prepare Reference Content (If any)
        page_content = ""
        meta_data = {}

        # 3️⃣ Get primary keyword from outline
        keywords_to_include = outline.get("keywords_to_include") or outline.get("semantic_keywords") or []
        primary_keyword = keywords_to_include[0] if keywords_to_include else topic

        keyword_requirements = ""
        if keywords_to_include:
            keyword_requirements = (
                "\nKEYWORD REQUIREMENTS:\n"
                f"- Approved keywords: {', '.join(keywords_to_include)}\n"
                "- Use each approved keyword phrase at least once in the final body_markdown output.\n"
                "- Prefer exact phrase matches when natural. If a long phrase is awkward, use a close natural variant that preserves the same meaning and word order.\n"
                "- Do not invent unrelated keywords or introduce new keyword themes.\n"
                "- If a keyword is used as a variant, the meaning must remain identical to the approved phrase.\n"
            )

        # 4️⃣ Extract SEO & SERP Insights (CRITICAL)
        seo_result = state.get("seo_result", {})
        keyword_clusters = seo_result.get("keyword_clusters", [])
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

        competitor_insights = (
            f"TOP SERP COMPETITORS:\n{serp_insights}\n\n{seo_signals}"
        )

        # 5️⃣ Extract Tone & Metadata
        tone = outline.get("tone", "Professional")
        target_word_count = outline.get("target_word_count", 2000)
        # Percentage-only tolerance — a flat floor (e.g. 200) is a 40% overshoot
        # allowance on a 500-word target but negligible on a 3000-word one.
        max_word_count = target_word_count + max(50, round(target_word_count * 0.15))
        logger.info(f"Tone: {tone}")

        # Extract key_facts and image_suggestions from the outline
        key_facts = outline.get("key_facts", []) or []
        image_suggestions = outline.get("image_suggestions", []) or []

        key_facts_str = ""
        if key_facts:
            facts_lines = "\n".join(
                (
                    f"  - {f.get('text', str(f))}"
                    + (
                        f" (source: {f['source_url']})"
                        if f.get("source_url")
                        else ""
                    )
                    if isinstance(f, dict)
                    else f"  - {f}"
                )
                for f in key_facts
            )
            key_facts_str = f"\nKEY FACTS TO INCLUDE IN CONTENT:\n{facts_lines}\n"

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

        # 6️⃣ Build internal links block from outline state
        internal_links = outline.get("internal_links") or []
        internal_links_str = ""
        if internal_links:
            link_lines = "\n".join(
                f"  - [{lnk.get('title', lnk.get('url', ''))}]({lnk.get('url', '')})  [status={lnk.get('status','').upper()}  score={lnk.get('score', 0):.2f}]"
                for lnk in internal_links
            )
            internal_links_str = (
                f"\n========================\n"
                f"LINKS TO EMBED — ZERO EXCEPTIONS, ALL MUST APPEAR\n"
                f"========================\n"
                f"There are {len(internal_links)} link(s) below. Every single one MUST appear as an inline hyperlink inside body_markdown. Missing even one is a failure.\n\n"
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
                f"SELF-CHECK before submitting: count the links above. Confirm that exact count of URLs appear in body_markdown. If any are missing — add them before submitting.\n"
            )

        # 7️⃣ Build brand promotion block from outline state (product-led marketing)
        brand_promo_str = ""
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
                good_example = f"  GOOD: '...tools like [{brand_name}]({brand_url}) help teams cut onboarding time in half.'\n"
            else:
                link_instructions = (
                    f"- No verified URL is available for {brand_name} — mention it by name only, as plain text.\n"
                    f"- Do NOT hyperlink {brand_name}. Do NOT invent a URL for it. Do NOT attach a search-result or internal-link URL to this mention — those belong to their own citations only.\n"
                )
                good_example = f"  GOOD: '...tools like {brand_name} help teams cut onboarding time in half.'\n"

            brand_promo_str = (
                f"\n========================\n"
                f"PRODUCT-LED MENTION — {brand_name}\n"
                f"========================\n"
                f"Brand: {brand_name}\n"
                + (f"About: {about}\n" if about else "")
                + (f"Selling position: {selling_pos}\n" if selling_pos else "")
                + f"\nINSTRUCTIONS:\n"
                f"- This is a single, soft product-led mention — not a case study and not a citation. It does NOT need search_tool evidence or a source in the `facts` field.\n"
                f"- Find the ONE section where the article already discusses a problem or need that {brand_name} genuinely addresses (based on the about/selling position above), and mention it there. Do not force it into an unrelated section.\n"
                f"- Weave it into existing prose as a natural aside — do NOT create a standalone sentence, paragraph, or CTA just to hold the mention.\n"
                f"- Make at most ONE mention in the whole article. If nothing in the outline genuinely fits {brand_name}, skip the mention entirely rather than forcing it in — a forced or irrelevant plug is worse than no mention.\n"
                f"- Only state capabilities that appear in the About/selling position above — do not invent features, claims, or stats about {brand_name}.\n"
                f"- NEVER write 'sponsored', 'advertisement', or otherwise signal it as paid content.\n"
                f"- Use the exact brand name: {brand_name}.\n"
                f"{link_instructions}"
                f"{good_example}"
                f"  BAD:  'Check out this product: {brand_name}.' (throwaway sentence)\n"
                f"  BAD:  Bending an unrelated section around {brand_name} just to include it.\n"
            )

        # 8️⃣ Build the human message for the agent
        # (system prompt is already embedded in the agent
        human_message_content = (
            f"Content Type: {content_type}\n"
            f"Topic: {topic}\n\n"
            f"Primary Keyword: {primary_keyword}\n"
            f"Target Word Count: {target_word_count}-{max_word_count} words (stay within this range — do not go meaningfully under or over)\n\n"
            f"COMPETITIVE LANDSCAPE:\n"
            f"{competitor_insights}\n"
            f"- Go deeper than these competitors\n"
            f"- Cover gaps they missed\n"
            f"- Offer a unique angle/perspective\n\n"
            f"Approved Outline:\n{outline_str}\n\n"
            f"Approved Keyword Clusters:\n{keyword_clusters_context}\n\n"
            f"Cluster-to-Heading Map:\n{cluster_heading_map_context}\n\n"
            f"{key_facts_str}"
            f"{image_suggestions_str}"
            f"{internal_links_str}"
            f"{brand_promo_str}"
            f"Reference / Source Content:\n{page_content}\n\n"
            f"Meta_data:\n{meta_data}\n\n"
            f"Tone:\n{tone}\n\n"
            f"Generate complete SEO-optimized content following the outline.\n"
            f"CRITICAL KEYWORD INSTRUCTION: Use only the approved keyword clusters above. "
            f"Follow each cluster's H2/H3/body placement from the cluster-to-heading map, "
            f"naturally integrate primary/supporting keywords in the mapped sections, "
            f"and do not add rejected or mixed-intent keyword themes.\n"
            f"{keyword_requirements}"
            f"Incorporate ALL key facts listed above verbatim in the relevant sections.\n"
            f"Embed ALL links listed above inside body_markdown as natural anchor text — never label them as 'internal' to the reader.\n"
            f"LINK REL ATTRIBUTE RULE: in the 'internal_links' output field, leave 'rel' empty/null (internal links are DoFollow). "
            f"In the 'outbound_links' output field, set 'rel' to 'nofollow' unless the link is a verified partner/citation you have a specific reason to keep followed — "
            f"in that case use 'sponsored' instead of 'nofollow'.\n"
            f"Populate the 'facts' output field with each fact used (text + source_url).\n"
            f"Populate the 'images' output field using the image placement guide above.\n"
            f"Ensure you outperform the competitors listed above."
        )

        # 7️⃣ Create the content agent
        logger.info("Creating content agent...")
        serp_payload = state.get("serp_payload", {})
        user_id = serp_payload.get("user_id")
        workspace_id = serp_payload.get("workspace_id")

        # Deduct all content stages before agent invoke (once, upfront)
        for _stage in ("content_drafting", "featured_image", "humanization", "deep_research"):
            try:
                await consume_stage_credits(user_id, STAGE_CREDITS[_stage], _stage)
            except InsufficientCreditsError as _e:
                _emit_credit_event(_e.available, _e.stage, _e.required, step="credits.exhausted")
                return {"content": {**content_state, "error": "insufficient_credits", "error_code": "insufficient_credits"}}

        generated_model = get_generated_content_model(content_type)
        agent = await create_content_agent(content_type=content_type, user_id=user_id)
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
                if "__humanize__" in (event.get("tags") or []):
                    continue
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
                                    e, list(tc.get("args", {}).keys())
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
                write({
                    "type": "tool_start",
                    "id": event_run_id,
                    "name": tool_name,
                    "query": query,
                })

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
                    write({
                        "type": "tool_end",
                        "id": event_run_id,
                        "name": tool_name,
                        "query": query,
                        "blocked": True,
                    })
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
                    "\n".join(lines)
                    if lines
                    else (str(raw_output)[:360] if raw_output else "")
                )

                write({
                    "type": "tool_end",
                    "id": event_run_id,
                    "name": tool_name,
                    "query": query,
                    "count": count,
                    "output": snippet,
                })

            # Always prefer the final chain-end state because HumanizeMiddleware
            # can replace structured_response after raw model output is parsed.
            # Skip raw humanize model output — tags/title would be hallucinated (pre-merge).
            elif kind == "on_chain_end" and "__humanize__" not in (event.get("tags") or []):
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

        # Guard against content generation / humanization drifting off the
        # user-selected topic — force the title back, same as outline.py does.
        if content_dict.get("title") != topic:
            logger.warning(
                "Generated title '%s' differs from selected topic '%s' — reverting to original topic",
                content_dict.get("title", ""),
                topic,
            )
            content_dict["title"] = topic

        # Strip any hallucinated placeholder image URLs (e.g. example.com) the
        # model may have invented for outline image_suggestions entries — only
        # the generate_image tool call produces a real, usable URL.
        _strip_placeholder_images(content_dict)

        # Focus keyword sent to WordPress must be exactly what the user entered/
        # selected, not the model's own `focus_keyphrase` output. Prefer the
        # keyword-selection step's choice, falling back to the raw payload
        # keyword (covers library/bulk runs that skip keyword selection).
        entered_keyword = (
            (seo_result.get("keyword_recommendations") or {}).get("selected_keyword")
            or serp_payload.get("query")
        )
        if entered_keyword and content_dict.get("focus_keyphrase") != entered_keyword:
            logger.info(
                "Overriding generated focus_keyphrase '%s' with user keyword '%s'",
                content_dict.get("focus_keyphrase", ""),
                entered_keyword,
            )
            content_dict["focus_keyphrase"] = entered_keyword

        logger.info(f"Content generated successfully: {content_dict.get('title', '')}")

        # Soft enforcement: warn when agent produced no sourced facts (evidence block was skipped)
        facts = content_dict.get("facts") or []
        sourced = [f for f in facts if (f.get("source_url") if isinstance(f, dict) else False)]
        if not sourced:
            logger.warning(
                "Content agent returned 0 sourced facts -- agent may have skipped EVIDENCE block. "
                "All third-party claims in this article are unverified. Topic: %s", topic
            )

        # Return structured content
        return {
            "content": {
                **content_state,
                "outline": outline,
                "final_content": {
                    **content_dict,
                    "status": "generated",
                    "rejected_reason": "",
                },
                "status": "content_generated",
            }
        }

    except Exception as e:
        logger.exception(f"Error generating content: {str(e)}")
        return {
            "content": {
                **content_state,
                "error": f"Generation failed: {str(e)}",
            }
        }

