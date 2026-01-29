from langchain_core.prompts import ChatPromptTemplate
from src.flow.prompts.system.eeat import EEAT_SYSTEM_PROMPT


def get_eeat_prompt() -> ChatPromptTemplate:
    """
    E-E-A-T injection prompt template for enhancing content with
    Experience, Expertise, Authoritativeness, and Trustworthiness signals.
    """
    return ChatPromptTemplate.from_messages(
        [
            ("system", EEAT_SYSTEM_PROMPT),
            (
                "human",
                """
Topic: {topic}
Primary Keyword: {primary_keyword}

Persona Context:
- You are: {persona_name}, {persona_role}
- Experience: {years_experience} years
- Expertise areas: {focus_areas}

CURRENT CONTENT TO ENHANCE:

Title: {title}

Body:
{body_markdown}

---

Enhance this content by injecting E-E-A-T signals naturally throughout.
The persona information should influence HOW you write, not WHAT you claim to be.
                """,
            ),
        ]
    )
