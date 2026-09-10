from langchain_core.prompts import ChatPromptTemplate

from src.flow.prompts.system.content import CONTENT_SYSTEM_PROMPT


def get_content_prompt() -> ChatPromptTemplate:
    """
    Content generation prompt focused on pure content creation.
    E-E-A-T persona injection is handled by a separate node.
    """
    return ChatPromptTemplate.from_messages(
        [
            ("system", CONTENT_SYSTEM_PROMPT),
            (
                "human",
                """
Content Type: {content_type}
Topic: {topic}

Primary Keyword: {primary_keyword}
Target Word Count: {target_word_count} words (minimum)

COMPETITIVE LANDSCAPE:
{competitor_insights}
- Go deeper than these competitors
- Cover gaps they missed
- Offer a unique angle/perspective

Approved Outline:
{outline}

Reference / Source Content:
{reference_text}

Meta_data:
{meta_data}

Tone: 
{tone}

Generate complete SEO-optimized content following the outline.
Ensure you incorporate all facts and statistics mentioned in the outline.
Populate the 'facts' field in the output JSON with objects containing 'text' and 'source_url' for each key verifiable fact or statistic you included in the content. For 'source_url', use the one from the outline or find a direct link to the data source.
Ensure you outperform the competitors listed above.
                """,
            ),
        ]
    )
