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
    return model.with_retry(stop_after_attempt=3, wait_exponential_jitter=True)


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


@lru_cache(maxsize=1)
def search_model():
    """
    Initializes and returns a chat model for search operations.
    Cached as singleton with automatic retry logic.

    Returns:
        BaseChatModel: An instance of the initialized chat model with retry.
    """
    model = init_chat_model("gpt-4o-mini", model_provider="openai")
    return model.with_retry(stop_after_attempt=3, wait_exponential_jitter=True)


@lru_cache(maxsize=1)
def load_embedder():
    """
    Loads and returns a SentenceTransformer embedder using the 'all-MiniLM-L6-v2' model on CPU.
    Cached as singleton — the model is loaded from disk only once.

    Returns:
        SentenceTransformer: An instance of the SentenceTransformer model for generating embeddings.
    """
    return SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', device="cpu")


@lru_cache(maxsize=1)
def title_refine_model():
    """
    Initializes a chat model with structured output for RewriterTitle.
    Cached as singleton.
    """
    llm = load_model()
    return llm.with_structured_output(RewriterTitle)


@lru_cache(maxsize=1)
def query_decomposer_model():
    """
    Initializes a chat model with structured output for QueryDecomposer.
    Cached as singleton.
    """
    llm = load_model()
    return llm.with_structured_output(QueryDecomposer)
