"""The checklist shown beside a finished article (dashboard task E10).

One shape, built from what the article row keeps, so the saved article's API
response and the generation run's final state show the same thing:

    {"readability": {"score": 62.4, "band": "standard", "label": "Standard"} | None,
     "keyphrase_density": {"value": 1.4, "status": "ok", "occurrences": 9, "detail": "..."} | None,
     "validation": {"passed": False, "gave_up": True, "stage": "post_humanize",
                    "issues": [{"name", "severity", "detail"}], "warnings": [...]} | None,
     "claims_to_verify": [{"category", "sentence", "unsupported"}]}

Readability is the band of the saved Flesch reading-ease score (the same bands
the dashboard's retired card used). Density comes from the on-page analysis
already saved in `seo_details`. The validator's findings and the claims to
verify are saved by the generation run under `seo_details["content_checks"]`
(persist_content); an article saved before that, or written by hand, has none.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from src.services.check_wording import user_validation

logger = logging.getLogger(__name__)

# Flesch reading ease: the higher, the easier.
READABILITY_BANDS: list[tuple[float, str, str]] = [
    (90, "very_easy", "Very easy"),
    (80, "easy", "Easy"),
    (70, "fairly_easy", "Fairly easy"),
    (60, "standard", "Standard"),
    (50, "fairly_difficult", "Fairly difficult"),
    (30, "difficult", "Difficult"),
    (float("-inf"), "very_difficult", "Very difficult"),
]

CONTENT_CHECKS_KEY = "content_checks"


def readability_band(score: Any) -> Optional[dict[str, Any]]:
    """The band of a Flesch reading-ease score, or None when there is no score."""
    try:
        value = float(score)
    except (TypeError, ValueError):
        return None
    for floor, band, label in READABILITY_BANDS:
        if value >= floor:
            return {"score": round(value, 1), "band": band, "label": label}
    return None


def parse_seo_details(seo_details: Any) -> dict[str, Any]:
    """The saved on-page analysis as a dict; {} when missing or not JSON."""
    if isinstance(seo_details, dict):
        return seo_details
    if not seo_details:
        return {}
    try:
        parsed = json.loads(seo_details)
    except (TypeError, ValueError):
        logger.warning("content_checklist: seo_details is not JSON; ignoring it")
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _density(details: dict[str, Any]) -> Optional[dict[str, Any]]:
    quality = details.get("content_quality") or {}
    if not isinstance(quality, dict) or quality.get("keyphrase_density_status") is None:
        return None
    return {
        "value": quality.get("keyphrase_density"),
        "status": quality.get("keyphrase_density_status"),
        "occurrences": quality.get("keyphrase_occurrences"),
        "detail": quality.get("keyphrase_density_detail"),
    }


def build_checklist(*, readability_score: Any, seo_details: Any) -> dict[str, Any]:
    """The article's checklist from its saved readability score and on-page analysis."""
    details = parse_seo_details(seo_details)
    checks = details.get(CONTENT_CHECKS_KEY) or {}
    if not isinstance(checks, dict):
        checks = {}
    return {
        "readability": readability_band(readability_score),
        "keyphrase_density": _density(details),
        # In words for the reader, for articles saved before the saved detail was.
        "validation": user_validation(checks.get("validation")),
        "claims_to_verify": checks.get("claims_to_verify") or [],
    }
