from fastapi import APIRouter, HTTPException
from src.api.tool.keyword_density.keywords_density_tool import keyword_density_checker
from src.api.tool.keyword_density.keyword_density_schema import (
    KeywordDensityRequest,
    KeywordDensityResponse
)

router = APIRouter(prefix="/keyword-density", tags=["Keyword Density"])

@router.post("/", response_model=KeywordDensityResponse)
def check_keyword_density(request: KeywordDensityRequest):
    try:
        return keyword_density_checker(
            content=request.content,
            keywords=request.keywords
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
