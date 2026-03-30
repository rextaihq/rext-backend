import os

from langchain_openai import OpenAIEmbeddings

from src.utils.logger import logger

_embedding_model = None


def get_embedding() -> OpenAIEmbeddings:
    """
    Get or create the singleton OpenAI embedding model.

    Uses the text-embedding-3-small model (1536 dimensions).
    Fails fast if OPENAI_API_KEY is not set.

    Returns:
        OpenAIEmbeddings: Configured embedding model instance.

    Raises:
        ValueError: If OPENAI_API_KEY environment variable is not set.
    """
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY environment variable is required but not set. "
            "Please set it in your .env file or environment."
        )

    _embedding_model = OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=api_key,
    )
    logger.info("OpenAI embedding model initialized successfully (text-embedding-3-small)")
    return _embedding_model
    