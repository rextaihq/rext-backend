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

# One line per check, by the name its result carries (usually validation.py's `check_<name>`).
USER_WORDING: dict[str, str] = {
    "word_count_band": "The article's length is outside the range the outline set.",
    "keyword_presence": "The article never uses the focus keyphrase.",
    "keyword_density": "The focus keyphrase is used too often or too rarely for the article's length.",
    "selected_title_preserved": "The title or the search title differs from the one you picked.",
    "focus_keyphrase_in_title": "The title doesn't contain the focus keyphrase.",
    "meta_description_present": "The article has no meta description.",
    "focus_keyphrase_in_meta_description": "The meta description doesn't contain the focus keyphrase.",
    "focus_keyphrase_in_introduction": "The introduction doesn't use the focus keyphrase.",
    "subheading_keyphrase": "Too few or too many subheadings use the focus keyphrase.",
    "subheading_length": "Some subheadings are too long or too short.",
    "title_subject_alignment": "The article drifts from the subject its title promises.",
    "required_sections": "Sections don't match the outline.",
    "hero_presence": "The opening the outline planned is missing.",
    "brand_presence": "Your brand isn't mentioned, though the outline asked for it.",
    "brand_url_accuracy": "The link on your brand needs a look.",
    "brand_placement": "Your brand mention sits on a line of its own instead of in a sentence.",
    "brand_placement_policy": "Your brand mention isn't where this kind of article puts it.",
    "brand_prominence": "Your brand's mentions don't match the prominence you chose.",
    "brand_integration_depth": "Your brand mention needs a specific benefit next to it.",
    "brand_factual_grounding": "Something said about your brand isn't in your brand details.",
    "brand_context_heuristic": "Check the tone of the sentence that mentions your brand.",
    "internal_links_integration": "Internal links aren't woven in as the outline planned.",
    "facts_and_external_links": "The article's sources and facts need a look.",
    "links_preserved": "A link was lost while the article was polished.",
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


def _meta_length(detail: str) -> str:
    # Too short is a warning ("aim for 120-156"), too long is blocking ("the maximum is 156").
    if "aim for" in detail or "too short" in detail:
        return "The meta description is too short: search results have room for more."
    return "The meta description is too long: search results cut it off."


# A check that reports one of several causes gets the line for the cause its detail names.
# Each marker is the check's fixed diagnostic wording in validation.py, never a part that
# carries a section name, a link or a title (a section called "Missing features" must not
# read as a missing section); a test holds the markers to the source. When the detail names
# none of them, the neutral line in USER_WORDING says less rather than guess.
_ONE_CAUSE: dict[str, list[tuple[str, str]]] = {
    "brand_prominence": [
        (
            "The user chose a SUBTLE mention",
            "Your brand is mentioned more often than the one subtle mention you chose.",
        ),
        (
            "The user chose a PROMINENT mention",
            "Your brand isn't named in the closing, though you chose a prominent mention.",
        ),
    ],
    "selected_title_preserved": [
        ("`meta_title` was changed", "The search title differs from the title you picked."),
        ("`title` was changed", "The title differs from the one you picked."),
    ],
    "brand_url_accuracy": [
        ("Brand mention has no hyperlink", "Your brand isn't linked to your site."),
        (
            "Brand mention is hyperlinked to",
            "The link on your brand goes to another address than your site's.",
        ),
    ],
}

# A check whose detail can name several causes at once: one line, a clause per cause.
_SEVERAL_CAUSES: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "required_sections": (
        "Sections",
        [
            ("section(s) the approved", "some the outline planned are missing"),
            ("REQUIRED section(s)", "some the outline planned are missing"),
            (
                "planned section(s) are out of the approved order",
                "some are out of the outline's order",
            ),
        ],
    ),
    "internal_links_integration": (
        "Internal links",
        [
            ("approved link(s) never embedded", "some you approved are missing"),
            (
                "only present as a bolted-on line",
                "some sit on a line of their own instead of in a sentence",
            ),
            ("present but possibly misplaced", "some sit in sentences about something else"),
            ("approved link(s) skipped, low topical overlap", "some were left out as off-topic"),
        ],
    ),
    "facts_and_external_links": (
        "Sources",
        [
            (
                "provenance unverifiable",
                "this run's research wasn't recorded, so they can't be checked",
            ),
            (
                "citation(s) not traceable to any search_tool result",
                "some can't be traced to this run's research",
            ),
            (
                "sourced fact(s)/link(s) never woven into the prose",
                "some sourced facts or links aren't woven into the text",
            ),
            (
                "external citations is more than recommended",
                "there are more citations than this kind of article needs",
            ),
            (
                "fact(s) wording doesn't clearly match its cited source",
                "some facts don't clearly match their source",
            ),
        ],
    ),
}


def _one_cause(name: str, detail: str) -> str:
    cases = _ONE_CAUSE[name]
    if detail in {line for _, line in cases}:
        return detail
    return next((line for marker, line in cases if marker in detail), USER_WORDING[name])


def _several_causes(name: str, detail: str) -> str:
    subject, cases = _SEVERAL_CAUSES[name]
    if detail.startswith(f"{subject}: "):
        return detail
    found = list(dict.fromkeys(clause for marker, clause in cases if marker in detail))
    return f"{subject}: {'; '.join(found)}." if found else USER_WORDING[name]


# Checks whose line depends on what the check found (a count, a direction, a cause).
_FROM_DETAIL = {
    "unsupported_claims": _claims,
    "meta_description_length": _meta_length,
    **{name: (lambda detail, name=name: _one_cause(name, detail)) for name in _ONE_CAUSE},
    **{name: (lambda detail, name=name: _several_causes(name, detail)) for name in _SEVERAL_CAUSES},
}


def user_detail(name: Any, detail: Any = "") -> str:
    """The line a person reads for a failed check, whatever the check's own detail says."""
    name = str(name or "")
    if name in _FROM_DETAIL:
        return _FROM_DETAIL[name](str(detail or ""))
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
