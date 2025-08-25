from typing_extensions import TypedDict, Annotated, Dict, List
from langgraph.graph.message import add_messages
from src.utils.helper import merge_evaluations, merge_contexts
from src.states.schemas import BlogArticle
from langchain_core.documents import Document
import operator
from pydantic import BaseModel

# Configuration for workflow
class URLCONFIF(BaseModel):
    category: str = "Technology"
    language: str = 'en'
    country: str = 'pk'
    WP_URL: Dict[str, str]
    keyword: List[str] = ['Ai', "ML", "DL", "Wordpress", "WordPress Maintenenace"]
    similarity_threshold: float = 0.3


class EvaluationState(TypedDict):
    rating: Annotated[List[int], operator.add]
    weight: Annotated[List[int], operator.add]
    total_rating: List[int]
    total_weight: List[int]


# Main Agent State used by LangGraph
class AgentState(TypedDict, total=False):
    # workflow configration
    config: URLCONFIF

    # Message state for tools calling
    messages: Annotated[list, add_messages]

    # Basic article data
    articles: Annotated[List[Dict], operator.add]
    filter_articles: List[Dict]
    selected_articles: List[Dict]

    # evaluation
    evaluations: Annotated[Dict[str, EvaluationState], merge_evaluations]

    # vector store context
    context: Annotated[List[Document], operator.add]

    # Blog generation states
    blog_context: Annotated[List[Dict], merge_contexts]
    reference_url: List[str]
    current_blog_index: int
    approved_blogs: Annotated[List[dict], operator.add]
    blog_feedback: Annotated[List[str], operator.add]
    generated_blog: Annotated[List[BlogArticle], operator.add] 
    # Human feedback or error
    error: Annotated[List[dict], operator.add]
