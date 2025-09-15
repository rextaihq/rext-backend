from langchain_huggingface import HuggingFaceEmbeddings

def get_hf_embedding():
    """Return a HuggingFace embedding model for retrieval tasks."""
    try:
        return HuggingFaceEmbeddings(
            model_name="BAAI/bge-small-en",
            model_kwargs={"device": 'cpu'}
        )
    except RuntimeError:
        # fallback to CPU if CUDA fails
        return HuggingFaceEmbeddings(
            model_name="BAAI/bge-small-en",
            model_kwargs={"device": "cpu"}
        )