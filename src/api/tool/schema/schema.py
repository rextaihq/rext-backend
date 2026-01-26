from pydantic import BaseModel, Field 
from typing import List,Optional 

class MetaDescriptionRequest(BaseModel):
     text: str 
     
class MetaDescriptionResponse(BaseModel):
     text: str 
    
class QuestionRequest(BaseModel):
    text:str 
    
class QuestionResponse(BaseModel):
    questions: List[str]
    
    
class TagLineRequest(BaseModel):
    brand: str = Field(..., description="Brand name")
    topic: str = Field(..., description="Product or topic")
    tone: Optional[str] = Field("professional", description="Tone of the tagline")
    count: Optional[int] = Field(5, ge=1, le=10, description="Number of taglines")
    
    
class TagLineResponse(BaseModel):
    taglines: List[str]
    
    