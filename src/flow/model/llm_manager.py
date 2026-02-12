from functools import lru_cache

from langchain.chat_models import init_chat_model
from src.states.schemas import RewriterTitle, QueryDecomposer
from sentence_transformers import SentenceTransformer
from src.states.schemas import BasicTopicGenerationList
from langsmith import trace, traceable, Client
from src.api.config import get_settings

# Get settings instance
settings = get_settings()


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
    return model.with_retry(stop_after_attempt=3, wait_exponential_jitter=True)