from langchain_community.vectorstores import FAISS
from  src.utils.embedding import get_hf_embedding

def load_vector_store(file_path: str = 'my_faiss_index3'):
    """
    Load a FAISS vector store from a local file.

    Args:
        file_path (str, optional): Path to the saved FAISS index directory.
                                   Defaults to 'my_faiss_index3'.

    Returns:
        FAISS: A loaded FAISS vector store with embeddings.
    """
    vector_store = FAISS.load_local(
        file_path, get_hf_embedding(), allow_dangerous_deserialization=True
    )
    return vector_store