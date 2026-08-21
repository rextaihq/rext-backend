"""
Human message template for the persona-mention repair fallback.
"""

from langchain_core.prompts import ChatPromptTemplate

from src.flow.prompts.system.persona_repair import PERSONA_REPAIR_SYSTEM_PROMPT


def get_persona_repair_prompt() -> ChatPromptTemplate:
    """Returns the chat prompt template used by HumanizeMiddleware's persona-repair fallback."""
    return ChatPromptTemplate.from_messages(
        [
            ("system", PERSONA_REPAIR_SYSTEM_PROMPT),
            (
                "human",
                """
Author: {persona_name}

Title (do NOT change): {title}
Introduction: {introduction}
Body (Markdown): {body_markdown}
""",
            ),
        ]
    )
