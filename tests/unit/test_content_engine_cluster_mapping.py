from src.flow.engines.content.content_engine import create_content_engine


def test_content_engine_maps_clusters_before_outline_generation():
    engine = create_content_engine()

    assert "map_keyword_clusters" in engine.nodes
