from langchain_community.vectorstores import FAISS
from  src.utils.embedding import get_embedding
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_core.documents import Document
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from src.utils.logger import logger
from uuid import uuid4
from tqdm import tqdm
import os, faiss
import yaml

def load_yaml(file_path: str = "config/config.yaml") -> dict:
    """
    Load a YAML configuration file and return it as a Python dictionary.

    Resolves the path relative to the project root to support consistent
    configuration access across different execution contexts.

    Args:
        file_path: Relative path to the YAML config file from project root
                  Default: "config/config.yaml"

    Returns:
        Dictionary containing the parsed YAML file contents

    Raises:
        FileNotFoundError: If the config file doesn't exist at the specified path
        yaml.YAMLError: If the file contains invalid YAML syntax

    Example:
        >>> config = load_yaml("config/config.yaml")
        >>> vector_store_path = config["vectorStore"]["store_path"]
    """
    # Resolve path: src/utils -> src -> project_root
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    abs_path = os.path.join(project_root, file_path)

    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"YAML config file not found at: {abs_path}")

    with open(abs_path, "r") as f:
        content = yaml.safe_load(f) or {}
        logger.info("Loaded config from", path=abs_path)
        return content



def add_to_vector_store(
    batch_size: int = 32,
    blog_context: list[Document] = (),
    workspace_id: str = None,
    knowledge_id: str = None,
    knowledge_type: str = None,
    knowledge_base_id: str = None
) -> bool:
    """
    Add documents to FAISS vector store with workspace and knowledge-level isolation.

    Following LangChain v1.0 best practices (Released Oct 2025):
    - Uses proper Document objects with metadata
    - Implements batch processing for efficiency
    - Multi-level isolation (workspace + knowledge item)
    - UUID-based document IDs for uniqueness
    - RecursiveCharacterTextSplitter for semantic chunking
    - BAAI/bge-small-en embeddings for retrieval quality

    Args:
        batch_size: Number of documents to process per batch (default: 32)
                   Batch size balances memory usage vs. processing speed
        blog_context: List of LangChain Document objects to add
                     Each Document must have page_content and metadata
        workspace_id: Workspace identifier for multi-tenant isolation
                     Used in metadata filtering for workspace-specific queries
        knowledge_id: Optional knowledge item ID (file_id, text_id, web_id)
                     Enables granular deletion of specific knowledge items
        knowledge_type: Optional knowledge type ("file", "text", "web")
                       Helps with filtering and debugging
        knowledge_base_id: Optional knowledge base ID
                          Enables filtering by specific knowledge base
                          Supports multiple KBs per workspace

    Returns:
        bool: True if successful, False otherwise

    Raises:
        ValueError: If blog_context is None/empty or workspace_id is None
        Exception: If batch insertion fails during processing

    Example:
        >>> from langchain_core.documents import Document
        >>> docs = [Document(page_content="Sample text", metadata={"source": "file.txt"})]
        >>> result = add_to_vector_store(
        ...     blog_context=docs,
        ...     workspace_id="workspace-123",
        ...     knowledge_id="file-456",
        ...     knowledge_type="file"
        ... )
        >>> print(result)
        True
    """
    if blog_context is None or len(blog_context) == 0:
        raise ValueError("blog_context should not be None or empty")

    if workspace_id is None:
        raise ValueError("workspace_id should not be None")
    # Determine embedding dimension
    test_embedding = get_embedding().embed_query("hello world")
    dimension = len(test_embedding)

    config = load_yaml()

    vector_store_path= config["vectorStore"]["store_path"]
    index_file_path = os.path.join(vector_store_path, "index.faiss")
    
    # Check if the index file exists, not just the directory
    if os.path.exists(index_file_path):
        logger.info(">> Loading existing FAISS index <<")
        vector_store = FAISS.load_local(
            vector_store_path,
            get_embedding(),
            allow_dangerous_deserialization=True
        )
    else:
        logger.info(">> Creating new FAISS index <<")
        # Ensure the directory exists
        os.makedirs(vector_store_path, exist_ok=True)
        index = faiss.IndexFlatL2(dimension)
        vector_store = FAISS(
            embedding_function=get_embedding(),
            index=index,
            docstore=InMemoryDocstore(),
            index_to_docstore_id={},
        )

    # Attach workspace and knowledge identifiers to metadata
    # This enables multi-level filtering: workspace → KB → knowledge item
    enhanced_metadata = {"workspace_id": workspace_id}
    if knowledge_base_id:
        enhanced_metadata["knowledge_base_id"] = knowledge_base_id
    if knowledge_id:
        enhanced_metadata["knowledge_id"] = knowledge_id
    if knowledge_type:
        enhanced_metadata["knowledge_type"] = knowledge_type

    documents_with_metadata = [
            Document(
                page_content=doc.page_content,
                metadata={**doc.metadata, **enhanced_metadata}
            )
            for doc in blog_context
    ]

    # Convert blog_context into LangChain Document objects
    uuids = [str(uuid4()) for _ in documents_with_metadata]

    logger.info(f"\n📦 Preparing to insert {len(documents_with_metadata)} documents into FAISS...\n")

    for i in tqdm(range(0, len(documents_with_metadata), batch_size), desc="Embedding & Inserting", unit="batch"):
        try:
            batch_docs = documents_with_metadata[i:i+batch_size]
            batch_ids = uuids[i:i+batch_size]
            _add_batch_with_retry(vector_store, batch_docs, batch_ids)
        except Exception as e:
            logger.error(f"Error during batch insertion after retries: {str(e)}", exc_info=True)
            return False

    logger.info("✅ Documents successfully inserted into FAISS")

    # Save index
    vector_store.save_local(vector_store_path)
    logger.info(f"💾 Vector store saved at {vector_store_path}")
    return True

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(Exception),
    before_sleep=lambda retry_state: logger.warning(
        f"Retrying embedding batch (attempt {retry_state.attempt_number})"
    ),
)
def _add_batch_with_retry(vector_store, batch_docs, batch_ids):
    """Add a batch of documents to the vector store with retry on failure."""
    vector_store.add_documents(documents=batch_docs, ids=batch_ids)

