from src.subgraphs.webSearch import web_search
from src.states.State import AgentState
from langgraph.graph import StateGraph, START
from langgraph.prebuilt import ToolNode, tools_condition
from src.tools.searchTool import get_tools

from src.api.lib.logger import auto_logger

logger = auto_logger()


def get_subgraph():
    """
    Build and compile a subgraph for the search workflow.

    This subgraph:
    1. Starts at the "SearchAgent" node.
    2. Uses a ToolNode to process tools returned by `get_tools()`.
    3. Routes execution between "SearchAgent" and "tools" based on `tools_condition`.
    4. Ends after the "SearchAgent" node completes execution.

    Returns:
        StateGraph: The compiled search workflow graph ready for execution.
    """
    
    # Initialize the shared state graph
    graph_builder = StateGraph(AgentState)

    # --- Add nodes ---
    graph_builder.add_node("SearchAgent", web_search)             # Main search node
    tool_node = ToolNode(tools=get_tools())                       # Tools handler
    graph_builder.add_node("tools", tool_node)

    # --- Define edges ---
    graph_builder.add_conditional_edges(
        "SearchAgent", 
        tools_condition
    )
    graph_builder.add_edge("tools", "SearchAgent")                 # Loop back
    graph_builder.add_edge(START, "SearchAgent")                   # Start point
    graph_builder.set_finish_point("SearchAgent")                  # End point

    # Compile and return the graph
    return graph_builder.compile()

if __name__ == "__main__":
    graph = get_subgraph()

    query = "Latest Update in wordpress Maintenenane"

    # # Run the graph
    # res = graph.invoke({
    #     "selected_articles": [{"title": query}]
    # })
    #
    # print(res['selected_articles'])