from src.states.State import AgentState
from src.utils.embedding import get_hf_embedding
from tqdm import tqdm
from uuid import uuid4
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_community.vectorstores import FAISS
from src.utils.vector_store import add_to_vector_store
from langchain.schema import Document
import os,faiss

def build_vector_store(state: AgentState=None,
    vector_store_path: str="my_faiss_index",
    batch_size: int=32,
    blog_context: list[Document]=(),
):
    if state is not None:
        blog_context = state['context']

    success_state = add_to_vector_store(blog_context=blog_context)
    
    if success_state:
        return state