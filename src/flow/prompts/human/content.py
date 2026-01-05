from langchain_core.prompts import ChatPromptTemplate
from src.flow.prompts.system.content import CONTENT_SYSTEM_PROMPT
from langchain.messages import SystemMessage, HumanMessage

def get_content_prompt()->ChatPromptTemplate:
    return ChatPromptTemplate.from_messages([
        SystemMessage(content = CONTENT_SYSTEM_PROMPT),
        HumanMessage(content = """
        Topic: {title}
        Outline: {outline}
        Persona: {persona}
        Reference Text: {reference_text}
        """)
    ])