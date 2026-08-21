"""
Human message template for the internal-links repair fallback.
"""

from langchain_core.prompts import ChatPromptTemplate

from src.flow.prompts.system.internal_links_repair import INTERNAL_LINKS_REPAIR_SYSTEM_PROMPT


def get_internal_links_repair_prompt() -> ChatPromptTemplate:
    """Returns the chat prompt template used by HumanizeMiddleware's internal-links repair fallback."""
    return ChatPromptTemplate.from_messages(
        [
            ("system", INTERNAL_LINKS_REPAIR_SYSTEM_PROMPT),
            (
                "human",
                """
Missing links (all MUST appear as inline anchors in body_markdown):
{missing_links}

Title (do NOT change): {title}
Introduction (do NOT change): {introduction}
Body (Markdown): {body_markdown}
""",
            ),
        ]
    )