def load_vector_store(file_path: str = None) -> FAISS:
    """
    Load a FAISS vector store from local storage.

    Following LangChain v1.0 best practices for FAISS persistence.
    Loads both the index and docstore for full vector store functionality.

    Args:
        file_path: Path to the saved FAISS index directory
                  If None, uses path from config/config.yaml
                  Default: None

    Returns:
        FAISS: Loaded FAISS vector store with embeddings and docstore

    Raises:
        FileNotFoundError: If the vector store directory doesn't exist
        Exception: If loading fails due to corrupted index

    Example:
        >>> vector_store = load_vector_store()
        >>> results = vector_store.similarity_search("query text", k=5)

    Note:
        Uses allow_dangerous_deserialization=True as the vector store
        is managed internally. For production, ensure proper access controls.
    """
    if file_path is None:
        config = load_yaml()
        file_path = config["vectorStore"]["store_path"]

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Vector store not found at: {file_path}")

    vector_store = FAISS.load_local(
        file_path,
        get_embedding(),
        allow_dangerous_deserialization=True
    )
    return vector_store

def search_vector_store(
    query: str,
    workspace_id: str,
    knowledge_base_id: str = None,
    k: int = 10,
    score_threshold: float = None,
) -> list[dict]:
    """
    Search the FAISS vector store for documents similar to the query.

    Performs semantic similarity search with workspace-level isolation
    via metadata filtering.

    Args:
        query: The search query text.
        workspace_id: Workspace ID for multi-tenant isolation (required).
        knowledge_base_id: Optional KB ID to narrow search scope.
        k: Maximum number of results to return (default 10).
        score_threshold: Optional maximum L2 distance score. Lower is more similar.
                        Results with score above this threshold are excluded.

    Returns:
        List of dicts with keys: content, metadata, score.
    """
    vector_store = load_vector_store()

    # Build metadata filter for workspace isolation
    filter_dict = {"workspace_id": workspace_id}
    if knowledge_base_id:
        filter_dict["knowledge_base_id"] = knowledge_base_id

    results_with_scores = vector_store.similarity_search_with_score(
        query=query,
        k=k,
        filter=filter_dict,
    )

    search_results = []
    for doc, score in results_with_scores:
        # If score_threshold is set, skip results above the threshold
        if score_threshold is not None and score > score_threshold:
            continue

        search_results.append({
            "content": doc.page_content,
            "metadata": doc.metadata,
            "score": round(float(score), 4),
        })

    logger.info(
        f"Search completed",
        extra={
            "workspace_id": workspace_id,
            "query_length": len(query),
            "results_returned": len(search_results),
            "k": k,
        },
    )

    return search_results

