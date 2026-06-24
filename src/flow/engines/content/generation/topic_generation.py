import logging
import re
from typing import Dict, Any, List
from src.flow.states.rext import REXT
from src.flow.model.structure.topics import SEOTopics
from src.flow.model.llm_manager import topic_generation_model
from langgraph.types import interrupt
from langchain_core.messages import SystemMessage, HumanMessage
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_REGENERATE_ACTIONS = {"regenerate_topics", "regenerate", "regen"}

# Intent → structural title formulas aligned with Google's ranking patterns
_INTENT_FORMULAS = {
    "informational": (
        "  - '[Keyphrase]: Complete {year} Guide for Beginners'\n"
        "  - 'How to [Keyphrase] — Step-by-Step ({year})'\n"
        "  - 'What Is [Keyphrase]? {year} Definitive Overview'\n"
        "  - '[Keyphrase] Explained: What Experts Know in {year}'\n"
        "  - '[Keyphrase] for [Audience]: What Actually Works in {year}'"
    ),
    "transactional": (
        "  - 'Best [Keyphrase] in {year}: Top [X] Picks'\n"
        "  - '[Keyphrase] Review {year}: Is It Worth It?'\n"
        "  - '[Keyphrase] vs [Alternative]: Which to Buy in {year}'\n"
        "  - '{year} [Keyphrase] Buyer's Guide for [Audience]'\n"
        "  - '[Keyphrase] Deals {year}: What You'll Actually Pay'"
    ),
    "commercial": (
        "  - 'Best [Keyphrase] Tools in {year}: Ranked & Compared'\n"
        "  - '[Keyphrase] Pricing {year}: Real Costs Broken Down'\n"
        "  - '[Keyphrase] vs [Competitor]: {year} Honest Comparison'\n"
        "  - 'Top [X] [Keyphrase] Platforms for [Audience] ({year})'\n"
        "  - '[Keyphrase] Alternatives in {year}: Better Options'"
    ),
    "navigational": (
        "  - '[Keyphrase] Guide {year}: Features, Tips & Updates'\n"
        "  - 'How to Use [Keyphrase] for [Goal] in {year}'\n"
        "  - '[Keyphrase] Tutorial: Full Getting-Started Guide {year}'\n"
        "  - '[Keyphrase] vs Competitors: {year} Full Comparison'\n"
        "  - '[Keyphrase] in {year}: Everything That Changed'"
    ),
}

_CONTENT_TYPE_NOTES = {
    "article": "Write evergreen educational titles — authoritative, informative, long-tail.",
    "how-to": "Every title MUST start with 'How to' — action-first, clear deliverable.",
    "review": "Include an evaluation signal (score, verdict, year) — make 'review' implicit or explicit.",
    "comparison": "Include 'vs' or 'compared' — the comparison must be explicit in the title.",
    "list": "Include a specific number — '7 Ways', '10 Tools', '5 Proven Strategies'.",
    "guide": "Signal depth and authority — 'Complete Guide', 'Definitive Guide', 'Full Guide'.",
    "case-study": "Lead with the outcome or metric — results-first framing builds click intent.",
    "news": "Signal recency — include the year and a timely, factual news angle.",
}


def _is_regenerate_request(response: Any) -> bool:
    if isinstance(response, dict):
        action = (response.get("action") or "").strip().lower()
        if action in _REGENERATE_ACTIONS:
            return True
        if response.get("regenerate_topics"):
            return True
    if isinstance(response, str):
        val = response.strip().lower()
        for action in _REGENERATE_ACTIONS:
            if val.startswith(action):
                return True
    return False


