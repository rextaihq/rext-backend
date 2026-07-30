# src/utils/content_quality.py
from typing import Any, Dict

MIN_WORD_COUNT = 50
MIN_UNIQUE_RATIO = 0.35  # below this = repetitive/filler text
MIN_FIT_RATIO = 0.15  # below this = mostly boilerplate, little real substance


def get_word_count(result: Any) -> int:
    if not result or not getattr(result, "markdown", None):
        return 0
    raw = getattr(result.markdown, "raw_markdown", "") or ""
    return len(raw.split())


def _get_fit_ratio(result: Any) -> float:
    """How much of the page is 'real' content vs boilerplate, per crawl4ai's own BM25 filter."""
    if not result or not getattr(result, "markdown", None):
        return 0.0
    raw = getattr(result.markdown, "raw_markdown", "") or ""
    fit = getattr(result.markdown, "fit_markdown", "") or ""
    raw_words = len(raw.split())
    fit_words = len(fit.split())
    if raw_words == 0:
        return 0.0
    return fit_words / raw_words


def _get_unique_ratio(result: Any) -> float:
    """Catches repeated/duplicated filler text."""
    if not result or not getattr(result, "markdown", None):
        return 0.0
    raw = getattr(result.markdown, "raw_markdown", "") or ""
    words = raw.lower().split()
    if not words:
        return 0.0
    return len(set(words)) / len(words)


def assess_content_quality(result: Any) -> Dict[str, Any]:
    """
    Returns a structured verdict instead of a single True/False,
    so callers can see WHY a page was flagged, not just that it was.
    """
    word_count = get_word_count(result)
    fit_ratio = _get_fit_ratio(result)
    unique_ratio = _get_unique_ratio(result)

    reasons = []
    if word_count < MIN_WORD_COUNT:
        reasons.append("too_few_words")
    if unique_ratio < MIN_UNIQUE_RATIO and word_count > 0:
        reasons.append("repetitive_content")
    if fit_ratio < MIN_FIT_RATIO and word_count >= MIN_WORD_COUNT:
        reasons.append("mostly_boilerplate")

    return {
        "is_thin": len(reasons) > 0,
        "reasons": reasons,
        "word_count": word_count,
        "fit_ratio": round(fit_ratio, 2),
        "unique_ratio": round(unique_ratio, 2),
    }


def build_thin_content_document(result: Any, assessment: Dict[str, Any]):
    from langchain_core.documents import Document

    reason_messages = {
        "too_few_words": "This page has very little text.",
        "repetitive_content": "This page's content looks repetitive or placeholder-like.",
        "mostly_boilerplate": "This page is mostly navigation/boilerplate with little real content.",
    }
    messages = [reason_messages[r] for r in assessment["reasons"]]
    return Document(
        page_content="",
        metadata={
            "url": getattr(result, "url", None),
            "status": "thin_content",
            **assessment,
            "message": " ".join(messages) or "This page doesn't have enough usable content.",
        },
    )
