"""Title <-> content subject alignment.

Pins a specific production defect: a title that compares AGENCIES shipped with
a body that compares TOOLS. Both are well-formed articles, both contain the
focus keyphrase, and every existing check passed — the mismatch was invisible
because nothing compared what the title promises with what the body delivers.

The signal used here is the title's ENTITY CLASS: the noun that says what kind
of thing the article is about (agencies / tools / courses / templates ...).
That is a narrow, low-false-positive comparison — far safer than generic
semantic similarity, which flags paraphrase as mismatch — and it is exactly
the axis the reported defect drifted along.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

# class key -> the surface forms that signal it. Keys are arbitrary labels;
# only the grouping matters. Two different classes appearing in one title is
# fine (e.g. "agency tools") — the check only fires on a class the title
# claims that the body then fails to deliver.
_ENTITY_CLASSES: dict[str, tuple[str, ...]] = {
    "agency": ("agency", "agencies"),
    "tool": ("tool", "tools"),
    "software": ("software",),
    "platform": ("platform", "platforms"),
    "app": ("app", "apps", "application", "applications"),
    "plugin": ("plugin", "plugins", "extension", "extensions", "addon", "addons"),
    "service": ("service", "services"),
    "company": ("company", "companies"),
    "vendor": ("vendor", "vendors", "supplier", "suppliers"),
    "provider": ("provider", "providers"),
    "freelancer": ("freelancer", "freelancers"),
    "consultant": ("consultant", "consultants", "consultancy", "consultancies"),
    "course": ("course", "courses", "class", "classes", "bootcamp", "bootcamps"),
    "book": ("book", "books", "ebook", "ebooks"),
    "template": ("template", "templates"),
    "framework": ("framework", "frameworks"),
    "strategy": ("strategy", "strategies", "tactic", "tactics"),
    "example": ("example", "examples", "case study", "case studies"),
    "mistake": ("mistake", "mistakes", "error", "errors", "pitfall", "pitfalls"),
    "tip": ("tip", "tips", "trick", "tricks"),
    "trend": ("trend", "trends"),
    "metric": ("metric", "metrics", "kpi", "kpis"),
    "checklist": ("checklist", "checklists"),
    "certification": ("certification", "certifications", "certificate", "certificates"),
}

# Minimum body occurrences of a class the title claims. One passing mention is
# not delivery — an article about tools can name-drop "agency" once.
_MIN_BODY_OCCURRENCES = 3

# A competing class must beat the promised one by this factor before the
# article counts as being about something else. Generous on purpose: "the best
# SEO agencies and the tools they use" is a legitimate article, not a defect.
_DOMINANCE_FACTOR = 2.0


def _count_occurrences(text: str, surface_forms: Iterable[str]) -> int:
    lowered = (text or "").lower()
    total = 0
    for form in surface_forms:
        total += len(re.findall(rf"\b{re.escape(form)}\b", lowered))
    return total


def detect_title_entity_classes(title: str) -> list[str]:
    """Entity classes the title claims the article is about."""
    if not title:
        return []
    return [key for key, forms in _ENTITY_CLASSES.items() if _count_occurrences(title, forms)]


def find_subject_mismatch(title: str, content_text: str) -> Optional[dict]:
    """Return mismatch detail when the body does not deliver the title's subject.

    None means aligned (including "the title names no entity class", which is
    the common case for how-to and explainer titles and must not be reported
    as a failure).
    """
    promised_classes = detect_title_entity_classes(title)
    if not promised_classes or not content_text:
        return None

    counts = {
        key: _count_occurrences(content_text, forms) for key, forms in _ENTITY_CLASSES.items()
    }

    for promised in promised_classes:
        promised_count = counts.get(promised, 0)

        if promised_count < _MIN_BODY_OCCURRENCES:
            competitor = _dominant_other_class(counts, promised_classes)
            return {
                "promised_class": promised,
                "promised_count": promised_count,
                "dominant_class": competitor[0] if competitor else None,
                "dominant_count": competitor[1] if competitor else 0,
                "reason": "absent",
            }

        competitor = _dominant_other_class(counts, promised_classes)
        if competitor and competitor[1] >= promised_count * _DOMINANCE_FACTOR:
            return {
                "promised_class": promised,
                "promised_count": promised_count,
                "dominant_class": competitor[0],
                "dominant_count": competitor[1],
                "reason": "dominated",
            }

    return None


def _dominant_other_class(
    counts: dict[str, int], promised_classes: list[str]
) -> Optional[tuple[str, int]]:
    others = [
        (key, value) for key, value in counts.items() if key not in promised_classes and value
    ]
    if not others:
        return None
    return max(others, key=lambda item: item[1])


def describe_subject_lock(title: str) -> str:
    """Prompt-ready statement of the subject the article must actually cover.

    Returned text is injected into the generation prompt next to the title so
    the constraint is stated where the model reads the title, rather than as a
    detached paragraph elsewhere in a long message.
    """
    classes = detect_title_entity_classes(title)
    if not classes:
        return (
            "SUBJECT LOCK: the article must be about exactly the subject, entity and "
            "intent the title states — do not substitute a related but different "
            "subject, and do not broaden or narrow it."
        )

    readable = ", ".join(_ENTITY_CLASSES[key][-1] for key in classes)
    return (
        f"SUBJECT LOCK — CRITICAL: the title is about {readable}. The article body must be "
        f"about {readable} too. Every comparison, list entry, recommendation and example must "
        f"be {readable} — not a different category of thing. For example, if the title is "
        f"about agencies, do NOT write about software tools instead; if the title is about "
        f"tools, do NOT write about agencies instead. Mentioning the other category in "
        f"passing is fine; making the article about it is a defect."
    )
