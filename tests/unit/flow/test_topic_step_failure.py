"""A topic step that yields no titles ends the run with a message (rext-control#359).

On the local stack a refused OpenAI key made topic generation return no topics;
the graph then skipped the title gate, generate_outline found no topic, and the
outline gate opened with an empty outline. Now the run ends at topics_failed,
with the same run.failed event and content.error the no-SERP end uses.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import src.flow.engines.content.generation.cluster_mapping as cluster_mapping_module
import src.flow.engines.content.generation.content_type as content_type_module
import src.flow.engines.content.generation.outline as outline_module
import src.flow.engines.content.generation.topic_generation as topic_module
import src.flow.engines.content.review.outline as review_outline_module
import src.flow.engines.seo.keyword_clustering as clustering_module
from src.flow.engines.content.content_engine import create_content_engine
from src.flow.engines.content.generation.topic_generation import (
    TOPICS_FAILED_CODE,
    TOPICS_FAILED_MESSAGE,
    topics_router,
)

STATE = {
    "serp_payload": {"query": "content marketing roi for small business", "workspace_id": "w"},
    "serp_normalized": {"query": "content marketing roi for small business"},
    "content": {"content_type": "blog"},
}


def _must_not_run(name):
    def node(state, *args, **kwargs):
        raise AssertionError(f"{name} ran after a failed topic step")

    return node


@pytest.fixture
def graph(monkeypatch):
    # The content-type gate passes straight through; the topic node is the
    # real one, with its model step failing the way a refused key makes it.
    monkeypatch.setattr(content_type_module, "content_type", lambda state: {})
    monkeypatch.setattr(
        topic_module,
        "topic_generation_model",
        lambda: SimpleNamespace(with_structured_output=lambda schema: object()),
    )
    monkeypatch.setattr(topic_module, "_generate_and_validate_topics", AsyncMock(return_value=None))
    monkeypatch.setattr(clustering_module, "keyword_clustering_node", _must_not_run("clustering"))
    monkeypatch.setattr(
        cluster_mapping_module, "map_keyword_clusters", _must_not_run("cluster mapping")
    )
    monkeypatch.setattr(outline_module, "generate_outline", _must_not_run("generate_outline"))
    monkeypatch.setattr(review_outline_module, "review_outline", _must_not_run("review_outline"))
    log = AsyncMock()
    monkeypatch.setattr("src.services.monitoring_service.MonitoringService.persist_error_log", log)
    return create_content_engine(), log


async def test_a_topic_step_with_no_titles_ends_the_run_with_its_message(graph):
    engine, log = graph
    events, final = [], None

    async for mode, chunk in engine.astream(STATE, stream_mode=["custom", "values"]):
        if mode == "custom":
            events.append(chunk)
        else:
            final = chunk

    assert events == [
        {
            "type": "run",
            "step": "run.failed",
            "error_code": TOPICS_FAILED_CODE,
            "message": TOPICS_FAILED_MESSAGE,
        }
    ]
    assert final["content"]["error_code"] == TOPICS_FAILED_CODE
    assert final["content"]["error"] == TOPICS_FAILED_MESSAGE
    assert final["content"]["topics"] == []
    assert "outline" not in final["content"]
    log.assert_awaited_once()


def test_the_router_sends_a_failed_topic_step_to_its_end():
    assert topics_router({"content": {"error_code": TOPICS_FAILED_CODE}}) == "topics_failed"
    assert topics_router({"content": {"topics": [{"title": "A"}]}}) == "keyword_clustering"
    assert topics_router({}) == "keyword_clustering"


async def test_no_query_ends_the_same_way():
    result = await topic_module.topic_generation({"serp_normalized": {}, "serp_payload": {}})

    assert result["content"]["error_code"] == TOPICS_FAILED_CODE
    assert result["content"]["topics"] == []
