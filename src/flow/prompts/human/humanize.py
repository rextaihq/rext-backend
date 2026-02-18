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
        ("human", """
Must follow system prompt rules. 
Rewrite the Title, Introduction and Body Based on the system prompt.
Title: {title}
Introduction: {introduction}
Body: {body_markdown}
""")
    ])
