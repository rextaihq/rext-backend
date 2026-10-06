"""Writing an article doesn't stall the backend's other requests (rext-control#386).

In the dashboard's `messages` stream mode the server sends the whole message so
far with every token, so the article step's long outputs became tens of MB per
run: rebuilt on the server per token, and pushed over every client connection.
The article step's models are tagged `nostream`, which keeps them out of that
mode; the `custom` token events the content step writes itself still flow. The
keyword clustering step's NLTK and TF-IDF work runs off the event loop.
"""

import threading
from collections import Counter
from typing import TypedDict
from unittest.mock import AsyncMock

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.config import get_stream_writer
from langgraph.constants import TAG_NOSTREAM
from langgraph.graph import END, START, StateGraph

import src.flow.engines.seo.keyword_clustering as clustering_module
import src.flow.model.llm_manager as llm_manager

ARTICLE = " ".join(["word"] * 200)


@pytest.fixture
def tags_of(monkeypatch):
    """The tags a loader passes to init_chat_model."""
    seen = []

    def fake_init(model, **kwargs):
        seen.append(kwargs)
        return object()

    monkeypatch.setattr(llm_manager, "init_chat_model", fake_init)

    def tags(loader):
        loader()
        return seen[-1].get("tags") or []

    return tags


def test_the_article_steps_models_are_kept_out_of_the_messages_stream(tags_of):
    assert TAG_NOSTREAM in tags_of(llm_manager.load_luna_content_model)  # the content agent
    assert TAG_NOSTREAM in tags_of(llm_manager.load_humanize_model)
    assert TAG_NOSTREAM in tags_of(llm_manager.load_content_model)  # repair


def test_the_earlier_steps_models_still_stream_their_messages(tags_of):
    # The outline and title steps are untouched: the dashboard's live outline
    # reads them from the messages stream.
    assert TAG_NOSTREAM not in tags_of(llm_manager.load_model)
    assert TAG_NOSTREAM not in tags_of(llm_manager.topic_generation_model)


class _State(TypedDict, total=False):
    text: str


def _graph(model):
    """A node that streams a model the way generate_content streams its agent."""

    async def write_article(state):
        write = get_stream_writer()
        async for event in model.astream_events("write", version="v2"):
            if event["event"] == "on_chat_model_stream":
                write({"type": "token", "content": event["data"]["chunk"].content})
        return {"text": "done"}

    graph = StateGraph(_State)
    graph.add_node("write_article", write_article)
    graph.add_edge(START, "write_article")
    graph.add_edge("write_article", END)
    return graph.compile()


async def _stream(tags):
    model = GenericFakeChatModel(messages=iter([AIMessage(content=ARTICLE)]), tags=tags)
    modes, tokens = Counter(), []
    async for mode, chunk in _graph(model).astream({}, stream_mode=["messages", "custom"]):
        modes[mode] += 1
        if mode == "custom":
            tokens.append(chunk["content"])
    return modes, "".join(tokens)


async def test_a_nostream_model_sends_its_custom_tokens_and_no_messages():
    modes, text = await _stream(tags=[TAG_NOSTREAM])

    assert modes["messages"] == 0
    assert text == ARTICLE


async def test_without_the_tag_every_token_is_also_a_messages_event():
    # The control: the same node, untagged, doubles every token into messages.
    modes, text = await _stream(tags=None)

    assert modes["messages"] >= 200
    assert text == ARTICLE


async def test_keyword_extraction_runs_off_the_event_loop(monkeypatch):
    threads = []

    class Extractor:
        def extract_keywords(self, serp, **kwargs):
            threads.append(threading.current_thread())
            return [{"keyword": "content marketing roi", "score": 1.0}]

    monkeypatch.setattr(clustering_module, "KeywordExtractor", Extractor)
    cluster = AsyncMock(return_value=[{"name": "ROI"}])
    monkeypatch.setattr(clustering_module.KeywordClusteringService, "cluster_keywords", cluster)
    state = {
        "serp_normalized": {"query": "content marketing roi", "normalize_results": []},
        "seo_result": {"serp_backlinks": {"main_intent": "informational"}},
        "content": {"content_type": "blog", "selected_topic": "Content Marketing ROI"},
    }

    result = await clustering_module.keyword_clustering_node(state)

    assert threads and threads[0] is not threading.main_thread()
    assert result["seo_result"]["keyword_clusters"] == [{"name": "ROI"}]
