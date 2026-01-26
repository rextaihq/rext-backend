from fastapi import APIRouter, HTTPException
from src.api.tool.keyword_rank_checker.keyword_rank_tool import keyword_rank_checker
from src.api.tool.keyword_rank_checker.keyword_rank_schema import (
    KeywordRankRequest,
    KeywordRankResponse
)

router = APIRouter(prefix="/keyword-ranks", tags=["Keyword Rank"])

@router.post("/", response_model=KeywordRankResponse)
async def check_keyword_rank(request: KeywordRankRequest):
    try:
        return await keyword_rank_checker(
            keyword=request.keyword,
            website_url=request.website_url
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))