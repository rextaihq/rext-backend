import logging

logger = logging.getLogger(__name__)

from langchain.chat_models import (  # noqa: E402 -- intentional: avoids a circular import
    init_chat_model,  # noqa: E402 -- intentional: avoids a circular import
)
from langchain_groq import ChatGroq  # noqa: E402 -- intentional: avoids a circular import

from src.api.config import get_settings  # noqa: E402 -- intentional: avoids a circular import

# Get settings instance
settings = get_settings()


def get_default_model():
    model = ChatGroq(
        model="openai/gpt-oss-120b",
        temperature=0,
        max_tokens=None,
        reasoning_format="parsed",
        timeout=None,
        max_retries=2,
        api_key="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",
    )
    return model


# Default token limits per use case
DEFAULT_MAX_TOKENS = 8192
CONTENT_GENERATION_MAX_TOKENS = 16384
TOPIC_GENERATION_MAX_TOKENS = 1024


def load_model(max_tokens: int = DEFAULT_MAX_TOKENS, temperature: float | None = None):
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
    # `temperature` is opt-in: omitted, this keeps OpenAI's default (1.0) and so
    # every existing caller behaves exactly as before. Extraction callers that
    # need repeatable output pass 0 explicitly - see workspace persona
    # extraction, where the default made the same page yield a different
    # persona list on every run.
    kwargs = {}
    if temperature is not None:
        kwargs["temperature"] = temperature
    model = init_chat_model(
        "gpt-4o-mini",
        model_provider="openai",
        api_key=settings.OPENAI_API_KEY,
        max_tokens=max_tokens,
        streaming=True,
        **kwargs,
    )
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
        temperature=0.9,
        streaming=True,
    )


def load_luna_content_model():
    """
    Returns GPT-5.6 Luna configured for content generation.

    Luna is OpenAI's fastest/lowest-cost GPT-5.6 tier. Like gpt-5.2, it's a
    reasoning model: it takes `reasoning_effort` instead of `temperature`,
    and doesn't support `streaming`.

    use_responses_api=True is required, not optional: OpenAI does not support
    function/tool calling with a reasoning model over the classic
    /v1/chat/completions endpoint at all — only over /v1/responses. The
    installed langchain-openai's auto-detection for which endpoint to use
    (_model_prefers_responses_api) only recognizes "-pro" tier reasoning
    models (gpt-5-pro, gpt-5.2-pro, gpt-5.4-pro, gpt-5.5-pro as of the latest
    1.6.0 release) — it doesn't know about gpt-5.6-luna yet, so it silently
    defaults to the unsupported chat/completions path for this model unless
    told otherwise here. Without this, an agent using this model with tools
    attached (search_tool, generate_image) doesn't reliably respect stop
    instructions from tool-call caps, which can exhaust LangGraph's
    recursion_limit before ever reaching a final answer.
    """
    return init_chat_model(
        "gpt-5.6-luna",
        model_provider="openai",
        api_key=settings.OPENAI_API_KEY,
        max_tokens=CONTENT_GENERATION_MAX_TOKENS,
        reasoning_effort="none",
        use_responses_api=True,
    )


def load_humanize_model():
    """
    Returns a model configured for content humanization.

    Humanization needs higher output limits because it rewrites complete
    long-form content while preserving the original structure.
    """
    return init_chat_model(
        "gpt-5.2",
        model_provider="openai",
        api_key=settings.OPENAI_API_KEY,
        max_tokens=CONTENT_GENERATION_MAX_TOKENS,
        reasoning_effort="low",
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
