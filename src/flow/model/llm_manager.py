import logging
from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_community.callbacks.manager import get_openai_callback
from langsmith import trace, traceable, Client
from src.api.config import get_settings

logger = logging.getLogger(__name__)

# Get settings instance
settings = get_settings()

# Default token limits per use case
DEFAULT_MAX_TOKENS = 4096
CONTENT_GENERATION_MAX_TOKENS = 8192
TOPIC_GENERATION_MAX_TOKENS = 1024


def load_model(max_tokens: int = DEFAULT_MAX_TOKENS):
    """
    Initializes and returns a chat model using LangChain's `init_chat_model`.

    This function loads the `gpt-4o-mini` model from the OpenAI provider.
    The model is cached (singleton) and includes a max_tokens limit
    to control API costs.

    Args:
        max_tokens: Maximum number of tokens the model can generate per call.
                    Defaults to 4096. Use CONTENT_GENERATION_MAX_TOKENS (8192)
                    for content generation nodes that need longer output.

    Returns:
        BaseChatModel: An instance of the initialized chat model.
    """
    model = init_chat_model(
        "gpt-4o-mini",
        model_provider="openai",
        api_key=settings.OPENAI_API_KEY,
        max_tokens=max_tokens,
    )
    logger.info("Initialized LLM model gpt-4o-mini with max_tokens=%d", max_tokens)
    return model


def load_content_model():
    """
    Returns a model configured for content generation with higher token limits.

    Content generation, E-E-A-T injection, and humanization produce long-form
    content that needs more output tokens than other operations.

    Returns:
        BaseChatModel: A chat model with 8192 max output tokens.
    """
    return init_chat_model(
        "gpt-4o-mini",
        model_provider="openai",
        api_key=settings.OPENAI_API_KEY,
        max_tokens=CONTENT_GENERATION_MAX_TOKENS,
    )


def topic_generation_model():
    """
    Initializes a chat model for topic generation with appropriate token limits.

    Returns:
        BaseChatModel: A chat model configured for topic generation.
    """
    model = init_chat_model(
        "gpt-4o-mini",
        model_provider="openai",
        api_key=settings.OPENAI_API_KEY,
        max_tokens=TOPIC_GENERATION_MAX_TOKENS,
    )
    return model

