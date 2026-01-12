"""
E-E-A-T Human Message Template

This module provides the human message template for E-E-A-T content enhancement.
It formats persona information and content for the LLM to inject E-E-A-T signals.
"""

from langchain_core.prompts import ChatPromptTemplate
from src.flow.prompts.system.eeat import EEAT_SYSTEM_PROMPT


def get_eeat_prompt() -> ChatPromptTemplate:
    """
    Returns a ChatPromptTemplate for E-E-A-T content enhancement.
    
    Template variables:
        - persona_name: Name of the persona (e.g., "Arsalan Khan")
        - persona_role: Professional role (e.g., "Technical SEO & AI Content Systems Consultant")
        - years_experience: Years of experience (e.g., 7)
        - focus_areas: Comma-separated areas of expertise
        - worked_with: Comma-separated types of clients/projects
        - writing_style: Description of writing style (e.g., "practical, experience-driven, no-fluff")
        - language_patterns: Comma-separated experience language patterns
        - tone: Authoritativeness tone (e.g., "confident")
        - title: Content title to enhance
        - body_markdown: Content body in markdown format
    
    Returns:
        ChatPromptTemplate configured for E-E-A-T enhancement
    """
    return ChatPromptTemplate.from_messages([
        ("system", EEAT_SYSTEM_PROMPT),
        ("human", """You are {persona_name}, a {persona_role} with {years_experience} years of experience.

Your expertise includes: {focus_areas}
You've worked with: {worked_with}
Your writing style is: {writing_style}

**E-E-A-T Guidelines:**
- **Experience**: Use language patterns like "{language_patterns}"
- **Expertise**: Explain tradeoffs, avoid generic advice, be decision-driven
- **Authoritativeness**: Maintain a {tone} tone with consistent terminology
- **Trustworthiness**: State limitations, avoid exaggerated claims, ensure factual accuracy

**Task**: Enhance the following content by injecting E-E-A-T signals naturally. Don't change the core structure or information, but add:
- Personal experience references where appropriate
- Practical insights from real-world projects
- Specific tradeoffs and decision-making guidance
- Confident but honest language
- Limitations or caveats where relevant

**Original Content:**
Title: {title}

{body_markdown}

**Instructions:**
- Keep the same markdown structure
- Maintain the original title
- Enhance with E-E-A-T signals naturally throughout
- Don't add unnecessary fluff
- Keep the word count similar (±10%)
""")
    ])
