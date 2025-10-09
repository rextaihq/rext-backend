# ContentState: workflow state across nodes
from typing import Any,Annotated
from langchain_core.documents import Document
from typing_extensions import TypedDict
from typing import Optional, List
from src.flow.states.blog_state import BlogArticle
from src.flow.states.payload_state import Payload
import operator

def merge_document_lists(existing: List[Document], new: List[Document]) -> List[Document]:
    """Merges two lists of LangChain Document objects."""
    return existing + new

class ContentState(TypedDict, total=False):
    request_payload: Payload
    topics: List[dict]
    humanReviewers: List[dict]
    context: Annotated[List[Document], merge_document_lists]
    human_review_notes: Optional[str]
    relavant_context: List[Document]
    urls: Annotated[list[str],operator.add]

    # Blog generation states
    reference_url: List[str]
    approved_blogs :list[dict]
    blog_feedback : str
    generated_blog: BlogArticle

    # Human feedback or error
    error: Annotated[List[dict], operator.add]