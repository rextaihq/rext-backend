import asyncio
import logging

from langchain.chat_models import init_chat_model
from langchain_core.callbacks import AsyncCallbackHandler, BaseCallbackHandler
from langgraph.constants import TAG_NOSTREAM

from src.api.config import get_settings
from src.flow.model.provider_outage import provider_outage, report_provider_outage
from src.utils.loop_local_http import SHARED_ASYNC_CLIENT

logger = logging.getLogger(__name__)
settings = get_settings()


# The event loop serving requests. LangChain runs sync callbacks in a worker
# thread, where asyncio.get_running_loop() raises, so the loop has to be
# captured while we are still on it -- see _remember_loop below.
_MAIN_LOOP: "asyncio.AbstractEventLoop | None" = None


def _remember_loop() -> None:
    """Capture the serving loop. Called where models are built, on the loop."""
    global _MAIN_LOOP
    if _MAIN_LOOP is None:
        try:
            _MAIN_LOOP = asyncio.get_running_loop()
        except RuntimeError:
            pass


def _alert_if_outage(service: str, error: BaseException) -> None:
    """An empty account, a rate limit or the provider down: the team hears of it, once an hour (G75)."""
    try:
        outage = provider_outage(error, service)
        if outage is not None:
            report_provider_outage(outage)
    except Exception:  # noqa: BLE001 - reporting never breaks generation
        pass


async def _report_ai_failure(service: str, error: BaseException) -> None:
    _alert_if_outage(service, error)
    try:
        from src.services.monitoring_service import MonitoringService

        await MonitoringService.report_third_party_failure(
            service=service,
            message=f"AI provider call failed: {error}",
            error=error,
            metadata={"provider": service},
        )
    except Exception:  # noqa: BLE001 - reporting never breaks generation
        pass


class _AsyncAIProviderFailureReporter(AsyncCallbackHandler):
    """
    Record AI provider failures in the admin Error Logs.

    Model calls happen inside LangGraph nodes across a dozen call sites, none
    of which reach an HTTP exception handler, so a provider outage -- an
    expired key, an exhausted quota, a vendor incident -- produced nothing an
    operator could see. Attaching this once where the models are built covers
    every call site without changing how any of them behave.

    This handler serves the async path (``ainvoke``), which is all but one of
    the call sites; it is awaited on the loop, so nothing has to be scheduled.
    """

    def __init__(self, service: str):
        self.service = service

    async def on_llm_error(self, error: BaseException, **kwargs) -> None:
        await _report_ai_failure(self.service, error)


class _SyncAIProviderFailureReporter(BaseCallbackHandler):
    """
    The same, for the sync path (``invoke``).

    Sync callbacks run in a worker threamodeld with no loop of its own, so the
    coroutine is handed back to the captured serving loop. Both handlers are
    attached to every model; when both fire for one failure the throttle in
    MonitoringService collapses them into a single row.
    """

    def __init__(self, service: str):
        self.service = service

    def on_llm_error(self, error: BaseException, **kwargs) -> None:
        loop = _MAIN_LOOP
        if loop is None or loop.is_closed():
            logger.warning("AI provider call failed (no loop to record it): %s", error)
            _alert_if_outage(self.service, error)
            return
        try:
            asyncio.run_coroutine_threadsafe(_report_ai_failure(self.service, error), loop)
        except Exception:  # noqa: BLE001 - reporting never breaks generation
            pass


def _reporters(service: str):
    """Both handlers for one provider, with the serving loop captured."""
    _remember_loop()
    return [
        _AsyncAIProviderFailureReporter(service),
        _SyncAIProviderFailureReporter(service),
    ]


# The article step's models are kept out of a run's `messages` stream. In that
# mode the server sends the whole message so far with every token, so one
# article's outputs become tens of MB, rebuilt on the server per token and
# pushed to every client. The dashboard doesn't need it for the article: the
# content step sends its own `custom` token events (content_generation.py),
# which this tag leaves alone. rext-control#386.
ARTICLE_STEP_TAGS = [TAG_NOSTREAM]

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
        callbacks=_reporters("OpenAI"),
        api_key=settings.OPENAI_API_KEY,
        # One pool per event loop: runs on their own loops never share a connection (G80).
        http_async_client=SHARED_ASYNC_CLIENT,
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
        callbacks=_reporters("OpenAI"),
        api_key=settings.OPENAI_API_KEY,
        # One pool per event loop: runs on their own loops never share a connection (G80).
        http_async_client=SHARED_ASYNC_CLIENT,
        max_tokens=CONTENT_GENERATION_MAX_TOKENS,
        temperature=0.9,
        streaming=True,
        tags=ARTICLE_STEP_TAGS,
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
        callbacks=_reporters("OpenAI"),
        api_key=settings.OPENAI_API_KEY,
        # One pool per event loop: runs on their own loops never share a connection (G80).
        http_async_client=SHARED_ASYNC_CLIENT,
        max_tokens=CONTENT_GENERATION_MAX_TOKENS,
        reasoning_effort="none",
        use_responses_api=True,
        tags=ARTICLE_STEP_TAGS,
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
        callbacks=_reporters("OpenAI"),
        api_key=settings.OPENAI_API_KEY,
        # One pool per event loop: runs on their own loops never share a connection (G80).
        http_async_client=SHARED_ASYNC_CLIENT,
        max_tokens=CONTENT_GENERATION_MAX_TOKENS,
        reasoning_effort="low",
        tags=ARTICLE_STEP_TAGS,
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
        callbacks=_reporters("OpenAI"),
        api_key=settings.OPENAI_API_KEY,
        # One pool per event loop: runs on their own loops never share a connection (G80).
        http_async_client=SHARED_ASYNC_CLIENT,
        max_tokens=TOPIC_GENERATION_MAX_TOKENS,
        streaming=True,
    )
    return model
