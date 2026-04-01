"""Human-turn outline prompts — specialized requirement blocks for each intent/content type.

Includes individual requirement blocks for all 34 content types, ensuring the LLM
populates the specialized fields in the corresponding Pydantic schema.
"""

from langchain_core.prompts import ChatPromptTemplate
from src.flow.prompts.system.outline import OUTLINE_PROMPTS_BY_CONTENT_TYPE
from src.flow.model.structure.outline_schemas import get_outline_schema
from src.flow.prompts.human.outline_types import get_outline_requirements
from src.flow.utils.content_type_utils import normalize_content_type_slug

# ---------------------------------------------------------------------------
# Shared human-turn base template
# ---------------------------------------------------------------------------

_HUMAN_BASE = """\
Generate a HIGH-QUALITY, SEO-OPTIMIZED CONTENT OUTLINE for a **{content_type}**.

### INPUT DATA

Content Type: {content_type}
Schema: {{schema_name}}
Primary Topic / Query:
{topic}

SERP Insights:
- Related Topics: {related_topics}
- People Also Ask Questions:
{questions}

- Competitor Coverage Summary:
{competitors_context}

- Intent Distribution:
{intent_distribution}

Iteration Feedback:
- Previous Rejection Reason: {rejected_reason}
- Previous Outline (if any):
{previous_outline}

### STRICT REQUIREMENTS

{{requirements}}

Return ONLY the JSON. No explanations.
"""

# ---------------------------------------------------------------------------
# Requirement blocks per search-intent group or specific content sub-type
# ---------------------------------------------------------------------------

_INFORMATIONAL_REQUIREMENTS = """\
1. Output MUST be valid JSON matching the `InformationalOutline` Pydantic schema.
2. Structure: 4–8 sections. Use H2 for main topics, H3 sparingly.
3. Every main topic must address a specific reader question or subtopic.
4. Populate 'prerequisites' (what the reader needs beforehand) and 'key_takeaways' (3-5 bullets summarizing the value).
5. Set 'table_of_contents' to true if this is a comprehensive pillar or white-paper.
6. Target word count: 1 000–3 000 (adjust for depth).
7. Ensure search_intent is set to 'informational' for each section.
"""

_COMMERCIAL_REQUIREMENTS = """\
1. Output MUST be valid JSON matching the `CommercialOutline` Pydantic schema.
2. 4–8 sections focusing on evaluation, comparison, and decision-making.
3. Populate 'products_covered' with a list of the 3-5 specific tools/options discussed.
4. Populate 'evaluation_criteria' with 3-6 criteria used (e.g., Performance, UX, Price).
5. Provide a summary 'verdict' declaring the winner or best use-case recommendation.
6. Set 'comparison_table_included' to true.
7. Ensure search_intent is 'commercial' for assessment sections.
"""

_NAVIGATIONAL_REQUIREMENTS = """\
1. Output MUST be valid JSON matching the `NavigationalOutline` Pydantic schema.
2. 3–8 sections focusing on brand identity, feature clarity, or documentation steps.
3. Define the 'primary_cta' (the single most important user action).
4. List 'trust_signals' to be featured (e.g., 'Loved by 10k+ devs', 'ISO 27001 Certified').
5. Use 300–2 000 words (keep documentation detailed, homepage concise).
6. Title must clearly reflect the brand or product name.
"""

_TRANSACTIONAL_REQUIREMENTS = """\
1. Output MUST be valid JSON matching the `TransactionalOutline` Pydantic schema.
2. 3–8 sections designed to drive conversions and address buyer hesitation.
3. Define the 'primary_cta' and identify 3-5 'objections_addressed' (e.g., 'price', 'implementation time').
4. List 'trust_signals' and define a strong 'risk_reversal' (e.g., '30-day money-back guarantee').
5. If applicable, specify an 'urgency_element'.
6. Headings must be punchy and benefit-driven.
"""

