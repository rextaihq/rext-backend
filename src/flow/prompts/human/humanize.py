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
        - persona_full_name: Author's full name
        - persona_professional_title: Author's professional title
        - persona_areas_of_expertise: Author's areas of expertise
        - persona_bio: Author's biography
        - persona_tone_of_voice: Author's specific tone
        - persona_description: General description of the persona
        - persona_goals: Author's goals for writing
        - persona_behaviors: Author's writing behaviors/style
    
    Returns:
        ChatPromptTemplate configured for humanization (90% human-written target)
    """ 
    return ChatPromptTemplate.from_messages([
        ("system", HUMANIZE_SYSTEM_PROMPT),
        ("human", """
Must follow system prompt rules. 
Rewrite the Title, Introduction, Body (Markdown), and HTML_Content based on the system prompt.
Title: {title}
Introduction: {introduction}
Body (Markdown): {body_markdown}
HTML_Content: {html_content}

""")
    ])
