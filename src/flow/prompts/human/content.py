from langchain_core.prompts import ChatPromptTemplate
from src.flow.prompts.system.content import CONTENT_SYSTEM_PROMPT


def get_content_prompt() -> ChatPromptTemplate:
    """
    Properly templated content generation prompt with E-E-A-T persona data.
    """
    return ChatPromptTemplate.from_messages(
        [
            ("system", CONTENT_SYSTEM_PROMPT),
            (
                "human",
                """
Topic: {topic}

Primary Keyword: {primary_keyword}
Target Word Count: {target_word_count} words (minimum)

Write as: {persona_name}, {persona_role} with {years_experience} years of experience
Expertise areas: {focus_areas}

COMPETITIVE LANDSCAPE:
{competitor_insights}
- Go deeper than these competitors
- Cover gaps they missed
- Offer a unique angle/perspective

Approved Outline:
{outline}

Reference / Source Content:
{reference_text}

Generate complete SEO-optimized content with E-E-A-T signals built-in.
Include your experience and expertise naturally throughout the content.
Ensure you outperform the competitors listed above.
                """,
            ),
        ]
    )
