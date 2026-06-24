from typing import List

from pydantic import BaseModel, Field


class SEOTopic(BaseModel):
    title: str = Field(
        description=(
            "SEO-optimized article title. These are guidelines, not hard constraints:\n"
            "(1) CHARACTER LENGTH: Ideally 50–60 characters for optimal SERP display; "
            "aim to stay within 60 characters when possible.\n"
            "(2) WORD COUNT: Preferably 10 words or fewer.\n"
            "(3) KEYPHRASE PLACEMENT: Ideally place the focus keyphrase near the beginning; "
            "avoid leading with stop words (The / A / An / This / Your / Our) when possible.\n"
            "(4) KEYPHRASE FREQUENCY: Use the focus keyphrase once if possible; avoid repetition.\n"
            "(5) ACCURACY: Title should truthfully represent the article content.\n"
            "(6) CHARACTERS: Prefer simple characters; avoid excessive special characters."
        )
    )
    focus_keyphrase: str = Field(
        description=(
            "The primary keyphrase from the user query that this title targets. "
            "Preferably the exact query term or its closest natural language variant."
        )
    )
    secondary_keyword: str = Field(
        description=(
            "The secondary keyword angle this title targets. "
            "Ideally different from other topics in the set to cover distinct semantic variations."
        )
    )
    structural_formula: str = Field(
        description=(
            "The title structural pattern used. Examples: "
            "'How to [X] in {year}', 'Best [X] for [Audience]', '[X] vs [Y]: {year} Comparison', "
            "'[X]: Complete {year} Guide', 'What Is [X]? {year} Overview'. "
            "Prefer a different formula from other topics in the set."
        )
    )
    targets_featured_snippet: bool = Field(
        description=(
            "True if this title is question-based (What / How / Why / Which / Is / Can) "
            "and is positioned to win Google's People Also Ask box or featured snippet position. "
            "At least one topic in the set should ideally have this set to True."
        )
    )


class SEOTopics(BaseModel):
    topics: List[SEOTopic] = Field(
        description=(
            "A list of SEO-optimized article topics, ideally 5. Recommendations for the full set:\n"
            "(1) Prefer a different structural_formula for each topic.\n"
            "(2) Prefer a different secondary_keyword for each topic.\n"
            "(3) At least one topic should have targets_featured_snippet=True "
            "for PAA / featured snippet targeting.\n"
            "(4) Each title should follow the SEOTopic field guidelines."
        )
    )
