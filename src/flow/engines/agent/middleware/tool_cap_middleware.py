import logging
from collections.abc import Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from src.flow.engines.agent.tools.tools import SEARCH_HARD_CAP

logger = logging.getLogger(__name__)


class ToolCapMiddleware(AgentMiddleware):
    """
    Intercepts tool calls before execution and enforces hard caps.
    Blocks capped search calls without hitting Tavily — no API cost, no context loss.
    """

    def __init__(self, counters: dict):
        super().__init__()
        self._counters = counters

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        name = request.tool_call["name"]

        if name == "search_tool":
            search_count = self._counters.get("search", [0])
            if search_count[0] >= SEARCH_HARD_CAP:
                logger.warning(
                    "ToolCapMiddleware: search cap %d/%d reached — blocking call.",
                    search_count[0],
                    SEARCH_HARD_CAP,
                )
                return ToolMessage(
                    content=(
                        f"HARD STOP: search cap reached ({SEARCH_HARD_CAP}/{SEARCH_HARD_CAP}). "
                        "You have gathered sufficient evidence. "
                        "Proceed IMMEDIATELY to writing the final article with the information already gathered."
                    ),
                    tool_call_id=request.tool_call["id"],
                )

        if name == "generate_image" and (
            self._counters.get("image_task") is not None
            or self._counters.get("image_placeholder") is not None
        ):
            logger.warning(
                "ToolCapMiddleware: generate_image already fired — blocking duplicate call."
            )
            return ToolMessage(
                content=(
                    "HARD STOP: image generation already started. "
                    "Do NOT call generate_image again. "
                    "The image will be injected automatically. "
                    "Proceed IMMEDIATELY to writing the final article."
                ),
                tool_call_id=request.tool_call["id"],
            )

        return await handler(request)
