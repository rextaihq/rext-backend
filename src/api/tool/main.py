from fastapi import FastAPI
from dotenv import load_dotenv
from src.app.tool.schemas.title_schema import TitleRequest
from src.app.tool.tools.title_tool import generate_title_tags

# Load LangSmith API key
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
