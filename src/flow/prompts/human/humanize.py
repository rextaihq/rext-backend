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
            # The article's voice closes the system message, so it outranks the
            # general style rules there rather than sitting under them.
            ("system", HUMANIZE_SYSTEM_PROMPT + "{voice_instruction}"),
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
{reader_instruction}
{brand_instruction}
{keyword_instruction}
{length_instruction}

Title (do NOT change): {title}
Introduction: {introduction}
Body (Markdown): {body_markdown}
""",
            ),
        ]
    )


def get_section_rewrite_prompt() -> ChatPromptTemplate:
    """
    Returns the chat prompt template for rewriting one part of an article (section_rewrite.py):
    the same standing instructions as the whole-article rewrite, and a message about one part.
    """
    return ChatPromptTemplate.from_messages(
        [
            ("system", HUMANIZE_SYSTEM_PROMPT + "{voice_instruction}"),
            (
                "human",
                """
Rewrite ONE part of an article, as the system prompt says. You are given only this part; the
others are rewritten separately, in the same voice. Return this part's text and nothing else:
no title, no meta description, no other field.
{brief}

THE ARTICLE: "{title}"
ITS SECTIONS, IN ORDER (so you know what the others cover; write only yours):
{sections}

YOU ARE REWRITING: {which}

REWRITE THE WORDS, KEEP THE SUBSTANCE. You may rephrase every sentence, change the voice and
vary the rhythm freely. Keep:
- Every heading line (## and ###) exactly as written, in the same order. Add none.
- Every markdown link exactly as written: [anchor](url). You may reword the anchor text to
  fit the new sentence, but never change or drop the URL, and never leave a link on a line of
  its own.
- Every markdown image embed: ![alt](url), unchanged, where it stands.
- Every statistic, figure, date, percentage, price and named source. Never alter one, drop one
  or invent one.
- Lists stay lists and numbered steps stay numbered steps, with the same items in their order.
- This is a part of a longer article. No new introduction to the article, no summary of it and
  no sign-off of its own. At most one illustrative example, and only in place of a generic
  sentence.
{brand_instruction}
{keyword_instruction}
LENGTH: this part has {words} words. Return between {low} and {high} words, counted before you
answer. A sentence you add takes the place of one you remove.

Return only this part's markdown, nothing before it and nothing after it.

{text}
""",
            ),
        ]
    )
