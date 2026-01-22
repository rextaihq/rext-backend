from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os
load_dotenv()
def get_llm():
    return ChatOpenAI(
        model="gpt-4o-mini", 
        api_key=os.getenv("OPENAI_API_KEY"), 
        temperature=0.7
    )
