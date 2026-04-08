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

Brand Context & Offerings:
{brand_context}

CURRENT CONTENT TO ENHANCE:

Title: {title}

Body:
{body_markdown}

---

Enhance this content by:
1. Injecting natural E-E-A-T signals based on the persona.
2. DISCRETELY injecting promotions for the person or their service/brand where it fits naturally.
3. Ensuring the brand's unique selling position is reflected.
                """,
            ),
        ]
    )
