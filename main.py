"""Convenience entrypoint for building the Rext LangGraph engine."""

from src.flow.engines.rext import create_rext_engine


def build_graph():
    """Return a compiled Rext graph instance."""
    return create_rext_engine()


if __name__ == "__main__":
    graph = build_graph()
    print("Graph built successfully:", type(graph).__name__)