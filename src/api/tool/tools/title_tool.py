# Change the import path if you moved get_llm to avoid the streamlit error
from src.api.tool.llm.ollama_llm import get_llm 
from src.api.tool.prompts.title_prompt import title_prompt

llm = get_llm()

def generate_title_tags(keyword: str, topic: str, brand: str, tone: str):
    """
    Generate 5 SEO-friendly title tags and return them as a clean list.
    """
    prompt = title_prompt.format(
        keyword=keyword,
        topic=topic,
        brand=brand,
        tone=tone
    )
    
    # 1. Get the response from the LLM
    response = llm.invoke(prompt)
    
    raw_content = response.content if hasattr(response, 'content') else str(response)
    titles_list = [
        line.strip("- ").strip() 
        for line in raw_content.split("\n") 
        if line.strip()
    ]
    
    return titles_list[:5]