# Map content type slugs to their specific requirement instruction blocks
TYPE_TO_REQUIREMENTS = {
    # Informational
    "blog": _INFORMATIONAL_REQUIREMENTS,
    "how-to-guide": _INFORMATIONAL_REQUIREMENTS + "8. Each step in 'sections' must use a clear action verb.",
    "explainer": _INFORMATIONAL_REQUIREMENTS + "8. First H2 must be a direct FEATURED SNIPPET definition.",
    "pillar-content": _INFORMATIONAL_REQUIREMENTS + "8. Must cover 5+ semantic sub-entities.",
    "checklist": _INFORMATIONAL_REQUIREMENTS,
    "tutorial": _INFORMATIONAL_REQUIREMENTS,
    "faq": _INFORMATIONAL_REQUIREMENTS,
    "white-paper": _INFORMATIONAL_REQUIREMENTS,
    "case-study": _INFORMATIONAL_REQUIREMENTS,
    "glossary": _INFORMATIONAL_REQUIREMENTS,
    "resource-list": _INFORMATIONAL_REQUIREMENTS,
    
    # Commercial
    "comparison": _COMMERCIAL_REQUIREMENTS,
    "best-tools": _COMMERCIAL_REQUIREMENTS,
    "alternatives": _COMMERCIAL_REQUIREMENTS,
    "in-depth-review": _COMMERCIAL_REQUIREMENTS,
    "pros-cons": _COMMERCIAL_REQUIREMENTS,
    "product-roundup": _COMMERCIAL_REQUIREMENTS,
    "buying-guide": _COMMERCIAL_REQUIREMENTS,
    
    # Navigational
    "brand-page": _NAVIGATIONAL_REQUIREMENTS,
    "product-homepage": _NAVIGATIONAL_REQUIREMENTS,
    "feature-overview": _NAVIGATIONAL_REQUIREMENTS,
    "documentation": _NAVIGATIONAL_REQUIREMENTS + "7. Sections must follow a logical technical hierarchy.",
    "login-guide": _NAVIGATIONAL_REQUIREMENTS,
    "contact-us": _NAVIGATIONAL_REQUIREMENTS,
    "about-us": _NAVIGATIONAL_REQUIREMENTS,
    "help-center": _NAVIGATIONAL_REQUIREMENTS,
    
    # Transactional
    "sales-page": _TRANSACTIONAL_REQUIREMENTS,
    "pricing-page": _TRANSACTIONAL_REQUIREMENTS,
    "signup-page": _TRANSACTIONAL_REQUIREMENTS,
    "demo-page": _TRANSACTIONAL_REQUIREMENTS,
    "coupon-page": _TRANSACTIONAL_REQUIREMENTS,
    "checkout-page": _TRANSACTIONAL_REQUIREMENTS,
    "landing-page": _TRANSACTIONAL_REQUIREMENTS,
    "service-page": _TRANSACTIONAL_REQUIREMENTS,
}


def normalize_content_type(raw: str | None) -> str:
    """Normalize raw content_type to a canonical kebab-case slug."""
    return normalize_content_type_slug(raw)


def get_outline_prompt(content_type: str = "blog") -> ChatPromptTemplate:
    """Return a system/human prompt pair for the given content_type."""

    content_type = normalize_content_type(content_type) or "blog"
    schema_name = get_outline_schema(content_type).__name__

    system_prompt = OUTLINE_PROMPTS_BY_CONTENT_TYPE.get(
        content_type, OUTLINE_PROMPTS_BY_CONTENT_TYPE["blog"]
    )

    requirements = get_outline_requirements(content_type=content_type, schema_name=schema_name)

    # Compose the human prompt by injecting specialized requirements and schema name
    human_msg = (
        _HUMAN_BASE.replace("{{requirements}}", requirements)
        .replace("{{schema_name}}", schema_name)
    )
    
    return ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", human_msg),
        ]
    )
