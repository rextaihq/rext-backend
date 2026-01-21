from fastapi import APIRouter, HTTPException, FastAPI

from src.api.tool.tools import generate_meta_description, validate_meta_description
from src.api.tool.schema import MetaDescriptionRequest, MetaDescriptionResponse

app=  FastAPI()
router = APIRouter(prefix="/tools", tags=["tools"])


@router.post("/meta-description/generate", response_model=MetaDescriptionResponse)
async def generate_meta_desc(request: MetaDescriptionRequest):
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
    
app.include_router(router)