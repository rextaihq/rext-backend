"""What the SERP shows, in a form the content-type and topic gates can put on screen.

The content-type step shows an evidence line above its suggestions ("6 of 10
results are list posts · 4 questions people also ask · AI Overview present")
and the topic step shows the top-ten titles beside its candidates
(plans/app/E-workflow.md, steps 3 and 4). Everything here is read from the
normalised SERP the run already holds; nothing is guessed when the data is not
there: no SERP gives no evidence, and no format counts as dominant unless
enough results share it.

A result's format is read from its title (and, for a home page, its URL) with
deliberately plain patterns, checked in a fixed order so that "10 best Notion
alternatives" is an alternatives page rather than a list post. Each format
names the content types it supports, so the screen can tie the line to the
cards it sits above.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Optional, TypedDict
from urllib.parse import urlparse

TOP_RESULTS = 10
# A format is "dominant" only when at least this many of the top results share
# it, and at least this share of them: two list posts in ten are not a pattern.
DOMINANT_MIN_COUNT = 3
DOMINANT_MIN_SHARE = 0.3


class FormatInfo(TypedDict):
    label: str  # plural, for "6 of 10 results are <label>"
    content_types: list[str]


FORMATS: dict[str, FormatInfo] = {
    "alternatives": {"label": "alternatives pages", "content_types": ["alternatives"]},
    "comparison": {"label": "comparisons", "content_types": ["comparison", "alternatives"]},
    "how-to": {"label": "how-to guides", "content_types": ["how-to-guide", "tutorial"]},
    "review": {"label": "reviews", "content_types": ["in-depth-review", "pros-cons"]},
    "list": {
        "label": "list posts",
        "content_types": ["best-tools", "product-roundup", "resource-list", "checklist"],
    },
    "explainer": {"label": "explainers", "content_types": ["explainer", "glossary", "faq"]},
    "guide": {"label": "in-depth guides", "content_types": ["pillar-content", "buying-guide"]},
    "home-page": {
        "label": "home pages",
        "content_types": ["product-homepage", "landing-page", "brand-page"],
    },
}

# Checked in this order; the first match wins.
_TITLE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("alternatives", re.compile(r"\balternatives?\b", re.I)),
    ("comparison", re.compile(r"\bvs\.?\b|\bversus\b|\bcompar(e|ed|ing|ison)\b", re.I)),
    (
        "how-to",
        re.compile(r"^how to\b|\bstep[- ]by[- ]step\b|\btutorial\b|\b\d+ (easy )?steps\b", re.I),
    ),
    (
        "list",
        re.compile(
            r"^(the )?(top )?\d+\b|\b\d+ (best|top)\b|\b(top|best) \d+\b|^(the )?(top|best)\b"
            r"|\blist of\b",
            re.I,
        ),
    ),
    ("review", re.compile(r"\breview(s|ed)?\b", re.I)),
    (
        "explainer",
        re.compile(
            r"^(what|who|why) (is|are|does|do)\b|\bmeaning\b|\bdefinition\b|\bexplained\b", re.I
        ),
    ),
    ("guide", re.compile(r"\bguide\b|\beverything you need to know\b", re.I)),
]


def classify_result_format(title: str, url: str = "") -> Optional[str]:
    """The format a search result's page is in, or None when nothing marks it."""
    title = (title or "").strip()
    for name, pattern in _TITLE_PATTERNS:
        if pattern.search(title):
            return name
    path = urlparse(url or "").path
    if url and path in ("", "/"):
        return "home-page"
    return None


def _top_results(serp_normalized: Optional[dict]) -> list[dict]:
    results = (serp_normalized or {}).get("normalize_results") or []
    return [r for r in results if isinstance(r, dict)][:TOP_RESULTS]


def build_serp_evidence(serp_normalized: Optional[dict]) -> Optional[dict[str, Any]]:
    """The content-type gate's evidence, or None when the run has no SERP (a library keyword).

    {"results": 10,
     "dominant_format": {"format": "list", "label": "list posts", "count": 6,
                         "content_types": [...]} or None,
     "formats": {"list": 6, "how-to": 2},
     "paa_count": 4,
     "ai_overview": True | False | None}
    """
    top = _top_results(serp_normalized)
    if not top:
        return None

    formats = [classify_result_format(r.get("title") or "", r.get("url") or "") for r in top]
    counts = Counter(f for f in formats if f)
    dominant = None
    if counts:
        # The most common format; a tie goes to the one ranked highest.
        best = max(counts, key=lambda f: (counts[f], -formats.index(f)))
        if counts[best] >= DOMINANT_MIN_COUNT and counts[best] / len(top) >= DOMINANT_MIN_SHARE:
            dominant = {"format": best, "count": counts[best], **FORMATS[best]}

    questions = (serp_normalized or {}).get("questions") or []
    features = (serp_normalized or {}).get("features") or {}
    return {
        "results": len(top),
        "dominant_format": dominant,
        "formats": dict(counts.most_common()),
        "paa_count": len(
            {q.strip().lower() for q in questions if isinstance(q, str) and q.strip()}
        ),
        # None when the SERP was read before the flag existed.
        "ai_overview": features.get("ai_overview"),
    }


def build_serp_titles(serp_normalized: Optional[dict]) -> list[dict[str, Any]]:
    """The top-ten results as the topic gate shows them beside its candidates."""
    return [
        {
            "position": r.get("position"),
            "title": r.get("title") or "",
            "domain": r.get("domain") or "",
            "url": r.get("url") or "",
            "format": classify_result_format(r.get("title") or "", r.get("url") or ""),
        }
        for r in _top_results(serp_normalized)
    ]
