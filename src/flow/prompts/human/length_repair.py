"""
Human message template for the length-correction repair fallback.
"""

from langchain_core.prompts import ChatPromptTemplate

from src.flow.prompts.system.length_repair import LENGTH_REPAIR_SYSTEM_PROMPT


def get_length_repair_prompt() -> ChatPromptTemplate:
    """Returns the chat prompt template used by HumanizeMiddleware's length-repair fallback."""
    return ChatPromptTemplate.from_messages(
        [
            ("system", LENGTH_REPAIR_SYSTEM_PROMPT),
            (
                "human",
                """
Current combined length (introduction + body_markdown): {current_words} words.
Target range: {target_min}-{target_max} words.
{direction_instruction}

Title (do NOT change): {title}
Introduction: {introduction}
Body (Markdown): {body_markdown}
""",
            ),
        ]
    )
