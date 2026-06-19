from pydantic import BaseModel, Field, field_validator, conlist


class SEOTopic(BaseModel):
    title: str = Field(
        description=(
            "SEO-optimized article title. ALL constraints are strict and enforced by the validator:\n"
            "(1) CHARACTER LENGTH: 50–60 characters — this is the SERP meta_title display window; "
            "count every character including spaces before returning; never exceed 60.\n"
            "(2) WORD COUNT: ≤10 words — hard cap.\n"
            "(3) KEYPHRASE FIRST: focus keyphrase must appear at the very beginning — "
            "never start with stop words (The / A / An / This / Your / Our).\n"
            "(4) KEYPHRASE ONCE: the focus keyphrase appears exactly once — no repetition.\n"
            "(5) NO CLICKBAIT: every title must truthfully represent the article content.\n"
            "(6) SLUG-SAFE: no special characters beyond hyphens, colons, and question marks."
        )
    )
    focus_keyphrase: str = Field(
        description=(
            "The primary keyphrase extracted from the user query that leads this title. "
            "Must be the exact query term or its closest natural language variant."
        )
    )
    secondary_keyword: str = Field(
        description=(
            "The secondary keyword angle this title uniquely targets. "
            "Must be different from the secondary_keyword of every other topic in this set — "
            "each topic covers a distinct semantic variation of the main query."
        )
    )
    structural_formula: str = Field(
        description=(
            "The title structural pattern used. Examples: "
            "'How to [X] in {year}', 'Best [X] for [Audience]', '[X] vs [Y]: {year} Comparison', "
            "'[X]: Complete {year} Guide', 'What Is [X]? {year} Overview'. "
            "Must be different from every other topic's structural_formula in this set."
        )
    )
    targets_featured_snippet: bool = Field(
        description=(
            "True if this title is question-based (What / How / Why / Which / Is / Can) "
            "and is positioned to win Google's People Also Ask box or featured snippet position. "
            "At least one topic in every set of 5 must have this set to True."
        )
    )

    @field_validator("title")
    @classmethod
    def enforce_title_seo_constraints(cls, v: str) -> str:
        v = v.strip()
        char_count = len(v)
        word_count = len(v.split())
        violations = []

        if char_count < 20:
            violations.append(f"too short ({char_count} chars — minimum 20)")
        if char_count > 60:
            violations.append(f"too long ({char_count} chars — maximum 60, Google truncates beyond this)")
        if word_count > 10:
            violations.append(f"too many words ({word_count} — maximum 10)")

        _STOP_WORD_STARTS = {"the ", "a ", "an ", "this ", "your ", "our ", "my "}
        if any(v.lower().startswith(sw) for sw in _STOP_WORD_STARTS):
            violations.append("starts with a stop word — focus keyphrase must come first")

        if violations:
            raise ValueError(
                f"Title SEO constraint violation(s): {'; '.join(violations)}. "
                f"Received: '{v}' ({char_count} chars, {word_count} words)."
            )
        return v


class SEOTopics(BaseModel):
    topics: conlist(SEOTopic, min_length=5, max_length=5) = Field(
        description=(
            "Exactly 5 SEO-optimized article topics. Rules for the full set:\n"
            "(1) Every topic must use a different structural_formula.\n"
            "(2) Every topic must target a different secondary_keyword.\n"
            "(3) At least one topic must have targets_featured_snippet=True "
            "(question-based title for PAA / featured snippet targeting).\n"
            "(4) Every title must pass the SEOTopic.title validator constraints."
        )
    )
