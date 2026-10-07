"""No unit test reaches a real model provider (G76, rext-control#613).

tests/conftest.py refuses every request the OpenAI client would send and fails the test that tried,
so a test can't spend credits or fail when the account is empty or the provider is down.
"""

from types import SimpleNamespace

import openai
import pytest
from langchain.chat_models import init_chat_model

import tests.conftest as conftest
from tests.conftest import LiveModelCallBlocked


async def test_a_model_call_is_refused_before_it_leaves(request):
    model = init_chat_model(
        "gpt-4o-mini", model_provider="openai", api_key="sk-test", max_retries=0
    )

    with pytest.raises(LiveModelCallBlocked):
        await model.ainvoke("hello")

    assert request.node.live_model_calls == ["AsyncOpenAI"]
    request.node.live_model_calls.clear()  # this test reached it on purpose


def test_the_sync_client_is_refused_too(request):
    client = openai.OpenAI(api_key="sk-test", max_retries=0)

    with pytest.raises(LiveModelCallBlocked):
        client.chat.completions.create(
            model="gpt-4o-mini", messages=[{"role": "user", "content": "hi"}]
        )

    assert request.node.live_model_calls == ["OpenAI"]
    request.node.live_model_calls.clear()


def _marked_item(marker):
    added = []
    return SimpleNamespace(
        added=added,
        add_marker=added.append,
        get_closest_marker=lambda name: object() if name == marker else None,
    )


@pytest.mark.parametrize(("opted_in", "skipped"), [(False, True), (True, False)])
def test_a_live_model_test_is_skipped_unless_asked(monkeypatch, opted_in, skipped):
    live, plain = _marked_item("live_model"), _marked_item("unit")
    monkeypatch.setattr(conftest, "RUN_LIVE_MODEL_TESTS", opted_in)

    conftest.pytest_collection_modifyitems(None, [live, plain])

    assert [m.mark.name for m in live.added] == (["skip"] if skipped else [])
    assert plain.added == []
