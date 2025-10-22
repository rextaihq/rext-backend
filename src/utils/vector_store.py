from langchain_community.vectorstores import FAISS
from  src.utils.embedding import get_hf_embedding
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_core.documents import Document
from src.utils.logger import logger
from uuid import uuid4
from tqdm import tqdm
import os, faiss
import yaml

def load_yaml(file_path: str = "config/config.yaml") -> dict:
    """
    Load a YAML config file and return it as a Python dict.
    Resolves the path relative to the project root.do not use relative paths.
    :param file_path: Path to the YAML config file.
    :return: Dictionary containing the YAML file contents.
    """
     # go up two levels: src/utils -> src -> project_root
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    abs_path = os.path.join(project_root, file_path)

    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"YAML config file not found at: {abs_path}")

    with open(abs_path, "r") as f:
        content = yaml.safe_load(f) or {}
        logger.info("✅ Loaded config:", content)
        return content



def add_to_vector_store(
    batch_size: int=32,
    blog_context: list[Document]=(),
    workspace_id:str=None
)->bool:
    if blog_context is None:
        raise "Document should not be none"

    if workspace_id is None:
        raise "Doc id should not be none"
    # Determine embedding dimension
    test_embedding = get_hf_embedding().embed_query("hello world")
    dimension = len(test_embedding)

    config = load_yaml()

    vector_store_path= config["vectorStore"]["store_path"]
    index_file_path = os.path.join(vector_store_path, "index.faiss")
    
    # Check if the index file exists, not just the directory
    if os.path.exists(index_file_path):
        logger.info(">> Loading existing FAISS index <<")
        vector_store = FAISS.load_local(
            vector_store_path,
            get_hf_embedding(),
            allow_dangerous_deserialization=True
        )
    else:
        logger.info(">> Creating new FAISS index <<")
        # Ensure the directory exists
        os.makedirs(vector_store_path, exist_ok=True)
        index = faiss.IndexFlatL2(dimension)
        vector_store = FAISS(
            embedding_function=get_hf_embedding(),
            index=index,
            docstore=InMemoryDocstore(),
            index_to_docstore_id={},
        )

    # Attach id to metadata
    documents_with_metadata = [
            Document(
                page_content=doc.page_content,
                metadata={**doc.metadata, "workspace_id": workspace_id} 
            )
            for doc in blog_context
    ]

    # Convert blog_context into LangChain Document objects
    uuids = [str(uuid4()) for _ in documents_with_metadata]

    logger.info(f"\n📦 Preparing to insert {len(documents_with_metadata)} documents into FAISS...\n")

    for i in tqdm(range(0, len(documents_with_metadata), batch_size), desc="🔍 Embedding & Inserting", unit="batch"):
        try:
            batch_docs = documents_with_metadata[i:i+batch_size]
            batch_ids = uuids[i:i+batch_size]
            vector_store.add_documents(documents=batch_docs, ids=batch_ids)
        except Exception as e:
            logger.info(f"⚠️ Error during batch insertion: {str(e)}")
            return False

    logger.info("✅ Documents successfully inserted into FAISS")

    # Save index
    vector_store.save_local(vector_store_path)
    logger.info(f"💾 Vector store saved at {vector_store_path}")
    return True

def load_vector_store(file_path: str = 'vector_store'):
    """
    Load a FAISS vector store from a local file.

    Args:
        file_path (str, optional): Path to the saved FAISS index directory.
                                   Defaults to 'my_faiss_index'.

    Returns:
        FAISS: A loaded FAISS vector store with embeddings.
    """
    vector_store = FAISS.load_local(
        file_path, get_hf_embedding(), allow_dangerous_deserialization=True
    )
    return vector_store

def delete_vectors(vector_id: str):
    """
    Delete all documents/vectors in the FAISS store whose metadata.workspace_id == workspace_id
    """
    vector_store = load_vector_store()
    # get all existing doc IDs in vector_store.docstore
    ids_to_delete = []
    for doc_id, doc in vector_store.docstore.dict.items():
        # assuming metadata has "workspace_id"
        if doc.metadata.get("workspace_id") == vector_id:
            ids_to_delete.append(doc_id)

    if not ids_to_delete:
        logger.info(f"No vectors found for workspace {vector_id}")
        return False
    # Delete those ids
    logger.info(f"delete vector store ids: {ids_to_delete}")
    result = vector_store.delete(ids=ids_to_delete)
    # result is True/False/None depending on success
    if result:
        logger.info(f"Ids delete successfully: {result}")
        return result
    else:
        logger.error(f"Ids not delete: {result}")
        return result