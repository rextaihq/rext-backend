from typing import TypedDict,Dict,List,Annotated
from langgraph.graph.message import add_messages
#  define the evulation creteria
from pydantic import BaseModel, Field
from typing import List

import operator

class AgentState(TypedDict, total=False):
    # Basic article data
    articles: List[Dict]
    wordpress_articles: List[Dict]
    combine_articles: List[Dict]
    selected_articles: List[Dict]

    # Relevance evaluation
    relevance_rating: Annotated[List[int], operator.add]
    relevance_weight: Annotated[List[int], operator.add]

    # Trend evaluation
    trend_rating: Annotated[List[int], operator.add]
    trend_weight: Annotated[List[int], operator.add]

    # Controversy evaluation
    controversy_rating: Annotated[List[int], operator.add]
    controversy_weight: Annotated[List[int], operator.add]

    # Uniqueness evaluation
    uniqueness_rating: Annotated[List[int], operator.add]
    uniqueness_weight: Annotated[List[int], operator.add]

    reader_rating: Annotated[List[int], operator.add]
    reader_weight: Annotated[List[int], operator.add]

    brand_rating: Annotated[List[int], operator.add]
    brand_weight: Annotated[List[int], operator.add]

    actionable_rating: Annotated[List[int], operator.add]
    actionable_weight: Annotated[List[int], operator.add]

    seo_rating: Annotated[List[int], operator.add]
    seo_weight: Annotated[List[int], operator.add]

    total_rating: List[int]
    total_weight: List[int]

    # Human feedback or error
    error: str



class Evaluation(BaseModel):
    # feedback: str = Field(..., description="Detailed feedback of the blog")
    rating: int = Field(..., ge=0, le=10, description="Rating of the blog on a scale of 0 to 10")
    weight: int = Field(..., ge=0, le=10, description="Weight/importance of this criterion (0 to 10)")