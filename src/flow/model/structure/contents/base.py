"""
Hardened Pydantic schema for generated content with strict on-page SEO validation.

SEO Enforcement Rules (2026 best practices):
- Title:            20–60 chars, ≤10 words, focus keyphrase at the START
- Slug:             lowercase, hyphens only, ≤80 chars
- Meta title:       50–60 chars, ≤10 words, focus keyphrase present
- Meta description: 140–160 chars, focus keyphrase present exactly once
- Introduction:     focus keyphrase in first sentence, ≥3 paragraphs
- Body markdown:    H1 required, keyphrase in H1, ≥1 image with keyphrase
                    in alt text, ≥1 internal link, H2 ≤10 words / ≤60 chars,
                    H3 ≤8 words / ≤50 chars
"""

from __future__ import annotations

import re
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator
from src.flow.model.structure.content import ImageAltText, Link, SchemaMarkup
from src.flow.model.structure.outline import Fact


# ─────────────────────────────────────────────────────────────────────────────
# Helper utilities
# ─────────────────────────────────────────────────────────────────────────────

def _contains_keyphrase(text: str, keyphrase: str) -> bool:
    """Case-insensitive substring check."""
    return keyphrase.lower() in text.lower()


def _first_sentence(text: str) -> str:
    """Return the first sentence (split on . ! ?) of a block of text."""
    match = re.split(r"[.!?]", text.strip())
    return match[0].strip() if match else text.strip()


def _paragraph_count(text: str) -> int:
    """Count non-empty paragraphs (blank-line separated)."""
    blocks = [b.strip() for b in re.split(r"\n{2,}", text.strip())]
    return sum(1 for b in blocks if b)


def _extract_headings(markdown: str) -> list[tuple[int, str]]:
    """
    Return list of (level, heading_text) tuples from a markdown string.
    level 1 = H1, 2 = H2, 3 = H3.
    Only levels 1–3 are validated.
    """
    results = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("### "):
            results.append((3, stripped[4:].strip()))
        elif stripped.startswith("## "):
            results.append((2, stripped[3:].strip()))
        elif stripped.startswith("# "):
            results.append((1, stripped[2:].strip()))
    return results


def _extract_image_alts(markdown: str) -> list[str]:
    """Return all image alt texts from markdown ![alt](src) syntax."""
    return re.findall(r"!\[([^\]]*)\]", markdown)


def _extract_internal_links(markdown: str) -> list[str]:
    """Return all markdown link texts [text](url) — simple heuristic."""
    return re.findall(r"\[([^\]]+)\]\(([^)]+)\)", markdown)


# ─────────────────────────────────────────────────────────────────────────────
# Main schema
# ─────────────────────────────────────────────────────────────────────────────

