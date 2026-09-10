import os

from langchain_openai import OpenAIEmbeddings


def get_embedding() -> OpenAIEmbeddings:
    """
    Get a fresh instance of the OpenAI embedding model.

    Uses the text-embedding-3-small model (1536 dimensions).
    Fails fast if OPENAI_API_KEY is not set.
    Direct initialization avoids loop-mismatch issues in multi-threaded/async environments.

    Returns:
        OpenAIEmbeddings: Configured embedding model instance.

    Raises:
        ValueError: If OPENAI_API_KEY environment variable is not set.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY environment variable is required but not set. "
            "Please set it in your .env file or environment."
        )

    model = OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=api_key,
    )
    # logger.debug("OpenAI embedding model instance created (text-embedding-3-small)")
    return model
