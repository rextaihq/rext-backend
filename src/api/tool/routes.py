from fastapi import HTTPException, APIRouter
from pydantic import BaseModel, Field
from typing import List

from src.api.tool.tools import count_text_metrics, generate_meta_description, validate_meta_description, generate_title_tags
from src.api.tool.schema import MetaDescriptionRequest, MetaDescriptionResponse, TitleRequest, TitleResponse

router = APIRouter(prefix='/tools', tags=['tools'])

# Define Schemas for Word Counter
class TextInput(BaseModel):
    # Ensures text is not just an empty string at the schema level
    text: str = Field(..., min_length=1)

class TextMetricsOutput(BaseModel):
    words: int
    characters: int
    sentences: int
    paragraphs: int
    min_read: int

# Word Counter Endpoint
@router.post("/count_metrics", response_model=TextMetricsOutput)
async def get_metrics(input_data: TextInput):
    """
    API endpoint to receive text via POST request and return metrics.
    URL will be: POST /tools/count_metrics
    """
    try:
        metrics = count_text_metrics(input_data.text)
        return metrics
    except Exception as e:
        # Generic error handling for the underlying logic
        raise HTTPException(status_code=500, detail=str(e))

# Meta Description Generator Endpoint
@router.post("/meta-description/generate", response_model=MetaDescriptionResponse)
async def generate_meta_desc(request: MetaDescriptionRequest):
    """
    API endpoint to generate meta description.
    URL will be: POST /tools/meta-description/generate
    """
    try:
        # Generate the meta description
        meta_description = generate_meta_description(
            page_title=request.page_title,
            target_keywords=request.target_keywords
        )

        # Validate it
        validation = validate_meta_description(meta_description)

        return MetaDescriptionResponse(
            meta_description=meta_description,
            validation=validation
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate meta description: {str(e)}")

# Title Tag Generator Endpoint
@router.post("/title-tags/generate", response_model=TitleResponse)
async def generate_titles(request: TitleRequest):
    """
    API endpoint to generate SEO-friendly title tags.
    URL will be: POST /tools/title-tags/generate
    """
    try:
        titles = generate_title_tags(
            keyword=request.keyword,
            topic=request.topic,
            brand=request.brand,
            tone=request.tone
        )
        return TitleResponse(titles=titles)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate title tags: {str(e)}")

