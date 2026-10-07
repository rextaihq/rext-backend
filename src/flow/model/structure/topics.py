"""Structured-output schema for SEO topic/title generation.

The field descriptions here are the model's second line of defence after the
system prompt: a constrained decoder re-reads them at the moment it writes each
field, so the title contract is restated where the title is actually produced.

Nothing here RAISES on a contract violation. Structured-output parsing failures
are indistinguishable from transient model errors at the call site, and a
single bad title must never destroy a whole topic set. Enforcement is
deterministic and lives in
``src.flow.engines.content.generation.seo_title_rules``, applied by
``topic_generation`` after parsing -- which is also the only place a title is
ever repaired.
"""

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

TITLE_MIN_CHARS = 50
TITLE_MAX_CHARS = 59


class SEOTopic(BaseModel):
    title: str = Field(
        description=(
            "SEO-optimized article title.\n\n"
            "MANDATORY FOCUS KEYPHRASE REQUIREMENT:\n"
            "- The title MUST contain the user's exact focus keyphrase, word for word, "
            "in the same order, as given in the prompt.\n"
            "- Do NOT substitute a synonym, abbreviation, singular/plural variant, "
            "reordering, or any reworded version of it.\n"
            "- Do NOT invent or choose a different focus keyword.\n"
            "- Place it near the beginning of the title when that reads naturally.\n"
            "- Use it once. Do not repeat it.\n\n"
            "MANDATORY TITLE LENGTH REQUIREMENT:\n"
            f"- The title MUST contain between {TITLE_MIN_CHARS} and {TITLE_MAX_CHARS} "
            "characters inclusive, unless the prompt gives a higher maximum for a long "
            "focus keyphrase, or a range of its own for a Chinese, Japanese, Korean or Thai "
            "title: then the prompt's range applies.\n"
            f"- For a title in Latin or a similar script, {TITLE_MIN_CHARS} characters is the "
            f"minimum and {TITLE_MAX_CHARS} the maximum, or the higher maximum the prompt "
            "gives for a long focus keyphrase.\n"
            "- For a Chinese, Japanese, Korean or Thai title, only the prompt's range "
            "applies.\n"
            "- Count spaces and punctuation as characters.\n"
            "- The title must remain natural and readable while satisfying the "
            "character requirement.\n\n"
            "CONTENT TYPE AND SEARCH INTENT:\n"
            "- The title must read like the specific content type named in the prompt "
            "(comparison, how-to guide, listicle, landing page, etc.) and satisfy the "
            "search intent named in the prompt.\n"
            "- Do not produce a generic title that would fit any content type.\n"
            "- State the SUBJECT explicitly -- what kind of thing the article is about "
            "(agencies, tools, services, courses, templates, ...). The article body is "
            "written to match this subject exactly, so a vague or mismatched subject "
            "produces the wrong article.\n\n"
            "SEO REQUIREMENTS:\n"
            "- Avoid keyword stuffing and unnecessary repetition.\n"
            "- Make the title clear, specific, useful, and compelling.\n"
            "- The title must accurately represent the topic that will be written.\n"
            "- Do not add unsupported facts, statistics, dates, products, companies, "
            "people, rankings, or claims merely to increase title length.\n"
            "- Do not use misleading clickbait.\n"
            "- Avoid unnecessary special characters and excessive punctuation.\n"
            "- Prefer a natural human-readable title over an SEO-stuffed title.\n\n"
            "IMPORTANT:\n"
            "The focus keyphrase and character requirements are strict output "
            "requirements. The application performs a final deterministic validation "
            "after structured output parsing, and any title that still violates them is "
            "repaired or dropped before the user ever sees it -- so this field should "
            "always attempt to satisfy them directly."
        ),
        json_schema_extra={
            "seo_title_rules": {
                "character_length": {
                    "minimum": TITLE_MIN_CHARS,
                    "maximum": TITLE_MAX_CHARS,
                    "inclusive": True,
                    "applies_to": "titles in Latin and similar scripts; Chinese, Japanese, "
                    "Korean and Thai titles take the prompt's range",
                },
                "focus_keyphrase": "exact_verbatim_match_required",
                "primary_keyphrase": "near_beginning_when_natural",
                "keyphrase_frequency": "once",
                "must_match_content_type": True,
                "must_match_search_intent": True,
                "keyword_stuffing": False,
                "unsupported_claims": False,
                "misleading_clickbait": False,
                "natural_readability": True,
            }
        },
    )

    recommended: bool = Field(
        default=False,
        description=(
            "True for exactly ONE topic in the complete set. "
            "This should be the safest and strongest overall topic choice "
            "for the user. All other topics must have recommended=False."
        ),
    )

    recommendation_reason: Optional[str] = Field(
        default=None,
        description=(
            "Only provide this when recommended=True. "
            "Use one short, plain-English sentence explaining why this topic "
            "is the best overall choice. Keep it concise and avoid SEO jargon. "
            "For every non-recommended topic this MUST be null."
        ),
    )

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title_whitespace(cls, value: object) -> object:
        """Whitespace/quote normalization only -- never rejects, never rewrites.

        Deliberately non-raising: length and keyphrase compliance are decided
        by the deterministic layer, which can repair a violation. Raising here
        would turn one bad title into a parse failure for all five.
        """
        if not isinstance(value, str):
            return value
        return " ".join(value.split()).strip("\"'`“”‘’ ").strip()


