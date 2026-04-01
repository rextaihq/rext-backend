from __future__ import annotations


_BASE_REQUIREMENTS = """\
GLOBAL QUALITY RULES (STRICT)
1. Output MUST be valid JSON and MUST match the requested schema exactly.
2. Every heading must be specific and keyword-rich — avoid generic headings like "Introduction" or "Conclusion".
3. Ensure a logical hierarchy; no redundancy; no repeated sections.
4. Include competitor-gap coverage: add 1-2 sections competitors likely missed.
5. Be publish-ready: practical, actionable, and intent-satisfying.
"""


_TYPE_REQUIREMENTS: dict[str, str] = {
    # Article / blog-like
    "blog": """\
BLOG / ARTICLE RULES
- Write an engaging `intro` (hook + context + promise).
- Use 4-8 H2 `sections` with a clear purpose and 2-5 key_points each.
- At least one section must set `snippet_opportunity=true` (definition/list/steps).
- End with a concrete `conclusion` recap + CTA.
""",

    # How-to
    "how-to-guide": """\
HOW-TO GUIDE RULES
- Provide `prerequisites` and `tools_or_materials` when relevant.
- Create 5-12 sequential `steps` with step_number starting at 1.
- Every step title must be an action verb (no "Step 1: ...").
- Include `common_mistakes` and `troubleshooting` if the topic has failure modes.
- Wrap up with 2-5 actionable `wrap_up` bullets.
""",

    # Comparison
    "comparison": """\
COMPARISON RULES
- Define 2-6 `compared_entities` with strengths + limitations.
- Provide 3-8 `evaluation_criteria` (each with why_it_matters + how_to_judge).
- Add `decision_guide` bullets that help readers choose based on priorities.
- Give 2-5 scenario-based `recommendations` and a clear `verdict`.
""",

    # Review
    "in-depth-review": """\
REVIEW RULES
- Fill `product_or_service`, `who_its_for`, and a realistic `rating` (0-5).
- Provide 3-10 `standout_features` (each tied to user value).
- Pros/cons must be specific (no vague claims).
- End with a decisive `verdict` and include `alternatives` if appropriate.
""",

    # Checklist
    "checklist": """\
CHECKLIST RULES
- Build 2-7 `categories`, each with 3-12 actionable items.
- Every item must include `why` and `how_to_verify`.
- Use priorities (`must` / `should` / `nice-to-have`) for decision clarity.
""",
}


_ALIASES: dict[str, str] = {
    # Informational variants that still use an article-like outline
    "explainer": "blog",
    "pillar-content": "blog",
    "faq": "blog",
    "white-paper": "blog",
    "case-study": "blog",
    "glossary": "blog",
    "resource-list": "blog",
    # How-to variants
    "tutorial": "how-to-guide",
    "documentation": "how-to-guide",
    "login-guide": "how-to-guide",
    # Comparison variants
    "best-tools": "comparison",
    "alternatives": "comparison",
    "pros-cons": "comparison",
    "product-roundup": "comparison",
    "buying-guide": "comparison",
}


def get_outline_requirements(content_type: str, schema_name: str) -> str:
    key = _ALIASES.get(content_type, content_type)
    type_block = _TYPE_REQUIREMENTS.get(key, _TYPE_REQUIREMENTS["blog"])
    return (
        f"SCHEMA: `{schema_name}`\n"
        f"{_BASE_REQUIREMENTS}\n"
        f"{type_block}"
    )

