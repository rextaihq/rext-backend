from langchain_huggingface import HuggingFaceEmbeddings

def get_hf_embedding() -> HuggingFaceEmbeddings:
    """
    Get HuggingFace embedding model for vector retrieval tasks.

    Following LangChain v1.0 best practices (Released Oct 2025):
    - Uses BAAI/bge-small-en for high-quality embeddings
    - Handles GPU/CPU device selection automatically
    - Singleton-like behavior (model is cached after first load)

    Model Details:
    - Model: BAAI/bge-small-en (BGE = BAAI General Embedding)
    - Dimensions: 384
    - Context Window: 512 tokens
    - Performance: Top-tier on MTEB benchmark for retrieval
    - Size: ~133MB (small, fast, production-ready)

    Returns:
        HuggingFaceEmbeddings: Configured embedding model instance

    Raises:
        RuntimeError: If model loading fails (re-raised after CPU fallback)

    Example:
        >>> embeddings = get_hf_embedding()
        >>> vector = embeddings.embed_query("sample text")
        >>> print(len(vector))
        384

        >>> # Batch embedding
        >>> vectors = embeddings.embed_documents(["text1", "text2"])
        >>> print(len(vectors))
        2

    Note:
        Model is downloaded to HuggingFace cache on first use (~133MB).
        Subsequent calls reuse cached model for fast initialization.
    """
    try:
        return HuggingFaceEmbeddings(
            model_name="BAAI/bge-small-en",
            model_kwargs={"device": "cpu"}
        )
    except RuntimeError as e:
        # Log error and fallback to CPU if CUDA fails
        print(f"Warning: Failed to load embedding model with default settings: {e}")
        print("Falling back to CPU-only mode...")
        return HuggingFaceEmbeddings(
            model_name="BAAI/bge-small-en",
            model_kwargs={"device": "cpu"}
        )