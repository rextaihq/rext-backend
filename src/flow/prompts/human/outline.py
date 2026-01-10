from langchain_core.prompts import ChatPromptTemplate
from src.flow.prompts.system.outline import OUTLINE_GENERATION_PROMPT


def get_outline_prompt() -> ChatPromptTemplate:
    """
    Returns a properly templated ChatPromptTemplate
    (DO NOT use SystemMessage / HumanMessage directly).
    """
    return ChatPromptTemplate.from_messages(
        [
            ("system", OUTLINE_GENERATION_PROMPT),
            (
                "human",
                """
I need a high-quality SEO outline for the following:

### 1. TARGET KEYWORD / TOPIC
Primary Query: {topic}

### 2. SERP ANALYSIS & COMPETITION
- Related Topics: {related_topics}
- Common Questions (PAA):
{questions}

- Top Competitors Context:
{competitors_context}

- Intent Distribution: {intent_distribution}

### 3. ITERATION FEEDBACK (IF ANY)
Previous Rejection Reason: {rejected_reason}

### 4. Previous Outline (IF ANY)
Previous Outline: {previous_outline}

Please generate a complete SEO outline strictly following the system guidelines.
""",
            ),
        ]
    )
