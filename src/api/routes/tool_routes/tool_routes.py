from fastapi import  HTTPException, APIRouter
from pydantic import BaseModel, Field
from src.api.tool.tools import count_text_metrics 

# 1. Initialize App and Router

router = APIRouter(prefix='/api', tags=['tools'])

# 2. Define Schemas
class TextInput(BaseModel):
    # Ensures text is not just an empty string at the schema level
    text: str = Field(..., min_length=1)

class TextMetricsOutput(BaseModel):
    words: int
    characters: int
    sentences: int
    paragraphs: int
    min_read: int

# 3. Define Endpoint on the Router
@router.post("/count_metrics", response_model=TextMetricsOutput)
async def get_metrics(input_data: TextInput):
    """
    API endpoint to receive text via POST request and return metrics.
    URL will be: POST /api/count_metrics
    """
    try:
        metrics = count_text_metrics(input_data.text)
        return metrics
    except Exception as e:
        # Generic error handling for the underlying logic
        raise HTTPException(status_code=500, detail=str(e))

# 4. Include the Router in the App

