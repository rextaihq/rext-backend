from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field

Tone = Literal["Professional", "Conversational", "Authoritative"]


class ImageSuggestion(BaseModel):
    description: str = Field(description="What the image should show.")
    alt_text_template: str = Field(description="SEO-optimized alt text template.")
    section: str = Field(description="Where the image should appear (e.g., 'intro', 'h2-3').")


class LinkSuggestion(BaseModel):
    anchor_text: str = Field(description="Suggested anchor text.")
    link_type: Literal["internal", "outbound"] = Field(description="Link type.")
    context: str = Field(description="What this link points to and why.")
    section: str = Field(description="Where this link should appear (e.g., 'h2-2', 'conclusion').")


class OutlineBase(BaseModel):
    # Core identity (strict: selected content type must be explicit in the output)
    content_type: str = Field(description="Canonical content type slug (kebab-case).")

    # SEO core
    title: str = Field(description="SEO-optimized title that includes the focus keyphrase.")
    slug_suggestion: str = Field(description="URL slug containing the focus keyphrase.")
    brief: str = Field(description="Goal + value proposition (who this is for, why it matters).")
    focus_keyphrase: str = Field(description="Primary focus keyphrase (2-6 words).")
    keywords_to_include: Annotated[
        list[str], Field(min_length=1, description="Secondary keywords / entities to include.")
    ]

    # Strategy
    target_audience: Annotated[
        list[str],
        Field(
            min_length=1,
            description=(
                "Persona(s) + intent (e.g., 'Beginner freelancers', 'IT managers')."
            ),
        ),
    ]
    tone: Tone
    target_word_count: int = Field(ge=300, le=5000)

    # Media / links
    image_suggestions: Annotated[list[ImageSuggestion], Field(min_length=1)]
    link_suggestions: Annotated[list[LinkSuggestion], Field(min_length=2)]


def _canonicalize_heading(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _ensure_no_duplicate_strings(items: List[str], label: str) -> None:
    normalized = [_canonicalize_heading(x) for x in items]
    duplicates = sorted({n for n in normalized if n and normalized.count(n) > 1})
    if duplicates:
        raise ValueError(f"{label} contains duplicates: {', '.join(duplicates[:5])}")


def _ensure_no_generic_headings(headings: List[str], label: str) -> None:
    banned = {"introduction", "conclusion", "summary", "overview"}
    bad = [h for h in headings if _canonicalize_heading(h) in banned]
    if bad:
        raise ValueError(
            f"{label} contains generic headings ({', '.join(sorted(set(bad)))}) "
            "— make headings specific and keyword-rich."
        )


def _ensure_focus_keyphrase_in_title(title: str, focus_keyphrase: str) -> None:
    if not focus_keyphrase:
        raise ValueError("focus_keyphrase is empty")
    if _canonicalize_heading(focus_keyphrase) not in _canonicalize_heading(title):
        raise ValueError("title must include the focus_keyphrase (exact or close variant)")


def _safe_list(value: Optional[List[str]]) -> List[str]:
    return list(value or [])
