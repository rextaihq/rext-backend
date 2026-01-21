from langchain_openai import ChatOpenAI

def get_llm():
    return ChatOpenAI(
        model="gpt-4o-mini", 
        api_key="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", 
        temperature=0.7
       
    )
