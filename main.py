"""Convenience entrypoint for building the Rext LangGraph engine."""

from src.flow.utils.langgraph_compat import apply_langgraph_patches
from src.flow.engines.rext import create_rext_engine

apply_langgraph_patches()

# def get_graph():
#     """Return a compiled Rext graph instance."""
#     return create_rext_engine()


graph = create_rext_engine()


if __name__ == "__main__":
    print("Graph built successfully:", type(graph).__name__)
