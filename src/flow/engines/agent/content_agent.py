from typing import Any, Callable, Sequence, Optional
from uuid import UUID
from langchain_core.caches import BaseCache
from langchain_core.tools import BaseTool
from langchain_ollama import ChatOllama
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langgraph.graph.state import CompiledStateGraph

from src.flow.engines.agent.tools.tools import get_tools
from src.flow.model.structure.contents import get_generated_content_model
from src.flow.prompts.system.content import CONTENT_SYSTEM_PROMPT
from langchain.agents.structured_output import ToolStrategy
from src.flow.model.llm_manager import load_content_model
from src.flow.engines.agent.middleware.persona_middleware import PersonaInjectionMiddleware
from src.flow.engines.agent.middleware.humanize_middleware import HumanizeMiddleware
from src.flow.model.llm_manager import load_model

async def create_content_agent(
    model: Optional[Any] = None,
    tools: Optional[Sequence[BaseTool | Callable | dict[str, Any]]] = None,
    # system_prompt: str = CONTENT_SYSTEM_PROMPT,
    rext_middleware: Sequence[AgentMiddleware] = (),
    debug: bool = False,
    name: Optional[str] = "content_agent",
    cache: Optional[BaseCache] = None,
    content_type: str=None,
    agent_store=None,
    response_format=None,
    counters: Optional[dict] = None,
) -> CompiledStateGraph:
    """
    Create a content agent with parent/child tool routing AND dynamic integration tools.
    REMOVED: No db/user_id/agent_id/workspace_id/active_integrations params - all handled internally.
    """

    # Assemble Base Tools (include ALL known tools so executor can run them)
    if tools is None:
        tools = get_tools(counters=counters)
    else:
        tools_list = list(tools)
        tools = tools_list

    if model is None:
        model = load_content_model()

    if response_format is None:
        response_format = ToolStrategy(get_generated_content_model(content_type), handle_errors=True)

    # Middleware Stack
    middleware_stack = [
        PersonaInjectionMiddleware(),
        HumanizeMiddleware(),
    ]

    if rext_middleware:
      middleware_stack.extend(rext_middleware)

    return create_agent(
        model=model,
        tools=tools,
        # system_prompt=system_prompt,
        middleware=middleware_stack,
        debug=debug,
        name=name,
        cache=cache,
        store=agent_store,
        response_format=response_format,
    ).with_config({"recursion_limit": 50})


if __name__ == "__main__":
  pass