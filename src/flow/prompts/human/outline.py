from langchain_core.prompts import ChatPromptTemplate
from src.flow.prompts.system.outline import OUTLINE_GENERATION_PROMPT
from langchain.messages import SystemMessage, HumanMessage

def get_outline_prompt()->ChatPromptTemplate:
    return ChatPromptTemplate.from_messages([
        SystemMessage(content = OUTLINE_GENERATION_PROMPT),
        HumanMessage(content = """
        I need a high-quality SEO outline for the following:

        ### 1. TARGET KEYWORD / TOPIC
        Primary Query: {query}

        ### 2. SERP ANALYSIS & COMPETITION
        - Related Topics: {related_topics}
        - Common Questions (PAA): {questions}
        - Top Competitors Context: {competitors_context}
        - Intent Distribution: {intent_distribution}

        ### 3. ITERATION FEEDBACK (IF ANY)
        - Previous Rejection Reason: {rejected_reason}

        Please generate a complete SEO outline strictly and following the system guidelines.
        """)
    ])