import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

from langchain.chat_models import init_chat_model
from langchain_community.callbacks.manager import get_openai_callback
from langsmith import trace, traceable, Client
from src.api.config import get_settings
from openai import OpenAI
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
        streaming=True,
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
        streaming=True,
    )


def topic_generation_model():
    """
    Initializes a chat model with low token limits suitable for topic generation.
    Cached as singleton — reuses the same instance across all calls.

    Returns:
        BaseChatModel: A chat model with 1024 max output tokens.
    """
    model = init_chat_model(
        "gpt-4o-mini",
        model_provider="openai",
        api_key=settings.OPENAI_API_KEY,
        max_tokens=TOPIC_GENERATION_MAX_TOKENS,
        streaming=True,
    )
    return model

def load_humanize_model():
    """
    Returns a model configured for content humanization with higher token limits.

    Humanization transforms AI content to appear natural, which requires
    significant context and output length.

    Returns:
        BaseChatModel: A chat model with 8192 max output tokens.
    """

    # return init_chat_model(
    # "gpt-5-mini", 
    # model_provider="openai",
    # api_key=settings.OPENAI_API_KEY,
    # max_tokens=CONTENT_GENERATION_MAX_TOKENS,
    # )   

    return init_chat_model(
    "gpt-5.2",
    model_provider="openai",
    api_key=settings.OPENAI_API_KEY,
    max_tokens=CONTENT_GENERATION_MAX_TOKENS,
    reasoning_effort="low"
)