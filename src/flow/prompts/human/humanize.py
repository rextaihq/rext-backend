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
Rewrite the Introduction and Body (Markdown) based on the system prompt. Return the Title unchanged.

REWRITE THE WORDS, KEEP THE SUBSTANCE. You may rephrase every sentence, change the
voice, reorder paragraphs within a section and vary the rhythm freely. You may NOT
remove any of the following — carry each one through into your rewrite:
- Every markdown link exactly as written: [anchor](url). You may reword the anchor
  text to fit the new sentence, but never change or drop the URL, and never leave a
  link stranded on its own line — weave it into a sentence.
- Every markdown image embed: ![alt](url). Keep the URL unchanged and keep it in the
  same section it appears in now.
- Every statistic, figure, date, percentage, price and named source. Reword the
  sentence around a number if you like; never alter the number itself, never drop it,
  and never invent a new one.
- Every section and its heading. Do not merge two sections into one, do not delete a
  section, and do not reorder them.
{brand_instruction}
{length_instruction}

Title (do NOT change): {title}
Introduction: {introduction}
Body (Markdown): {body_markdown}
""",
            ),
        ]
    )