class SEOTopics(BaseModel):
    topics: List[SEOTopic] = Field(
        description=(
            "Generate exactly 5 article topic options.\n\n"
            "MANDATORY REQUIREMENTS FOR EVERY TOPIC:\n"
            "1. Every title MUST contain the user's exact focus keyphrase, word for "
            "word, in the same order as given in the prompt. Never a synonym, variant "
            "or reworded version, and never a different keyword you chose yourself.\n"
            f"2. Every title MUST be between {TITLE_MIN_CHARS} and {TITLE_MAX_CHARS} "
            "characters inclusive, or up to the higher maximum the prompt gives for a long "
            "focus keyphrase, or within the range the prompt gives for a Chinese, Japanese, "
            "Korean or Thai title.\n"
            "3. Count spaces and punctuation when calculating title length.\n"
            "4. Titles must remain natural and readable while satisfying the length "
            "rule.\n"
            "5. Every title must read like the specific content type named in the "
            "prompt and satisfy the search intent named in the prompt.\n"
            "6. Every title must state the subject explicitly and consistently -- the "
            "article body will be written to match it exactly.\n"
            "7. Place the focus keyphrase near the beginning when natural.\n"
            "8. Avoid keyword stuffing and unnecessary repetition.\n"
            "9. Do not invent facts, statistics, search volume, competition data, "
            "rankings, companies, products, people, dates, or unsupported claims.\n"
            "10. Titles must accurately represent the content that could be written.\n"
            "11. Avoid misleading clickbait and excessive punctuation.\n"
            "12. The 5 titles must be meaningfully different angles, not rewordings of "
            "each other.\n\n"
            "RECOMMENDATION REQUIREMENTS:\n"
            "- Exactly ONE topic must have recommended=True.\n"
            "- All other topics must have recommended=False.\n"
            "- The recommended topic must have a concise recommendation_reason.\n"
            "- All non-recommended topics must have recommendation_reason=null.\n\n"
            "The focus keyphrase and character requirements are strict. The application "
            "performs a separate deterministic validation after structured-output "
            "parsing, so an individual title violation must never be allowed to crash "
            "the complete topic-generation flow."
        ),
        json_schema_extra={
            "topic_generation_rules": {
                "recommended_topic_count": 1,
                "ideal_topic_count": 5,
                "title_character_minimum": TITLE_MIN_CHARS,
                "title_character_maximum": TITLE_MAX_CHARS,
                "title_character_range_applies_to": "Latin and similar scripts; Chinese, "
                "Japanese, Korean and Thai titles take the prompt's range",
                "title_character_count_includes_spaces": True,
                "title_must_contain_exact_focus_keyphrase": True,
                "title_must_match_content_type_and_intent": True,
                "unsupported_facts": False,
                "keyword_stuffing": False,
            }
        },
    )
