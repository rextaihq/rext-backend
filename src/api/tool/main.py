from fastapi import FastAPI
from dotenv import load_dotenv
from src.api.tool.schemas.title_schema import TitleRequest
from src.api.tool.tools.title_tool import generate_title_tags
import os

# # Load LangSmith API key
load_dotenv()

app = FastAPI(
    title="Title Tag Generator API",
    description="Generates SEO-friendly title tags using LangChain LLM",
    version="1.0"
)

@app.post("/generate-title-tags")
def generate_titles(data: TitleRequest):
    """
    Call the Title Tag Generator Tool directly (no agent).
    """
    titles = generate_title_tags(
        keyword=data.keyword,
        topic=data.topic,
        brand=data.brand,
        tone=data.tone
    )
    return {"titles": titles}
