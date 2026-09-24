"""Human message template for targeted quality repair."""

from langchain_core.prompts import ChatPromptTemplate

from src.flow.prompts.system.repair import CONTENT_REPAIR_SYSTEM_PROMPT


def get_repair_prompt() -> ChatPromptTemplate:
    """Returns the chat prompt template used by repair_content."""
    return ChatPromptTemplate.from_messages(
        [
            ("system", CONTENT_REPAIR_SYSTEM_PROMPT),
            (
                "human",
                """
ARTICLE STAGE: {article_stage}

ISSUES TO FIX:
{issues_block}
{sources_block}{preservation_block}
Title (READ-ONLY — return verbatim): {title}
Meta description: {meta_description}
Introduction: {introduction}
Body (Markdown): {body_markdown}
""",
            ),
        ]
    )
