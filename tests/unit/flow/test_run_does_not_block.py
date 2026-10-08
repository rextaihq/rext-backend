"""Writing an article doesn't stall the backend's other requests (rext-control#386).

In the dashboard's `messages` stream mode the server sends the whole message so
far with every token, so the article step's long outputs became tens of MB per
run: rebuilt on the server per token, and pushed over every client connection.
The article step's models are tagged `nostream`, which keeps them out of that
mode; the `custom` token events the content step writes itself still flow. The
keyword clustering step's NLTK and TF-IDF work runs off the event loop.
"""

import asyncio
import threading
import time
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


def test_the_nltk_corpora_are_loaded_at_import_from_disk_without_a_download(monkeypatch):
    # NLTK's first corpus load is not thread-safe. Importing keyword_service (at
    # server start, on one thread) loads it, so the extractions running in
    # worker threads only ever read a loaded corpus; and the start makes no
    # network call: the image holds the data (G39, rext-control#390).
    import importlib

    import nltk
    from nltk.corpus import stopwords

    import src.services.keyword_service as keyword_service

    assert keyword_service.load_nltk_data(download=True)  # on disk for this test
    downloads = []
    monkeypatch.setattr(nltk, "download", lambda *a, **k: downloads.append(a) or True)
    try:
        reloaded = importlib.reload(keyword_service)
        assert downloads == []
        assert type(stopwords).__name__ != "LazyCorpusLoader"
        assert "the" in reloaded.ENGLISH_STOP_WORDS
        assert "the" in reloaded.KeywordExtractor().stop_words
        assert downloads == []
    finally:
        monkeypatch.undo()
        importlib.reload(keyword_service)


def test_missing_nltk_data_is_downloaded_once_on_first_use_not_at_start(monkeypatch):
    # No data on disk (a checkout that never fetched it): the server still starts,
    # with no download at import; the first extractions, in worker threads, fetch
    # it once between them.
    import importlib

    import nltk
    from nltk.corpus import stopwords

    import src.services.keyword_service as keyword_service

    assert keyword_service.load_nltk_data(download=True)
    real_words = stopwords.words
    downloads = []

    def missing(*args, **kwargs):
        raise LookupError("Resource stopwords not found.")

    def download(name, quiet=False):
        time.sleep(0.05)
        downloads.append(name)
        monkeypatch.setattr(stopwords, "words", real_words)
        return True

    monkeypatch.setattr(stopwords, "words", missing)
    monkeypatch.setattr(nltk, "download", download)
    try:
        reloaded = importlib.reload(keyword_service)
        assert reloaded.ENGLISH_STOP_WORDS is None and downloads == []

        extractors = []
        workers = [
            threading.Thread(target=lambda: extractors.append(reloaded.KeywordExtractor()))
            for _ in range(4)
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=30)

        assert downloads == list(reloaded.NLTK_DATA)  # once, not once per thread
        assert len(extractors) == 4 and all("the" in e.stop_words for e in extractors)
    finally:
        monkeypatch.undo()
        importlib.reload(keyword_service)
    assert keyword_service.ENGLISH_STOP_WORDS
