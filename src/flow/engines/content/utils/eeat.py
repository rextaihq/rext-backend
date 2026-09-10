from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Mapping, Optional

from src.flow.model.structure.eeat import EEATTrustScore
from src.flow.model.structure.outlines import get_outline_display_name, normalize_content_type
from src.flow.prompts.system.eeat_scoring import (
    CONTENT_TYPE_GUIDANCE,
    EEAT_SCORING_SYSTEM_PROMPT,
    PILLAR_SIGNALS,
    RUBRIC_VERSION,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 4096
MAX_MARKDOWN_CHARS = 16000
SCORING_SCOPE = "content_level_only"

PILLAR_WEIGHTS = {
    "experience": 0.20,
    "expertise": 0.25,
    "authoritativeness": 0.20,
    "trustworthiness": 0.35,
}

EEAT_HIGH_PRIORITY = {
    "blog",
    "how-to-guide",
    "explainer",
    "pillar-content",
    "tutorial",
    "white-paper",
    "case-study",
    "checklist",
    "faq",
    "comparison",
    "best-tools",
    "alternatives",
    "in-depth-review",
    "pros-cons",
    "product-roundup",
    "buying-guide",
    "about-us",
    "documentation",
    "help-center",
    "brand-page",
}

EEAT_MEDIUM_PRIORITY = {
    "glossary",
    "resource-list",
    "feature-overview",
}

EEAT_LOW_PRIORITY = {
    "sales-page",
    "pricing-page",
    "signup-page",
    "demo-page",
    "coupon-page",
    "checkout-page",
    "landing-page",
    "service-page",
    "product-homepage",
    "login-guide",
    "contact-us",
}


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(high, value))


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def to_plain_data(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return to_plain_data(value.model_dump())
    if isinstance(value, Mapping):
        return {str(k): to_plain_data(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_plain_data(item) for item in value]
    return value


def as_mapping(value: Any) -> Dict[str, Any]:
    value = to_plain_data(value)
    return dict(value) if isinstance(value, Mapping) else {}


def get_eeat_priority(content_type: str | None) -> str:
    normalized = normalize_content_type(content_type)
    if normalized in EEAT_HIGH_PRIORITY:
        return "high"
    if normalized in EEAT_MEDIUM_PRIORITY:
        return "medium"
    if normalized in EEAT_LOW_PRIORITY:
        return "low"
    return "high"


def score_status(score: float) -> str:
    if score >= 75:
        return "good"
    if score >= 50:
        return "needs_work"
    return "poor"


def _format_signal_table(signals: List[tuple[str, str, int]]) -> str:
    lines = ["| Signal ID | Label | Max pts |", "|---|---|---:|"]
    for signal_id, label, max_pts in signals:
        lines.append(f"| {signal_id} | {label} | {max_pts} |")
    return "\n".join(lines)


def _compact_metadata(metadata: Optional[Dict[str, Any]]) -> str:
    metadata = as_mapping(metadata)
    facts = [as_mapping(item) for item in (metadata.get("facts") or []) if as_mapping(item)]
    outbound = [
        as_mapping(item) for item in (metadata.get("outbound_links") or []) if as_mapping(item)
    ]
    schema = as_mapping(metadata.get("schema_markup"))

    payload = {
        "content_type": metadata.get("content_type"),
        "title": metadata.get("title"),
        "meta_title": metadata.get("meta_title"),
        "focus_keyphrase": metadata.get("focus_keyphrase"),
        "facts": facts[:20],
        "outbound_links": outbound[:20],
        "schema_markup": schema,
        "generated_at": metadata.get("generated_at"),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def build_scoring_prompt(markdown_content: str, metadata: Optional[Dict[str, Any]] = None) -> str:
    metadata = as_mapping(metadata)
    content_type = normalize_content_type(metadata.get("content_type"))
    priority = get_eeat_priority(content_type)
    display_name = get_outline_display_name(content_type) if content_type else "Blog"

    excerpt = (markdown_content or "")[:MAX_MARKDOWN_CHARS]

    rubric_sections = "\n\n".join(
        f"### {pillar.title()}\n{_format_signal_table(signals)}"
        for pillar, signals in PILLAR_SIGNALS.items()
    )

    return f"""{EEAT_SCORING_SYSTEM_PROMPT}

---
CONTENT TYPE: {display_name} ({content_type or "blog"})
E-E-A-T PRIORITY TIER: {priority}
RUBRIC VERSION: {RUBRIC_VERSION}

{CONTENT_TYPE_GUIDANCE[priority]}

---
SCORING RUBRIC (award 0 to max_points per signal; pillar score = sum capped at 100):

{rubric_sections}

---
METADATA CONTEXT (supplementary — markdown is primary evidence):
{_compact_metadata(metadata)}

---
MARKDOWN TO EVALUATE:
{excerpt}

Return a complete EEATTrustScore object with all four pillars, every signal listed,
awarded_points, evidence quotes, reasoning, up to 6 recommendations, and confidence.

Set confidence (0-100) per the confidence scoring rules above — this reflects how
certain you are in the assessment given available evidence, NOT the E-E-A-T quality
of the content itself.
"""


def _sum_signal_awards(pillar_data: Dict[str, Any]) -> float:
    signals = pillar_data.get("signals") or []
    total = sum(clamp(as_mapping(s).get("awarded_points", 0)) for s in signals)
    return clamp(total)


def _reconcile_pillar(pillar_data: Dict[str, Any]) -> float:
    from_signals = _sum_signal_awards(pillar_data)
    reported = clamp(as_mapping(pillar_data).get("score", from_signals))
    if abs(reported - from_signals) > 2.0:
        return round(from_signals, 2)
    return round(reported, 2)


def compute_weighted_score(pillar_scores: Dict[str, float]) -> float:
    return clamp(
        sum(pillar_scores.get(pillar, 0.0) * weight for pillar, weight in PILLAR_WEIGHTS.items())
    )


def _evidence_coverage(result: EEATTrustScore) -> float:
    signals_with_evidence = 0
    total_signals = 0
    for pillar_name in ("experience", "expertise", "authoritativeness", "trustworthiness"):
        pillar = getattr(result, pillar_name)
        for signal in pillar.signals:
            total_signals += 1
            if signal.evidence and signal.evidence.lower() != "not found":
                signals_with_evidence += 1
    if not total_signals:
        return 0.0
    return signals_with_evidence / total_signals


def compute_confidence_fallback(markdown_content: str, result: EEATTrustScore) -> float:
    """Heuristic fallback when the LLM does not return a usable confidence score."""
    word_count = len(re.findall(r"\b[\w'-]+\b", markdown_content or "", flags=re.UNICODE))
    heading_count = len(re.findall(r"^#{1,6}\s", markdown_content or "", flags=re.MULTILINE))

    confidence = 55.0
    if word_count >= 600:
        confidence += 15.0
    elif word_count >= 300:
        confidence += 8.0
    else:
        confidence -= 10.0

    if heading_count >= 3:
        confidence += 8.0

    confidence += _evidence_coverage(result) * 12.0
    return round(clamp(confidence), 2)


def resolve_confidence(
    llm_confidence: float,
    markdown_content: str,
    result: EEATTrustScore,
) -> float:
    """
    Prefer the LLM-assessed confidence from structured output.
    Fall back to a lightweight heuristic only when the model omits or zeroes confidence.
    """
    llm_value = clamp(llm_confidence)
    if llm_value > 0:
        return round(llm_value, 2)
    return compute_confidence_fallback(markdown_content, result)


def validate_and_normalize(result: EEATTrustScore, markdown_content: str) -> Dict[str, Any]:
    raw = result.model_dump()

    pillar_scores: Dict[str, float] = {}
    signal_breakdown: Dict[str, List[Dict[str, Any]]] = {}

    for pillar_name in ("experience", "expertise", "authoritativeness", "trustworthiness"):
        pillar_raw = as_mapping(raw.get(pillar_name))
        reconciled = _reconcile_pillar(pillar_raw)
        pillar_scores[pillar_name] = reconciled
        signal_breakdown[pillar_name] = [
            {
                "signal_id": as_mapping(s).get("signal_id"),
                "label": as_mapping(s).get("label"),
                "max_points": as_mapping(s).get("max_points"),
                "awarded_points": round(clamp(as_mapping(s).get("awarded_points", 0)), 2),
                "evidence": as_mapping(s).get("evidence", "not found"),
            }
            for s in (pillar_raw.get("signals") or [])
        ]

    overall = compute_weighted_score(pillar_scores)
    status = score_status(overall)
    confidence = resolve_confidence(
        clamp(as_mapping(raw).get("confidence", 0)),
        markdown_content,
        result,
    )

    recommendations = [
        normalize_whitespace(str(item))
        for item in (raw.get("recommendations") or [])
        if normalize_whitespace(str(item))
    ][:6]

    return {
        "score": round(overall, 2),
        "trust_score": round(overall, 2),
        "status": status,
        "experience": pillar_scores["experience"],
        "expertise": pillar_scores["expertise"],
        "authoritativeness": pillar_scores["authoritativeness"],
        "trustworthiness": pillar_scores["trustworthiness"],
        "signal_breakdown": signal_breakdown,
        "reasoning": normalize_whitespace(str(raw.get("reasoning") or "")),
        "recommendations": recommendations,
        "confidence": confidence,
        "rubric_version": RUBRIC_VERSION,
        "content_type": normalize_content_type(as_mapping(raw).get("content_type")),
        "scoring_scope": SCORING_SCOPE,
    }


async def calculate_eeat_trust_score(
    markdown_content: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Evaluate content-level E-E-A-T from markdown using an LLM rubric scorer.

    Accepts assembled markdown (title + introduction + body) and optional metadata
    for supplementary context. No HTML parsing or deterministic fallback.
    """
    markdown_content = (markdown_content or "").strip()
    if not markdown_content:
        logger.warning("Empty markdown provided for E-E-A-T evaluation")
        return {}

    metadata = as_mapping(metadata)
    if metadata.get("content_type"):
        metadata["content_type"] = normalize_content_type(metadata["content_type"])

    logger.info(
        "Starting LLM E-E-A-T evaluation (type=%s, chars=%d)",
        metadata.get("content_type"),
        len(markdown_content),
    )

    from src.flow.model.llm_manager import load_model

    prompt = build_scoring_prompt(markdown_content, metadata)
    llm = load_model(max_tokens=DEFAULT_MAX_TOKENS).with_structured_output(EEATTrustScore)
    llm_result = await llm.ainvoke(prompt)

    normalized = validate_and_normalize(llm_result, markdown_content)
    normalized["content_type"] = metadata.get("content_type") or normalized.get("content_type")

    logger.info(
        "E-E-A-T score calculated: %.1f (%s)",
        normalized["score"],
        normalized["status"],
    )
    return normalized
