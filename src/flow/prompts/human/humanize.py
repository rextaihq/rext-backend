"""
Humanization Human Message Template

This module provides the human message template for content humanization.
It formats content for the LLM to transform into naturally human-written text.
"""

from langchain_core.prompts import ChatPromptTemplate
from src.flow.prompts.system.humanize import HUMANIZE_SYSTEM_PROMPT


def get_humanize_prompt() -> ChatPromptTemplate:
    """
    Returns a ChatPromptTemplate for content humanization.
    
    Template variables:
        - title: Content title to humanize
        - body_markdown: Content body in markdown format
    
    Returns:
        ChatPromptTemplate configured for humanization (90% human-written target)
    """
    return ChatPromptTemplate.from_messages([
        ("system", HUMANIZE_SYSTEM_PROMPT),
        ("human", """**Your Task**: Completely rewrite the following content to make it sound like it was written by a real person with personality, not AI. The content should feel natural, conversational, engaging, and authentic.

**Original Content:**
Title: {title}

{body_markdown}

**Output Instructions:**
- Rewrite to sound VERY naturally human with strong personality
- Target: 90% human-written detection score (10% AI)
- Keep all factual information intact
- Maintain markdown formatting
- Make it highly engaging, conversational, and authentic
- Break formal writing rules when it sounds more natural
- Add personality and unique voice throughout
""")
    ])