class BaseGeneratedContent(BaseModel):
    """
    Validated schema for all generated content types.

    Every field includes SEO guardrails enforced at validation time so
    downstream consumers receive content that is already compliant.
    """

    # ── Core SEO fields ───────────────────────────────────────────────────────

    title: str = Field(
        min_length=20,
        max_length=60,
        description=(
            "SEO page title: 20–60 characters, ≤10 words. "
            "Focus keyphrase MUST appear at the very beginning. "
            "No clickbait, no filler words."
        ),
    )

    slug: Optional[str] = Field(
        default=None,
        pattern=r"^[a-z0-9-]+$",
        max_length=80,
        description="Lowercase SEO-friendly slug using hyphens only. ≤80 chars.",
    )

    meta_title: Optional[str] = Field(
        default=None,
        min_length=50,
        max_length=60,
        description=(
            "SEO meta title: strictly 50–60 chars, ≤10 words. "
            "Must contain the focus keyphrase."
        ),
    )

    meta_description: Optional[str] = Field(
        default=None,
        min_length=140,
        max_length=160,
        description=(
            "SEO meta description: 140–160 chars. "
            "Include focus keyphrase exactly once, naturally."
        ),
    )

    # ── Keyphrase & keyword fields ────────────────────────────────────────────

    focus_keyphrase: Optional[str] = Field(
        default=None,
        description="Primary focus keyphrase used for all SEO validations.",
    )

    keyphrase_density: Optional[float] = Field(
        default=None,
        ge=0.5,
        le=3.0,
        description=(
            "Keyphrase density as a percentage. "
            "Target 0.5–3.0 % to avoid under-optimisation or keyword stuffing."
        ),
    )

    secondary_keywords: List[str] = Field(
        default_factory=list,
        description="Supporting LSI / secondary keywords.",
    )

    tags: List[str] = Field(
        default_factory=list,
        description="Taxonomy tags for the content.",
    )

    # ── Content body fields ───────────────────────────────────────────────────

    introduction: Optional[str] = Field(
        default=None,
        description=(
            "Opening section containing the focus keyphrase in the very first sentence. "
            "Must be at least 3 full paragraphs — never a single short paragraph."
        ),
    )

    body_markdown: Optional[str] = Field(
        default=None,
        description=(
            "Complete content body in Markdown (excluding introduction). "
            "REQUIREMENTS: "
            "(1) Exactly one H1 that contains the focus keyphrase. 20–58 chars, 5-8 words. "
            "(2) At least one image with the focus keyphrase in its alt text. "
            "(3) At least one internal link. "
            "(4) H2 headings: ≤8 words and ≤58 characters. "
            "(5) H3 headings: ≤6 words and ≤48 characters. "
            "(6) Every H2 section must be substantial — no stub sections. "
            "Do not summarise — elaborate with examples, data, step-by-step "
            "breakdowns, and real-world anecdotes."
        ),
    )

    # ── SEO enrichment fields ─────────────────────────────────────────────────

    images: List[ImageAltText] = Field(
        default_factory=list,
        description=(
            "SEO-optimised image alt suggestions. "
            "At least one must include the focus keyphrase."
        ),
    )

    internal_links: List[Link] = Field(
        default_factory=list,
        description="Internal link suggestions (minimum 1 required).",
    )

    outbound_links: List[Link] = Field(
        default_factory=list,
        description="Outbound / external link suggestions.",
    )

    schema_markup: Optional[SchemaMarkup] = Field(
        default=None,
        description="JSON-LD schema markup (Article, FAQPage, HowTo, etc.).",
    )

    facts: List[Fact] = Field(
        default_factory=list,
        description="Verifiable statistics or facts cited in the content.",
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Model-level validator — runs before field validators
    # ─────────────────────────────────────────────────────────────────────────

    @model_validator(mode="before")
    @classmethod
    def fix_links_and_normalize(cls, data: Any) -> Any:
        """
        Normalize link fields before field-level validation:
        - Infer link_type from field name if missing.
        - Supply required fallback fields (placement, anchor_text).
        """
        if not isinstance(data, dict):
            return data

        for field_name in ("internal_links", "outbound_links"):
            raw_links = data.get(field_name, [])

            if not isinstance(raw_links, list):
                raw_links = []

            fixed = []
            for link_raw in raw_links:
                if not isinstance(link_raw, dict):
                    continue

                link = link_raw.copy()
                link.setdefault(
                    "link_type",
                    "internal" if field_name == "internal_links" else "external",
                )
                link.setdefault("placement", "body")
                link.setdefault("anchor_text", link.get("url", "Read more"))
                fixed.append(link)

            data[field_name] = fixed

        return data

    # ─────────────────────────────────────────────────────────────────────────
    # Field-level validators
    # ─────────────────────────────────────────────────────────────────────────

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        value = value.strip()
        words = value.split()

        if len(words) > 10:
            raise ValueError(
                f"Title exceeds 10 words ({len(words)} words): '{value}'"
            )

        return value

    @field_validator("meta_title")
    @classmethod
    def validate_meta_title(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value

        value = value.strip()
        words = value.split()

        if len(words) > 10:
            raise ValueError(
                f"Meta title exceeds 10 words ({len(words)} words): '{value}'"
            )

        return value

    @field_validator("keyphrase_density")
    @classmethod
    def validate_keyphrase_density(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and not (0.5 <= value <= 3.0):
            raise ValueError(
                f"Keyphrase density {value:.2f}% is outside the 0.5–3.0% safe range."
            )
        return value

    @field_validator("introduction")
    @classmethod
    def validate_introduction(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value

        paragraphs = _paragraph_count(value)
        if paragraphs < 3:
            raise ValueError(
                f"Introduction must contain at least 3 paragraphs; "
                f"found {paragraphs}. Expand the opening section."
            )

        return value

    @field_validator("body_markdown")
    @classmethod
    def validate_body_markdown(cls, value: Optional[str]) -> Optional[str]:
        """
        Validate all structural on-page SEO requirements in body_markdown:
        1. Heading word / character limits (H2 ≤10 words / 60 chars, H3 ≤8 words / 50 chars)
        2. Exactly one H1 present
        3. At least one image alt text present
        4. At least one internal link present (markdown link syntax)
        """
        if not value:
            return value

        headings = _extract_headings(value)
        errors: list[str] = []

        # ── 1. Heading length checks ──────────────────────────────────────────
        for level, heading in headings:
            if level == 2:
                if len(heading.split()) > 10:
                    errors.append(f"H2 exceeds 10 words: '{heading}'")
                if len(heading) > 60:
                    errors.append(f"H2 exceeds 60 characters: '{heading}'")

            elif level == 3:
                if len(heading.split()) > 8:
                    errors.append(f"H3 exceeds 8 words: '{heading}'")
                if len(heading) > 50:
                    errors.append(f"H3 exceeds 50 characters: '{heading}'")

        # ── 2. Exactly one H1 ────────────────────────────────────────────────
        h1_headings = [h for lvl, h in headings if lvl == 1]
        if len(h1_headings) == 0:
            errors.append(
                "No H1 found in body_markdown. "
                "Add exactly one H1 containing the focus keyphrase."
            )
        elif len(h1_headings) > 1:
            errors.append(
                f"Multiple H1 headings found ({len(h1_headings)}). "
                "Only one H1 is allowed per document."
            )

        # ── 3. At least one image ─────────────────────────────────────────────
        image_alts = _extract_image_alts(value)
        if not image_alts:
            errors.append(
                "No images found in body_markdown. "
                "Add at least one image with a descriptive alt text "
                "containing the focus keyphrase."
            )

        # ── 4. At least one internal link ────────────────────────────────────
        links = _extract_internal_links(value)
        if not links:
            errors.append(
                "No links found in body_markdown. "
                "Add at least one internal link to improve content structure."
            )

        if errors:
            raise ValueError(
                "body_markdown failed SEO validation:\n  - "
                + "\n  - ".join(errors)
            )

        return value

    # ─────────────────────────────────────────────────────────────────────────
    # Cross-field validators — keyphrase presence checks
    # ─────────────────────────────────────────────────────────────────────────

    @model_validator(mode="after")
    def validate_keyphrase_presence(self) -> "BaseGeneratedContent":
        """
        After all field validators pass, enforce keyphrase placement rules
        that require access to multiple fields simultaneously.
        """
        kp = self.focus_keyphrase
        if not kp:
            # Cannot enforce keyphrase rules without a keyphrase defined.
            return self

        errors: list[str] = []

        # ── Title: keyphrase must appear at the start ─────────────────────────
        title_lower = self.title.lower()
        kp_lower = kp.lower()

        if kp_lower not in title_lower:
            errors.append(
                f"Focus keyphrase '{kp}' not found in title: '{self.title}'"
            )
        elif not title_lower.startswith(kp_lower):
            errors.append(
                f"Focus keyphrase '{kp}' must appear at the START of the title. "
                f"Current title: '{self.title}'"
            )

        # ── Meta title: keyphrase must be present ─────────────────────────────
        if self.meta_title and not _contains_keyphrase(self.meta_title, kp):
            errors.append(
                f"Focus keyphrase '{kp}' not found in meta_title: '{self.meta_title}'"
            )

        # ── Meta description: keyphrase must appear exactly once ──────────────
        if self.meta_description:
            count = self.meta_description.lower().count(kp_lower)
            if count == 0:
                errors.append(
                    f"Focus keyphrase '{kp}' not found in meta_description."
                )
            elif count > 1:
                errors.append(
                    f"Focus keyphrase '{kp}' appears {count} times in "
                    f"meta_description. It should appear exactly once."
                )

        # ── Introduction: keyphrase in the very first sentence ────────────────
        if self.introduction:
            first = _first_sentence(self.introduction)
            if not _contains_keyphrase(first, kp):
                errors.append(
                    f"Focus keyphrase '{kp}' must appear in the first sentence "
                    f"of the introduction. First sentence found: '{first[:120]}…'"
                )

        # ── Body: H1 must contain keyphrase ──────────────────────────────────
        if self.body_markdown:
            headings = _extract_headings(self.body_markdown)
            h1_headings = [h for lvl, h in headings if lvl == 1]

            if h1_headings and not _contains_keyphrase(h1_headings[0], kp):
                errors.append(
                    f"Focus keyphrase '{kp}' not found in H1: '{h1_headings[0]}'"
                )

            # ── Body: at least one image alt must contain keyphrase ───────────
            image_alts = _extract_image_alts(self.body_markdown)
            if image_alts:
                if not any(_contains_keyphrase(alt, kp) for alt in image_alts):
                    errors.append(
                        f"Focus keyphrase '{kp}' not found in any image alt text. "
                        f"At least one image alt must include the focus keyphrase."
                    )

        # ── images list: at least one alt must contain keyphrase ──────────────
        if self.images:
            alts = [img.alt_text for img in self.images if hasattr(img, "alt_text")]
            if alts and not any(_contains_keyphrase(a, kp) for a in alts):
                errors.append(
                    f"Focus keyphrase '{kp}' not found in any ImageAltText.alt_text. "
                    "At least one image suggestion must include the focus keyphrase."
                )

        if errors:
            raise ValueError(
                "Keyphrase placement validation failed:\n  - "
                + "\n  - ".join(errors)
            )

        return self


if __name__ == "__main__":
    pass