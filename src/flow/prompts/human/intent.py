from langchain_core.prompts import ChatPromptTemplate
from src.flow.prompts.system.intent import SEO_INTENT_SYSTEM_PROMPT

def get_intent_prompt() -> ChatPromptTemplate:
    """
    Prompt for predicting search intent based on keyword and SERP results.
    """
    return ChatPromptTemplate.from_messages(
        [
            ("system", SEO_INTENT_SYSTEM_PROMPT),
            (
                "human",
                """
Keyword: {query}

TOP SERP RESULTS:
{serp_data}

Based on the keyword and the top SERP results above, determine the search intent.
                """,
            ),
        ]
    )