def _extract_serp_signals(serp_normalized: dict) -> tuple[list[str], list[str], list[str]]:
    """Pull competitor titles, PAA questions, and related topics from SERP state."""
    if not serp_normalized:
        return [], [], []

    # Intent-matched titles are higher quality — prefer them over raw organic results
    intent_signals = serp_normalized.get("intent_matched_signals") or {}
    if intent_signals.get("titles"):
        competitor_titles = [t for t in intent_signals["titles"] if t][:8]
    else:
        competitor_titles = [
            r["title"]
            for r in (serp_normalized.get("normalize_results") or [])[:8]
            if r.get("title")
        ]

    questions = [q for q in (serp_normalized.get("questions") or []) if q][:6]
    related_topics = [t for t in (serp_normalized.get("related_topics") or []) if t][:6]

    return competitor_titles, questions, related_topics


def _build_system_prompt(current_year: int, intent: str, content_type: str) -> str:
    formulas = _INTENT_FORMULAS.get(intent, _INTENT_FORMULAS["informational"])
    formulas = formulas.replace("{year}", str(current_year))

    content_type_note = _CONTENT_TYPE_NOTES.get(
        content_type, f"Match the '{content_type}' format explicitly in the title."
    )

    return (
        f"You are a senior SEO strategist. Generate 5 optimised article titles for {current_year}.\n\n"
        "========================\n"
        "SEO TITLE RULES — NON-NEGOTIABLE\n"
        "Derived from Google ranking standards.\n"
        "========================\n"
        "CHARACTER LENGTH:\n"
        "  - Optimal (meta_title SERP display): 50–60 characters — TARGET THIS RANGE\n"
        "  - Acceptable minimum: 20 characters\n"
        "  - Hard maximum: 60 characters — Google truncates anything beyond this in SERPs\n"
        "  - Count every character including spaces before returning\n\n"
        "WORD COUNT: ≤10 words per title — hard cap\n\n"
        "KEYPHRASE PLACEMENT:\n"
        "  - Focus keyphrase MUST appear at the VERY BEGINNING of every title\n"
        "  - Do NOT start with stop words: 'The', 'A', 'An', 'This', 'Your' — keyphrase first\n"
        "  - Keyphrase appears EXACTLY ONCE per title — never repeat it (keyphrase density rule)\n\n"
        "CLICKBAIT: Zero tolerance — every title must truthfully represent the content\n\n"
        f"FRESHNESS: Consider adding '{current_year}' where it genuinely adds value (stats, comparisons, buyer guides) — omit if the user prefers evergreen or year-free titles\n\n"
        "SECONDARY KEYWORDS:\n"
        "  - Each of the 5 titles must cover a DIFFERENT secondary keyword angle\n"
        "  - Draw each angle from the related searches provided in the human message\n"
        "  - This gives semantic coverage across multiple search variations\n\n"
        "SLUG COMPATIBILITY: Titles should be naturally convertible to clean slugs\n"
        "  - No special characters beyond hyphens and colons\n"
        "  - Avoid stop-word-only suffixes like '...and More', '...and Beyond'\n\n"
        "========================\n"
        f"CONTENT TYPE: {content_type.upper()}. topic must be match with intent and content type.\n"
        "========================\n"
        f"{content_type_note}\n\n"
        "========================\n"
        f"SEARCH INTENT: {intent.upper()}\n"
        "========================\n"
        f"Use these structural formulas aligned to '{intent}' intent as starting points:\n"
        f"{formulas}\n\n"
        "========================\n"
        "E-E-A-T TITLE SIGNALS (Google's quality ranking factor)\n"
        "========================\n"
        "- EXPERIENCE: embed concrete outcomes — 'Cut Costs by 30%', 'From 0 to 50K Users'\n"
        "- EXPERTISE: use specific, credible language — 'Data-Backed', 'Expert-Reviewed', 'Proven'\n"
        "- AUTHORITY: avoid vague superlatives — replace 'Best Ever' with 'Best for [audience]'\n"
        "- TRUST: no invented statistics in titles — keep every claim verifiable\n\n"
        "========================\n"
        "FEATURED SNIPPET TARGETING\n"
        "========================\n"
        "for Google's People Also Ask boxes and featured snippet positions.\n\n"
        "========================\n"
        "PRE-SUBMIT CHECKLIST — verify every title before returning\n"
        "========================\n"
        "  1. Starts with the focus keyphrase (no stop word before it)\n"
        "  2. Is 50–60 characters ideally, never exceeds 60\n"
        "  3. Contains ≤10 words\n"
        "  4. Keyphrase appears exactly once\n"
        "  5. Matches the search intent\n"
        "  6. Uses a different structural pattern and secondary keyword angle from the other 4"
    )


