"""
Human message template for the brand-mention repair fallback.
"""

from langchain_core.prompts import ChatPromptTemplate

from src.flow.prompts.system.brand_repair import BRAND_REPAIR_SYSTEM_PROMPT


def get_brand_repair_prompt() -> ChatPromptTemplate:
    """Returns the chat prompt template used by HumanizeMiddleware's repair fallback."""
    return ChatPromptTemplate.from_messages(
        [
            ("system", BRAND_REPAIR_SYSTEM_PROMPT),
            (
                "human",
                """
Brand: {brand_name}
{about_line}{selling_position_line}{url_line}

Title (do NOT change): {title}
Introduction: {introduction}
Body (Markdown): {body_markdown}
""",
            ),
        ]
    )
