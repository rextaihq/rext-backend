from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import OllamaEmbeddings
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv
import os

load_dotenv()

def get_embedding() -> HuggingFaceEmbeddings:
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
        # embeddings = OllamaEmbeddings(model="nomic-embed-text:latest", num_gpu=0)
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small",api_key = os.getenv("OPENAI_API_KEY"))
        return embeddings
    except RuntimeError as e:
        # Log error and fallback to CPU if CUDA fails
        print(f"Warning: Failed to load embedding model with default settings: {e}")
        print("Falling back to CPU-only mode...")
        # return OllamaEmbeddings(
        #     model="nomic-embed-text:latest",
        #     num_gpu=0
        # )
        return OpenAIEmbeddings(model="text-embedding-3-small",api_key = os.getenv("OPENAI_API_KEY"))


if __name__ == "__main__":
    embedding = get_embedding()
    print(embedding.embed_query("Hello World"))

    # Test batch document embedding
    docs = [
            "Artificial Intelligence is evolving rapidly.",
            "Large Language Models are becoming more efficient.",
            "Agentic workflows are the next big thing in software development."
        ]
    print(f"\n2. Testing embed_documents with {len(docs)} documents")
    doc_vectors = embedding.embed_documents(docs)
    print(f"   Success! Created {len(doc_vectors)} vectors.")
    
    print("\n✅ Ollama embedding model is working correctly!")
