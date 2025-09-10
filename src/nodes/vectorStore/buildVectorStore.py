from src.states.State import AgentState
from src.utils.helper import get_hf_embedding
from tqdm import tqdm
from uuid import uuid4
import os, faiss
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_community.vectorstores import FAISS
from langchain.schema import Document

def build_vector_store(state: AgentState=None,
    vector_store_path: str="my_faiss_index",
    batch_size: int=32,
    blog_context: list[Document]=[]
):
    
    if state is not None:
        blog_context = state['context']

    # Determine embedding dimension
    test_embedding = get_hf_embedding().embed_query("hello world")
    dimension = len(test_embedding)


    if os.path.exists(vector_store_path):
        print(">> Loading existing FAISS index <<")
        vector_store = FAISS.load_local(
            vector_store_path,
            get_hf_embedding(),
            allow_dangerous_deserialization=True
        )
    else:
        print(">> Creating new FAISS index <<")
        index = faiss.IndexFlatL2(dimension)
        vector_store = FAISS(
            embedding_function=get_hf_embedding(),
            index=index,
            docstore=InMemoryDocstore(),
            index_to_docstore_id={},
        )

    # Convert blog_context into LangChain Document objects
    uuids = [str(uuid4()) for _ in blog_context]

    print(f"\n📦 Preparing to insert {len(blog_context)} documents into FAISS...\n")

    for i in tqdm(range(0, len(blog_context), batch_size), desc="🔍 Embedding & Inserting", unit="batch"):
        try:
            batch_docs = blog_context[i:i+batch_size]
            batch_ids = uuids[i:i+batch_size]
            vector_store.add_documents(documents=batch_docs, ids=batch_ids)
        except Exception as e:
            print(f"⚠️ Error during batch insertion: {str(e)}")

    print("✅ Documents successfully inserted into FAISS")

    # Save index
    vector_store.save_local(vector_store_path)
    print(f"💾 Vector store saved at {vector_store_path}")

    return state