def _build_human_message(
    query: str,
    current_year: int,
    intent: str,
    content_type: str,
    competitor_titles: list[str],
    questions: list[str],
    related_topics: list[str],
    feedback: str = "",
) -> str:
    parts = []

    if feedback:
        parts.append(
            f"USER FEEDBACK — READ THIS FIRST, HIGHEST PRIORITY:\n"
            f"{feedback}\n"
            f"Apply the above feedback BEFORE anything else. It overrides any conflicting SEO guideline below.\n"
            f"{'=' * 48}"
        )

    parts += [
        f"Generate 5 SEO article titles for: {query}",
        f"Year: {current_year} | Search intent: {intent} | Content type: {content_type}",
    ]

    if competitor_titles:
        parts.append(
            "\nCOMPETITOR TITLES ALREADY RANKING — differentiate from these, do NOT copy:\n"
            + "\n".join(f"  - {t}" for t in competitor_titles)
        )

    if questions:
        parts.append(
            "\nPEOPLE ALSO ASK — use as inspiration for question-based titles (featured snippet targeting):\n"
            + "\n".join(f"  ? {q}" for q in questions)
        )

    if related_topics:
        parts.append(
            "\nRELATED SEARCHES — consider for secondary keyword coverage in title variants:\n"
            + "\n".join(f"  ~ {t}" for t in related_topics)
        )

    parts.append(
        f"\nGenerate 5 unique titles now.\n"
        f"Topic/keyphrase: '{query}'\n"
        f"Each title must:\n"
        f"  - Start with the core keyphrase extracted from '{query}' (or its closest natural variant) — NOT a stop word\n"
        f"  - Be 50–60 characters ideally, never more than 60\n"
        f"  - Contain ≤10 words\n"
        f"  - Keyphrase appears exactly once per title\n"
        f"  - Cover a different secondary keyword angle — use the related searches above for each angle\n"
        f"  - Use a structurally different pattern from the other 4 titles"
    )

    return "\n".join(parts)


