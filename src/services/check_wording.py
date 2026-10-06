"""What a failed article check says to the person reading the article.

A validation check's `detail` is written for the repair step: it quotes the offending
sentences and tells the model how to fix them ("Fix each one in place — remove or soften
it, never replace it with a guessed value…"). That text stays in the run's state, where
the repair step reads it. What the article's checklist shows, in the API and so in the
dashboard, is the line here for the check's name: short, plain, written for a person.
"""

from __future__ import annotations

import json
import re
from typing import Any

# One line per check (validation.py's `check_<name>`), in the order the checks run.
USER_WORDING: dict[str, str] = {
    "word_count_band": "The article's length is outside the range the outline set.",
    "keyword_presence": "The article never uses the focus keyphrase.",
    "keyword_density": "The focus keyphrase is used too often or too rarely for the article's length.",
    "selected_title_preserved": "The title differs from the one you picked.",
    "focus_keyphrase_in_title": "The title doesn't contain the focus keyphrase.",
    "meta_description_present": "The article has no meta description.",
    "meta_description_length": "The meta description is longer than search results show.",
    "focus_keyphrase_in_meta_description": "The meta description doesn't contain the focus keyphrase.",
    "focus_keyphrase_in_introduction": "The introduction doesn't use the focus keyphrase.",
    "subheading_keyphrase": "Too few or too many subheadings use the focus keyphrase.",
    "subheading_length": "Some subheadings are too long or too short.",
    "title_subject_alignment": "The article drifts from the subject its title promises.",
    "required_sections": "A section the outline planned is missing.",
    "hero_presence": "The opening the outline planned is missing.",
    "brand_presence": "Your brand isn't mentioned, though the outline asked for it.",
    "brand_url_accuracy": "The link on your brand doesn't go to your site's address.",
    "brand_placement": "Your brand mention isn't where the outline placed it.",
    "brand_placement_policy": "Your brand mention isn't where this kind of article puts it.",
    "brand_prominence": "Your brand gets less space than you chose for it.",
    "brand_integration_depth": "Your brand is named, but the article doesn't say what it offers.",
    "brand_factual_grounding": "Something said about your brand isn't in your brand details.",
    "brand_context_heuristic": "Check the tone of the sentence that mentions your brand.",
    "internal_links_integration": "Some of the internal links you approved aren't in the article.",
    "facts_and_external_links_integration": "Some sources can't be traced to this run's research.",
    "links_preserved": "A source link was lost while the article was polished.",
    "cta_presence": "The call to action from the outline isn't in the article.",
    "placeholder_product_names": 'The article names placeholder products (like "Tool A") instead of real ones.',
}

_COUNT = re.compile(r"^\s*(\d+)")


def _claims(detail: str) -> str:
    match = _COUNT.match(detail or "")
    count = int(match.group(1)) if match else 0
    if count == 1:
        return "1 claim isn't backed by a source: soften it or add a source."
    if count > 1:
        return f"{count} claims aren't backed by a source: soften them or add sources."
    return "Some claims aren't backed by a source: soften them or add sources."


def user_detail(name: Any, detail: Any = "") -> str:
    """The line a person reads for a failed check, whatever the check's own detail says."""
    name = str(name or "")
    if name == "unsupported_claims":
        return _claims(str(detail or ""))
    if name in USER_WORDING:
        return USER_WORDING[name]
    label = name.replace("_", " ").strip().capitalize() or "A check"
    return f"{label}: this check didn't pass."


def user_rows(rows: Any) -> Any:
    """Check rows ({name, severity, detail}) with each detail in words for the reader."""
    if not isinstance(rows, list):
        return rows
    return [
        {**row, "detail": user_detail(row.get("name"), row.get("detail"))}
        if isinstance(row, dict)
        else row
        for row in rows
    ]


def user_validation(validation: Any) -> Any:
    """A saved validation summary with its issues and warnings in words for the reader."""
    if not isinstance(validation, dict):
        return validation
    return {
        **validation,
        "issues": user_rows(validation.get("issues")),
        "warnings": user_rows(validation.get("warnings")),
    }


def public_seo_details(seo_details: Any, checks_key: str = "content_checks") -> Any:
    """`seo_details` as the API returns it: the saved validation in words for the reader.

    Articles saved before this kept the repair step's wording in
    `seo_details["content_checks"]["validation"]`; this rewrites it on the way out, so
    no saved article returns it. Anything that isn't that JSON is returned as it is.
    """
    if not isinstance(seo_details, str) or checks_key not in seo_details:
        return seo_details
    try:
        parsed = json.loads(seo_details)
    except (TypeError, ValueError):
        return seo_details
    checks = parsed.get(checks_key) if isinstance(parsed, dict) else None
    if not isinstance(checks, dict) or not isinstance(checks.get("validation"), dict):
        return seo_details
    parsed[checks_key] = {**checks, "validation": user_validation(checks["validation"])}
    return json.dumps(parsed, default=str)
