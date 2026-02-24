"""Convenience entrypoint for building the Rext LangGraph engine."""

from src.flow.engines.rext import create_rext_engine


def get_graph():
    """Return a compiled Rext graph instance."""
    return create_rext_engine()


graph = get_graph()


if __name__ == "__main__":
    print("Graph built successfully:", type(graph).__name__)