async def topic_generation(state: REXT) -> Dict[str, Any]:
    logger.info("Starting topic generation")

    from src.utils.credit_manager import STAGE_CREDITS, consume_stage_credits
    _user_id = (state.get("serp_payload") or {}).get("user_id")

    # 1 credit — SERP & competitor analysis (SERP+SEO already completed before this node)
    if state.get("serp_result"):
        await consume_stage_credits(_user_id, STAGE_CREDITS["serp_seo"], "serp_seo")

    # ── Resolve query ─────────────────────────────────────────────
    normalized_result = state.get("serp_normalized", {})

    if normalized_result and normalized_result.get("error"):
        logger.warning(
            "Skipping topic generation due to upstream error: %s",
            normalized_result["error"],
        )
        return {"content": {"topics": [], "selected_topic": ""}}

    query = normalized_result.get("query")
    if not query:
        serp_payload = state.get("serp_payload", {})
        query = serp_payload.get("query", "")
    if not query:
        logger.warning("No query found")
        return {"content": {"topics": [], "selected_topic": ""}}

    # ── Resolve intent, content type, and SERP signals ────────────
    serp_backlinks = state.get("seo_result", {}).get("serp_backlinks", {})
    selected_intent = serp_backlinks.get("main_intent", "informational")
    selected_content_type = state.get("content", {}).get("content_type", "article")
    current_year = datetime.now(timezone.utc).year

    competitor_titles, questions, related_topics = _extract_serp_signals(normalized_result)
    logger.info(
        "SERP signals: %d competitor titles, %d PAA questions, %d related topics",
        len(competitor_titles), len(questions), len(related_topics),
    )

    # ── Build messages ────────────────────────────────────────────
    model = topic_generation_model().with_structured_output(SEOTopics)

    system_content = _build_system_prompt(current_year, selected_intent, selected_content_type)
    human_content = _build_human_message(
        query=query,
        current_year=current_year,
        intent=selected_intent,
        content_type=selected_content_type,
        competitor_titles=competitor_titles,
        questions=questions,
        related_topics=related_topics,
    )

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=human_content),
    ]

    # ── Initial generation ────────────────────────────────────────
    results: SEOTopics = await model.ainvoke(messages)
    topics: List[str] = [t.title for t in results.topics]

    logger.info("Generated %d topics", len(topics))

    # ── Interrupt loop until valid selection ──────────────────────
    while True:
        user_response = interrupt(
            {
                "type": "topic",
                "instruction": "Select a topic",
                "topics": topics,
                "allow_regenerate": True,
            }
        )

        # ── Explicit regenerate ───────────────────────────────────
        if _is_regenerate_request(user_response):
            logger.info("User requested regeneration")

            feedback = ""
            if isinstance(user_response, dict):
                feedback = user_response.get("feedback", "").strip()
            elif isinstance(user_response, str):
                val = user_response.strip()
                for action in _REGENERATE_ACTIONS:
                    if val.lower().startswith(action):
                        feedback = val[len(action):].lstrip(".: ").strip()
                        break

            if feedback.lower() in {"none", "skip", "no", "n/a", ""}:
                feedback = ""

            # Rebuild human message with feedback so SERP context is always present
            regen_human = _build_human_message(
                query=query,
                current_year=current_year,
                intent=selected_intent,
                content_type=selected_content_type,
                competitor_titles=competitor_titles,
                questions=questions,
                related_topics=related_topics,
                feedback=feedback,
            )
            # Rebuild system prompt: feedback block goes first so it overrides SEO rules that conflict
            if feedback:
                regen_system = (
                    f"{'=' * 56}\n"
                    f"USER FEEDBACK — ABSOLUTE PRIORITY\n"
                    f"{'=' * 56}\n"
                    f"{feedback}\n\n"
                    f"This feedback was given by the user for this regeneration.\n"
                    f"It MUST be followed exactly. Any SEO guideline below that conflicts "
                    f"with this feedback should be ignored in favour of the feedback.\n"
                    f"{'=' * 56}\n\n"
                    + system_content
                )
            else:
                regen_system = system_content
            messages = [
                SystemMessage(content=regen_system),
                HumanMessage(content=regen_human),
            ]

            if feedback:
                logger.info("Regenerating with user feedback: %s", feedback)

            results = await model.ainvoke(messages)
            topics = [t.title for t in results.topics]
            continue

        # ── Extract topic ─────────────────────────────────────────
        if isinstance(user_response, dict):
            selected_topic = (
                user_response.get("Selected Topic")
                or user_response.get("selected_topic")
                or user_response.get("topic")
                or ""
            )
        else:
            selected_topic = str(user_response)

        selected_topic = selected_topic.strip()

        # ── Auto regenerate if empty ──────────────────────────────
        if not selected_topic:
            logger.warning("Empty input → regenerating topics")
            results = await model.ainvoke(messages)
            topics = [t.title for t in results.topics]
            continue

        logger.info("User selected topic: %s", selected_topic)
        break

    # 1 credit — keyword & topic research
    await consume_stage_credits(_user_id, STAGE_CREDITS["keyword_research"], "keyword_research")

    return {
        "content": {
            "topics": topics,
            "selected_topic": selected_topic,
        }
    }
