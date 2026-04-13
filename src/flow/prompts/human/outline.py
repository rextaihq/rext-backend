from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from src.flow.prompts.system.outline import OUTLINE_GENERATION_PROMPT

_DEFAULT_GUIDANCE = """Keep the outline aligned to the requested intent and page type.
Use headings and key points that a writer can directly expand into final content.
"""

_CONTENT_TYPE_GUIDANCE: dict[str, str] = {
    # Informational
    "blog": "Include an intro, body sections, FAQ if useful, and a conclusion. Optimize for informational intent.",
    "explainer": "Define key terms early; introduce concepts progressively; use examples and analogies.",
    "how-to-guide": "Make sections task-oriented; include concrete steps where the schema supports them; include prerequisites/tools.",
    "tutorial": "Keep a learning progression; include steps and code suggestions where relevant.",
    "checklist": "Make sections lead to an actionable checklist; keep items scannable and practical.",
    "pillar-content": "Cover the topic comprehensively; ensure sections map to major subtopics and clusters.",
    "faq": "Group questions into clear categories; keep answers snippet-friendly.",
    "white-paper": "Use a research/report structure (methodology, findings, implications) where the schema supports it.",
    "case-study": "Use a narrative arc (challenge, approach, results); quantify outcomes where possible.",
    "glossary": "Organize terms logically; definitions should be concise and accurate.",
    "resource-list": "Organize by category; include selection criteria and practical context.",
    # Commercial
    "comparison": "Focus on comparison criteria, a clear structure, and decision support; include a comparison table if the schema calls for it.",
    "alternatives": "Explain why alternatives are needed; cover a reasonable set of alternatives and decision criteria.",
    "in-depth-review": "Use feature-by-feature sections; include ratings consistently where required.",
    "best-tools": "Organize tools by use case; explain selection methodology; include pros/cons if the schema supports it.",
    "pros-cons": "Include balanced pros/cons and practical recommendations.",
    "product-roundup": "Cluster products by segment; keep evaluation criteria consistent.",
    "buying-guide": "Educate the buyer; include evaluation framework and common pitfalls.",
    # Navigational
    "brand-page": "Structure like a brand overview page (who/what/why, offerings, trust, next steps).",
    "product-homepage": "Structure like a product homepage (value prop, features, proof, FAQs, CTAs).",
    "feature-overview": "Structure around feature categories and benefits; keep it scannable.",
    "documentation": "Structure around getting started, core concepts, and common tasks.",
    "login-guide": "Structure around access, troubleshooting, and account recovery where relevant.",
    "contact-us": "Structure around contact methods, response times, and routing to the right channel.",
    "about-us": "Structure around mission, story, team, credibility, and trust.",
    "help-center": "Structure around common problem categories and self-serve pathways.",
    # Transactional
    "sales-page": "Structure like a sales page (problem, solution, benefits, proof, pricing/offer, FAQs, CTA).",
    "pricing-page": "Structure around plans, feature comparison, billing details, FAQs, and CTAs.",
    "signup-page": "Structure around signup steps, friction reducers, trust, and FAQs.",
    "demo-page": "Structure around demo value, what you'll see, scheduling, FAQs, and CTA.",
    "coupon-page": "Structure around the offer, how to redeem, terms, FAQs, and CTA.",
    "checkout-page": "Structure around checkout steps, trust, policies, and FAQs.",
    "landing-page": "Structure around the campaign offer, benefits, proof, and CTA.",
    "service-page": "Structure around service overview, process, deliverables, proof, FAQs, and CTA.",
}


def get_outline_guidance(content_type: str) -> str:
    return _CONTENT_TYPE_GUIDANCE.get(content_type, _DEFAULT_GUIDANCE)


def get_outline_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            ("system", OUTLINE_GENERATION_PROMPT),
            (
                "human",
                """
Create a content outline as a single JSON object.

Requested content_type: {content_type}

Schema contract (STRICT):
- Output MUST be valid JSON.
- Output MUST include all required top-level keys: {required_keys}
- Output MUST set `content_type` to exactly: {content_type}
- Output MUST include ONLY keys defined by the schema (no extra keys).
- Follow schema constraints (min/max items, allowed literals, patterns).

Content-type guidance:
{content_type_guidance}

Input topic/query:
{topic}

SERP insights:
- Related topics: {related_topics}
- People Also Ask questions:
{questions}

Competitor coverage summary:
{competitors_context}

Intent distribution:
{intent_distribution}

SEO keyword clusters:
{keyword_clusters}

Revision context:
- Previous rejection reason: {rejected_reason}
- Previous outline (if any):
{previous_outline}

Return ONLY the JSON.
""",
            ),
        ]
    )