def delete_vectors(
    vector_id: str = None,
    workspace_id: str = None,
    knowledge_id: str = None,
    knowledge_base_id: str = None
) -> bool:
    """
    Delete documents/vectors from FAISS store with flexible filtering.

    Supports both workspace-level and knowledge-item-level deletion.
    Following LangChain v1.0 best practices for metadata-based deletion.

    Args:
        vector_id: Legacy parameter - workspace identifier for deletion
                  Deprecated: Use workspace_id instead
                  If provided, deletes all docs with metadata.workspace_id == vector_id
        workspace_id: Workspace identifier for filtering
                     If provided alone, deletes all workspace vectors
                     If combined with knowledge_id, deletes specific knowledge item
        knowledge_base_id: Knowledge base identifier
                          Enables deletion of all items in a specific KB
                          Can be combined with workspace_id
        knowledge_id: Knowledge item identifier (file_id, text_id, web_id)
                     Must be used with workspace_id
                     Enables granular deletion of specific knowledge items

    Returns:
        bool: True if documents were deleted successfully, False if no documents found

    Raises:
        ValueError: If neither vector_id nor workspace_id is provided
        Exception: If vector store loading or deletion fails

    Examples:
        >>> # Delete all vectors for a workspace
        >>> result = delete_vectors(workspace_id="workspace-123")
        >>> print(result)
        True

        >>> # Delete vectors for a specific knowledge item
        >>> result = delete_vectors(
        ...     workspace_id="workspace-123",
        ...     knowledge_id="file-456"
        ... )
        >>> print(result)
        True

        >>> # Legacy usage (backward compatible)
        >>> result = delete_vectors(vector_id="workspace-123")
        >>> print(result)
        True
    """
    # Handle legacy vector_id parameter
    if vector_id and not workspace_id:
        workspace_id = vector_id

    if not workspace_id:
        raise ValueError("Either vector_id or workspace_id must be provided")

    try:
        vector_store = load_vector_store()
        
        if vector_store:
            # Collect all doc IDs matching the filter criteria
            ids_to_delete = []
            for doc_id, doc in vector_store.docstore._dict.items():
                # Check workspace_id match
                if doc.metadata.get("workspace_id") != workspace_id:
                    continue

                # If knowledge_base_id specified, also check that
                if knowledge_base_id and doc.metadata.get("knowledge_base_id") != knowledge_base_id:
                    continue

                # If knowledge_id specified, also check that
                if knowledge_id and doc.metadata.get("knowledge_id") != knowledge_id:
                    continue

                ids_to_delete.append(doc_id)

            if not ids_to_delete:
                filter_desc = f"workspace {workspace_id}"
                if knowledge_base_id:
                    filter_desc += f", KB {knowledge_base_id}"
                if knowledge_id:
                    filter_desc += f", knowledge {knowledge_id}"
                logger.info(f"No vectors found for {filter_desc}")
                return False

            # Delete matching documents
            filter_desc = f"workspace {workspace_id}"
            if knowledge_base_id:
                filter_desc += f", KB {knowledge_base_id}"
            if knowledge_id:
                filter_desc += f", knowledge {knowledge_id}"
            logger.info(f"Deleting {len(ids_to_delete)} vectors for {filter_desc}")
            result = vector_store.delete(ids=ids_to_delete)

            # Save the updated index after deletion
            if result:
                config = load_yaml()
                vector_store_path = config["vectorStore"]["store_path"]
                vector_store.save_local(vector_store_path)
                logger.info(f"Successfully deleted {len(ids_to_delete)} vectors")
                return True
            else:
                logger.error(f"Failed to delete vectors")
                return False
        else:
            logger.info(f"No Vector Store Found")

    except Exception as e:
        logger.error(f"Error deleting vectors: {str(e)}")
        raise