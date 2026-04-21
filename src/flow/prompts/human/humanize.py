"""
Human message template for content humanization.
"""

from langchain_core.prompts import ChatPromptTemplate

from src.flow.prompts.system.humanize import HUMANIZE_SYSTEM_PROMPT


def get_humanize_prompt() -> ChatPromptTemplate:
    """
    Returns the chat prompt template used by HumanizeMiddleware.
    """
    return ChatPromptTemplate.from_messages(
        [
            ("system", HUMANIZE_SYSTEM_PROMPT),
            (
                "human",
                """
Must follow system prompt rules.
Rewrite the Title, Introduction and Body (Markdown) based on the system prompt.
Preserve facts, links, and source URLs.

Title: {title}
Introduction: {introduction}
Body (Markdown): {body_markdown}
""",
            ),
        ]
    )
