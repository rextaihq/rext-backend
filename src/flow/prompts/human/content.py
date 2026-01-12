from langchain_core.prompts import ChatPromptTemplate
from src.flow.prompts.system.content import CONTENT_SYSTEM_PROMPT


def get_content_prompt() -> ChatPromptTemplate:
    """
    Properly templated content generation prompt
    """
    return ChatPromptTemplate.from_messages(
        [
            ("system", CONTENT_SYSTEM_PROMPT),
            (
                "human",
                """
Topic: {topic}

Approved Outline:
{outline}

Author Persona (E-E-A-T):
{persona}

Reference / Source Content:
{reference_text}

Write the full SEO-optimized article strictly following the outline.
""",
            ),
        ]
    )
