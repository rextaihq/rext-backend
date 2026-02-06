from functools import lru_cache

from langchain.chat_models import init_chat_model
from src.states.schemas import RewriterTitle, QueryDecomposer
from sentence_transformers import SentenceTransformer
from src.states.schemas import BasicTopicGenerationList
from langsmith import trace, traceable, Client
from src.api.config import get_settings

# Get settings instance
settings = get_settings()


@lru_cache(maxsize=1)
def load_model():
    """
    Initializes and returns a chat model using LangChain's `init_chat_model`.

    This function loads the `gpt-4o-mini` model from the OpenAI provider.
    The model is cached (singleton) and includes automatic retry logic
    for transient failures (rate limits, timeouts).

    Returns:
        BaseChatModel: An instance of the initialized chat model with retry.
    """
    model = init_chat_model("gpt-4o-mini", model_provider="openai", api_key=settings.OPENAI_API_KEY)
    return model


@lru_cache(maxsize=1)
def topic_generation_model():
    """
    Initializes a chat model with structured output for BasicTopicGenerationList.
    Cached as singleton — reuses the same instance across all calls.

    Returns:
        BaseStructuredChatModel: A chat model that returns outputs conforming to the `BasicTopicGenerationList` schema.
    """
    model = load_model()
    return model.with_structured_output(BasicTopicGenerationList)

