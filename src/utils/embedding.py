from langchain_openai import OpenAIEmbeddings

from src.utils.logger import logger

_embedding_model = None

def get_embedding():
    """
    Get OpenAI embedding model for vector retrieval tasks.
    """
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model

    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not found in environment")
            
        _embedding_model = OpenAIEmbeddings(
            model="text-embedding-3-small",
            api_key=api_key
        )
        return _embedding_model
    except Exception as e:
        logger.error(f"Failed to initialize embedding model: {e}", exc_info=True)
        # Final fallback
        return OpenAIEmbeddings(
            model="text-embedding-3-small",
            api_key=os.getenv("OPENAI_API_KEY")
        )


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
