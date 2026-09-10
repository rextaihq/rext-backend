"""Where cited facts and external links belong, per content type.

Companion to brand_placement_policy.py — same per-content-type research
approach, applied to third-party citations (facts sourced via search_tool)
rather than brand promotion. Fixes a concrete, reported failure mode: 2-3
external links dumped as a bare, unlabeled list at the end of the article
instead of woven into the sentence that makes the claim they support.

2026 SEO/AEO context: AI-answer-engine citation extraction and modern search
ranking both reward specific, verifiable claims attributed inline next to the
sentence they support — a trailing, unlabeled link dump reads as an
afterthought to both a human reader and an extraction model, and gets far
less citation/trust credit than the same source referenced in context.
"""

from __future__ import annotations

from typing import Literal, TypedDict

CitationStyle = Literal["inline_only", "inline_or_references", "minimal"]


class EvidencePlacementPolicy(TypedDict):
    citation_style: CitationStyle
    guidance: str  # injected into the generation prompt verbatim
    max_recommended_citations: int  # soft cap — exceeding it is a warning, not blocking


_INLINE_ONLY_GUIDANCE = (
    "Weave every cited fact/statistic directly into the sentence that makes the claim it supports "
    '(e.g. "...cuts onboarding time by 40% [per a recent industry survey](url)..."). Do NOT collect '
    'citations into a list, footnote block, or a "Sources"/"References" section at the end — every '
    "citation must sit inline, immediately next to the specific claim it backs."
)
_REFERENCES_GUIDANCE = (
    "Prefer weaving citations inline next to the claim they support — this is still the default. A "
    'labeled "Sources" or "References" section at the end is acceptable for this format ONLY if '
    "every entry is clearly attributed AND the primary claims in the body are still cited inline, not "
    "just listed there — the references section supplements inline citations, it doesn't replace them."
)
_MINIMAL_GUIDANCE = (
    "Use at most one or two sharp, verifiable statistics as trust signals (e.g. inside a benefits/social-"
    "proof section), cited inline. Do not turn this page into a research article — heavy citation "
    "undermines a conversion-focused format, and a links list here reads as off-brand clutter."
)

_INLINE_ONLY_TYPES = (
    "blog",
    "how-to-guide",
    "explainer",
    "checklist",
    "tutorial",
    "faq",
    "case-study",
    "glossary",
    "comparison",
    "best-tools",
    "product-roundup",
    "alternatives",
    "pros-cons",
    "buying-guide",
)
_INLINE_OR_REFERENCES_TYPES = ("pillar-content", "white-paper", "resource-list", "in-depth-review")
_MINIMAL_TYPES = (
    "brand-page",
    "product-homepage",
    "feature-overview",
    "documentation",
    "login-guide",
    "contact-us",
    "about-us",
    "help-center",
    "sales-page",
    "pricing-page",
    "signup-page",
    "demo-page",
    "coupon-page",
    "checkout-page",
    "landing-page",
    "service-page",
)

EVIDENCE_PLACEMENT_POLICY: dict[str, EvidencePlacementPolicy] = {
    **{
        ct: {
            "citation_style": "inline_only",
            "guidance": _INLINE_ONLY_GUIDANCE,
            "max_recommended_citations": 6,
        }
        for ct in _INLINE_ONLY_TYPES
    },
    **{
        ct: {
            "citation_style": "inline_or_references",
            "guidance": _REFERENCES_GUIDANCE,
            "max_recommended_citations": 8,
        }
        for ct in _INLINE_OR_REFERENCES_TYPES
    },
    **{
        ct: {
            "citation_style": "minimal",
            "guidance": _MINIMAL_GUIDANCE,
            "max_recommended_citations": 2,
        }
        for ct in _MINIMAL_TYPES
    },
}

_DEFAULT_EVIDENCE_POLICY: EvidencePlacementPolicy = {
    "citation_style": "inline_only",
    "guidance": _INLINE_ONLY_GUIDANCE,
    "max_recommended_citations": 6,
}


def resolve_evidence_placement_policy(content_type: str) -> EvidencePlacementPolicy:
    """The citation-style policy for this content type.

    Defaults to the strictest ("inline_only") policy for any content type
    not explicitly covered — safer to over-enforce inline weaving than to
    silently allow a link dump for an unrecognized type.
    """
    from src.flow.model.structure.outlines import normalize_content_type

    normalized = normalize_content_type(content_type)
    return EVIDENCE_PLACEMENT_POLICY.get(normalized, _DEFAULT_EVIDENCE_POLICY)
