"""A model call that turns into a run of whitespace is stopped and asked once more
(rext-control#697): on staging one outline call wrote 26,402 whitespace characters in a row,
until the token limit, and the review step opened on an empty outline."""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessageChunk, HumanMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from openai import LengthFinishReasonError
from pydantic import BaseModel

import src.flow.engines.content.generation.outline as outline_module
import src.flow.model.runaway as runaway
from src.flow.engines.content.generation.provider_unavailable import (
    PROVIDER_UNAVAILABLE_CODE,
    PROVIDER_UNAVAILABLE_MESSAGE,
    stop_on_outage,
)
from src.flow.model.provider_outage import (
    STEP_FAILED,
    UNREADABLE_ANSWER,
    ProviderUnavailable,
    provider_outage,
)
from src.flow.model.runaway import (
    WhitespaceRunaway,
    WhitespaceWatch,
    ainvoke_watched,
    answer_before_runaway,
    ran_away,
)

pytestmark = pytest.mark.unit


# --- the watch ----------------------------------------------------------------------------


def test_a_long_run_of_whitespace_stops_the_call():
    watch, run = WhitespaceWatch(limit=10), uuid4()
    watch.on_llm_new_token('{"title":', run_id=run)
    for _ in range(9):
        watch.on_llm_new_token(" ", run_id=run)
    with pytest.raises(WhitespaceRunaway, match="10 whitespace characters"):
        watch.on_llm_new_token("\n", run_id=run)


def test_indented_json_is_not_a_runaway():
    watch, run = WhitespaceWatch(), uuid4()
    deep = "\n" + " " * 40  # ten levels of four-space indentation
    for _ in range(200):
        for token in ["{", deep, '"steps"', ":", " [", deep, "{", deep, '"a"', "}"]:
            watch.on_llm_new_token(token, run_id=run)


def test_whitespace_that_ends_one_token_counts_towards_the_run():
    watch, run = WhitespaceWatch(limit=10), uuid4()
    watch.on_llm_new_token('"tips":    ', run_id=run)  # four at its end
    watch.on_llm_new_token("     ", run_id=run)  # nine
    with pytest.raises(WhitespaceRunaway):
        watch.on_llm_new_token("\t", run_id=run)


def test_each_call_is_counted_on_its_own_and_forgotten_when_it_ends():
    watch, first, second = WhitespaceWatch(limit=10), uuid4(), uuid4()
    watch.on_llm_new_token(" " * 9, run_id=first)
    watch.on_llm_new_token(" " * 9, run_id=second)
    watch.on_llm_end(None, run_id=first)
    watch.on_llm_new_token(" " * 9, run_id=first)  # a new count: the first ended
    watch.on_llm_error(RuntimeError("x"), run_id=second)
    watch.on_llm_new_token(" " * 9, run_id=second)


def test_one_token_written_again_and_again_stops_the_call():
    watch, run = WhitespaceWatch(repeats=5), uuid4()
    watch.on_llm_new_token('{"tip":"', run_id=run)
    for _ in range(4):
        watch.on_llm_new_token("\\n", run_id=run)  # an escaped line break inside a string
    with pytest.raises(WhitespaceRunaway, match="one token 5 times") as stopped:
        watch.on_llm_new_token("\\n", run_id=run)
    assert stopped.value.text == '{"tip":"'


def test_a_token_that_only_recurs_is_not_a_runaway():
    watch, run = WhitespaceWatch(repeats=5), uuid4()
    for _ in range(50):
        for token in ['"', ",", '"', ":"]:
            watch.on_llm_new_token(token, run_id=run)


def test_the_runaway_carries_what_was_written_before_it():
    watch, run = WhitespaceWatch(limit=10), uuid4()
    watch.on_llm_new_token('{"title":"x"', run_id=run)
    with pytest.raises(WhitespaceRunaway) as stopped:
        watch.on_llm_new_token(" " * 10, run_id=run)
    assert stopped.value.text == '{"title":"x"'


def test_a_token_that_is_not_text_is_left_alone():
    watch, run = WhitespaceWatch(limit=2), uuid4()
    watch.on_llm_new_token("", run_id=run)
    watch.on_llm_new_token([{"type": "text", "text": "   "}], run_id=run)  # content blocks


# --- through the model's stream -------------------------------------------------------------


class _Streamed(BaseChatModel):
    """A chat model that streams the tokens it is given, as `load_model`'s does."""

    tokens: list[str]
    streaming: bool = True
    sent: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "streamed"

    def _generate(self, *args: Any, **kwargs: Any) -> ChatResult:
        raise NotImplementedError

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        for token in self.tokens:
            self.sent.append(token)
            yield ChatGenerationChunk(message=AIMessageChunk(content=token))


async def test_the_watch_ends_a_streamed_call_where_the_whitespace_starts(caplog):
    caplog.set_level(logging.WARNING, logger="rext.stage_timing")
    spaces = [" " * 50] * 40  # 2,000 in a row
    model = _Streamed(tokens=['{"title":"x"', *spaces, "}"], streaming=True, sent=[])

    with pytest.raises(WhitespaceRunaway):
        await ainvoke_watched(model, [HumanMessage(content="outline")], stage="outline_model")

    # Two attempts, each stopped at the 400th space: the other 1,600 were never waited for.
    assert len(model.sent) == 2 * (1 + runaway.RUNAWAY_WHITESPACE // 50)
    assert [r.getMessage() for r in caplog.records if r.name == "rext.stage_timing"] == [
        "stage_runaway stage=outline_model reason=whitespace attempt=1 answer_kept=no",
        "stage_runaway stage=outline_model reason=whitespace attempt=2 answer_kept=no",
    ]


async def test_an_ordinary_streamed_answer_is_returned_untouched():
    model = _Streamed(
        tokens=["{", "\n  ", '"title"', ": ", '"x"', "\n", "}"], streaming=True, sent=[]
    )
    answer = await ainvoke_watched(model, [HumanMessage(content="outline")], stage="outline_model")
    assert answer.content == '{\n  "title": "x"\n}'


async def test_no_watch_is_left_on_calls_made_afterwards():
    model = _Streamed(tokens=["ok"], streaming=True, sent=[])
    await ainvoke_watched(model, [HumanMessage(content="x")], stage="intent")
    assert runaway._watch.get() is None
    spaced = _Streamed(tokens=[" " * 50] * 20, streaming=True, sent=[])
    await spaced.ainvoke([HumanMessage(content="x")])  # unwatched: nothing stops it
    assert len(spaced.sent) == 20


# --- the answer it had already written ------------------------------------------------------------


class _Plan(BaseModel):
    title: str
    steps: list[str]
    success: str = "done"
    minutes: int | None = 15
    words: int = 2000


def test_an_answer_whole_but_for_its_closing_brace_is_kept():
    # Where every runaway caught began: after the last text field, only defaults left to write.
    plan = answer_before_runaway('{"title":"x","steps":["a","b"],"success":"it works"', _Plan)
    assert plan == _Plan(title="x", steps=["a", "b"], success="it works", minutes=15, words=2000)
    assert answer_before_runaway('{"title":"x","steps":["a"],', _Plan) == _Plan(
        title="x", steps=["a"]
    )


def test_an_answer_the_model_had_closed_is_kept_as_it_stands():
    # Closed, and only then the whitespace: adding a brace would make it unreadable.
    closed = '{"title":"x","steps":["a","b"],"success":"it works","minutes":20,"words":1800}'
    assert answer_before_runaway(closed, _Plan) == _Plan(
        title="x", steps=["a", "b"], success="it works", minutes=20, words=1800
    )
    assert answer_before_runaway(closed + "\n\n", _Plan) is not None


async def test_a_call_that_ran_away_after_closing_its_answer_is_answered_from_it():
    written = ['{"title":"x",', '"steps":["a"],', '"words":1900}']
    model = _Streamed(tokens=[*written, *[" " * 50] * 40], streaming=True, sent=[])

    plan = await ainvoke_watched(
        model, [HumanMessage(content="plan")], stage="titles", schema=_Plan
    )

    assert plan == _Plan(title="x", steps=["a"], words=1900)
    assert len(model.sent) == len(written) + runaway.RUNAWAY_WHITESPACE // 50  # one attempt


@pytest.mark.parametrize(
    "text",
    [
        '{"title":"x","steps":["a","b"',  # inside a list
        '{"title":"x","steps":["a"],"success":"it wor',  # inside a string
        '{"title":"x"',  # the steps, which the schema requires, were never written
        '{"title":"x","steps":"none"',  # doesn't fit the schema
        '["a","b"',  # not the answer's object
        "",
    ],
)
def test_anything_less_is_not_an_answer(text):
    assert answer_before_runaway(text, _Plan) is None


def test_without_the_schema_nothing_is_kept():
    assert answer_before_runaway('{"title":"x","steps":["a"]', None) is None


async def test_a_call_that_ran_away_after_its_answer_is_answered_from_it(caplog):
    caplog.set_level(logging.WARNING, logger="rext.stage_timing")
    written = ['{"title":"x",', '"steps":["a","b"],', '"success":"it works"']
    model = _Streamed(tokens=[*written, *[" " * 50] * 40], streaming=True, sent=[])

    plan = await ainvoke_watched(
        model, [HumanMessage(content="plan")], stage="outline_model", schema=_Plan
    )

    assert plan == _Plan(title="x", steps=["a", "b"], success="it works")
    assert len(model.sent) == len(written) + runaway.RUNAWAY_WHITESPACE // 50  # one attempt
    assert [r.getMessage() for r in caplog.records if r.name == "rext.stage_timing"] == [
        "stage_runaway stage=outline_model reason=whitespace attempt=1 answer_kept=yes"
    ]


async def test_a_call_that_ran_away_mid_answer_is_asked_for_again():
    model = _Streamed(
        tokens=['{"title":"x",', '"steps":["a"', *[" " * 50] * 40], streaming=True, sent=[]
    )
    with pytest.raises(WhitespaceRunaway):
        await ainvoke_watched(
            model, [HumanMessage(content="plan")], stage="clustering", schema=_Plan
        )
    assert len(model.sent) == 2 * (2 + runaway.RUNAWAY_WHITESPACE // 50)  # two attempts


async def test_a_recorded_runaway_is_answered_with_its_outline(caplog):
    """A real answer, as recorded on 2026-10-07: a how-to outline written up to its last text
    field, then whitespace without end (26,402 characters of it in the longest seen)."""
    from src.flow.model.structure.outlines import get_outline_model

    caplog.set_level(logging.WARNING, logger="rext.stage_timing")
    recorded = json.loads(
        (Path(__file__).parent / "data" / "how_to_outline_before_runaway.json").read_text()
    )["written"]
    pieces = [recorded[i : i + 40] for i in range(0, len(recorded), 40)]
    model = _Streamed(tokens=[*pieces, *[" " * 50] * 528], streaming=True, sent=[])
    schema = get_outline_model("how-to-guide")

    outline = await ainvoke_watched(
        model, [HumanMessage(content="outline")], stage="outline_model", schema=schema
    )

    assert isinstance(outline, schema)
    assert outline.title and len(outline.steps.steps) == 7
    assert outline.success_definition.endswith("launch of the podcast.")
    assert outline.target_word_count == 2000  # the fields it never reached take their defaults
    # One attempt, stopped 400 characters into the whitespace: 26,000 more were never waited for.
    assert len(model.sent) == len(pieces) + runaway.RUNAWAY_WHITESPACE // 50
    assert [r.getMessage() for r in caplog.records if r.name == "rext.stage_timing"] == [
        "stage_runaway stage=outline_model reason=whitespace attempt=1 answer_kept=yes"
    ]


# --- asked once more ----------------------------------------------------------------------------


def _cut_off() -> LengthFinishReasonError:
    return LengthFinishReasonError.__new__(LengthFinishReasonError)


class _Scripted:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0

    async def ainvoke(self, _messages):
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply


@pytest.mark.parametrize("first", [WhitespaceRunaway("ran away"), _cut_off()])
async def test_a_runaway_or_a_cut_off_answer_is_asked_for_once_more(first):
    model = _Scripted(first, "the outline")
    assert await ainvoke_watched(model, [], stage="outline_model") == "the outline"
    assert model.calls == 2


async def test_a_second_runaway_is_the_callers():
    model = _Scripted(WhitespaceRunaway("one"), WhitespaceRunaway("two"), "never reached")
    with pytest.raises(WhitespaceRunaway, match="two"):
        await ainvoke_watched(model, [], stage="outline_model")
    assert model.calls == 2


async def test_a_call_that_is_itself_a_second_attempt_is_not_asked_for_again():
    model = _Scripted(WhitespaceRunaway("ran away"), "never reached")
    with pytest.raises(WhitespaceRunaway):
        await ainvoke_watched(model, [], stage="outline_model", attempts=1)
    assert model.calls == 1


async def test_any_other_error_is_not_asked_for_again():
    model = _Scripted(ValueError("bad schema"), "never reached")
    with pytest.raises(ValueError):
        await ainvoke_watched(model, [], stage="clustering")
    assert model.calls == 1


def test_a_wrapped_runaway_is_still_recognised():
    try:
        try:
            raise WhitespaceRunaway("inner")
        except WhitespaceRunaway as inner:
            raise RuntimeError("the parser failed") from inner
    except RuntimeError as wrapped:
        assert ran_away(wrapped) == "whitespace"
    assert ran_away(_cut_off()) == "cut_off"
    assert ran_away(ValueError("x")) is None


# --- the outline step ---------------------------------------------------------------------------


class _Reply:
    def __init__(self, data):
        self._data = data

    def model_dump(self):
        return dict(self._data)


def _how_to(steps):
    return {"title": "x", "steps": {"steps": [{"title": f"Step {i}"} for i in range(steps)]}}


async def _generate(monkeypatch, replies):
    """generate_outline for a How-To with the model's replies scripted, as the graph runs it
    (under stop_on_outage); returns the node's answer and the number of model calls."""
    queue = list(replies)
    calls = []

    class _Model:
        def with_structured_output(self, _schema):
            return self

        async def ainvoke(self, messages):
            calls.append(messages)
            reply = queue.pop(0)
            if isinstance(reply, BaseException):
                raise reply
            return _Reply(reply)

    async def _none(*_a, **_kw):
        return None

    async def _empty(*_a, **_kw):
        return []

    async def _no_entities(_workspace_id):
        return "", []

    async def _no_personas(*_a, **_kw):
        return None, []

    import src.flow.model.structure.outlines.render as render_module

    monkeypatch.setattr(outline_module, "load_model", lambda **_kw: _Model())
    monkeypatch.setattr(outline_module, "_fetch_known_entities", _no_entities)
    monkeypatch.setattr(outline_module, "_bulk_sync_workspace", _none)
    monkeypatch.setattr(outline_module, "_fetch_internal_links", _empty)
    monkeypatch.setattr(outline_module, "_rank_personas_for_outline", _no_personas)
    monkeypatch.setattr(outline_module, "_fetch_brand_voice_promotion", _none)
    monkeypatch.setattr(outline_module, "resolve_focus_keyword", lambda _state: "start a podcast")
    monkeypatch.setattr(
        outline_module, "build_cluster_heading_map", lambda **_kw: {"enabled": False}
    )
    monkeypatch.setattr(render_module, "normalize_outline", lambda outline, _type: {})

    state = {
        "serp_payload": {"workspace_id": None},
        "content": {
            "selected_topic": "How to start a podcast",
            "content_type": "how-to-guide",
            "outline": {"rejected_reason": "None"},
        },
    }
    node = stop_on_outage(outline_module.generate_outline.__wrapped__)
    return await node(state), len(calls)


async def test_an_outline_call_that_ran_away_is_asked_for_again(monkeypatch):
    result, calls = await _generate(monkeypatch, [WhitespaceRunaway("ran away"), _how_to(5)])

    assert calls == 2
    assert len(result["content"]["outline"]["steps"]["steps"]) == 5
    assert not result["content"].get("error")


class _SmallHowTo(BaseModel):
    title: str
    steps: dict
    target_word_count: int = 2000


async def test_an_outline_that_ran_away_after_its_last_field_is_kept(monkeypatch):
    monkeypatch.setattr(outline_module, "get_outline_model", lambda _content_type: _SmallHowTo)
    written = json.dumps(_how_to(4))[:-1]  # everything but the closing brace

    result, calls = await _generate(monkeypatch, [WhitespaceRunaway("ran away", written)])

    assert calls == 1  # not asked again: the outline was already there
    outline = result["content"]["outline"]
    assert len(outline["steps"]["steps"]) == 4
    assert outline["target_word_count"] == 2000  # the schema's own default
    assert not result["content"].get("error")


async def test_a_thin_outlines_second_attempt_makes_one_call(monkeypatch):
    # The first outline is thin (no steps), so it is asked for again; that attempt runs away.
    # It used to be asked for once more itself: up to four calls for one outline.
    result, calls = await _generate(monkeypatch, [_how_to(0), WhitespaceRunaway("ran away")])

    assert calls == 2
    assert result["content"]["outline"]["steps"]["steps"] == []  # the first one is kept


async def test_an_outline_that_runs_away_twice_ends_the_run_with_the_notice(monkeypatch):
    result, calls = await _generate(monkeypatch, [WhitespaceRunaway("one"), _cut_off()])

    assert calls == 2
    # The notice the graph ends on (provider_unavailable): no empty outline for the review step.
    assert result == {
        "content": {"error": PROVIDER_UNAVAILABLE_MESSAGE, "error_code": PROVIDER_UNAVAILABLE_CODE}
    }


async def test_an_outline_that_fails_any_other_way_ends_the_run_too(monkeypatch):
    result, calls = await _generate(monkeypatch, [ValueError("the answer didn't fit the schema")])

    assert calls == 1
    assert result["content"]["error_code"] == PROVIDER_UNAVAILABLE_CODE
    assert "outline" not in result["content"]


async def test_the_failure_names_its_kind_and_alerts_nobody(monkeypatch):
    queue = [WhitespaceRunaway("one"), WhitespaceRunaway("two")]

    class _Model:
        def with_structured_output(self, _schema):
            return self

        async def ainvoke(self, _messages):
            raise queue.pop(0)

    async def _no_entities(_workspace_id):
        return "", []

    async def _none(*_a, **_kw):
        return None

    monkeypatch.setattr(outline_module, "load_model", lambda **_kw: _Model())
    monkeypatch.setattr(outline_module, "_fetch_known_entities", _no_entities)
    monkeypatch.setattr(outline_module, "_bulk_sync_workspace", _none)
    monkeypatch.setattr(outline_module, "resolve_focus_keyword", lambda _state: "start a podcast")
    monkeypatch.setattr(
        outline_module, "build_cluster_heading_map", lambda **_kw: {"enabled": False}
    )
    state = {
        "serp_payload": {"workspace_id": None},
        "content": {"selected_topic": "How to start a podcast", "content_type": "how-to-guide"},
    }

    with pytest.raises(ProviderUnavailable) as stopped:
        await outline_module.generate_outline.__wrapped__(state)

    assert stopped.value.outage.kind == UNREADABLE_ANSWER
    assert provider_outage(stopped.value).kind == UNREADABLE_ANSWER
    assert STEP_FAILED != UNREADABLE_ANSWER


async def test_an_outline_that_cant_be_written_takes_no_credits(monkeypatch):
    import src.utils.credit_manager as credits

    charged = []

    async def balance(_user, _workspace):
        return 100

    async def consume(*args, **kwargs):
        charged.append(args)

    monkeypatch.setattr(credits, "_get_balance", balance)
    monkeypatch.setattr(credits, "consume_stage_credits", consume)
    queue = [WhitespaceRunaway("one"), _cut_off()]

    class _Model:
        def with_structured_output(self, _schema):
            return self

        async def ainvoke(self, _messages):
            raise queue.pop(0)

    async def _no_entities(_workspace_id):
        return "", []

    async def _none(*_a, **_kw):
        return None

    monkeypatch.setattr(outline_module, "load_model", lambda **_kw: _Model())
    monkeypatch.setattr(outline_module, "_fetch_known_entities", _no_entities)
    monkeypatch.setattr(outline_module, "_fetch_workspace_profile", _none)
    monkeypatch.setattr(outline_module, "_bulk_sync_workspace", _none)
    monkeypatch.setattr(outline_module, "resolve_focus_keyword", lambda _state: "start a podcast")
    monkeypatch.setattr(
        outline_module, "build_cluster_heading_map", lambda **_kw: {"enabled": False}
    )
    state = {
        "serp_payload": {"workspace_id": None, "user_id": str(uuid4())},
        "content": {"selected_topic": "How to start a podcast", "content_type": "how-to-guide"},
    }

    # The node as the graph runs it: the charge around it, the notice outside.
    result = await stop_on_outage(outline_module.generate_outline)(state)

    assert result["content"]["error_code"] == PROVIDER_UNAVAILABLE_CODE
    assert not queue and charged == []


# --- what a stop is not ---------------------------------------------------------------------------


async def test_a_stop_by_the_watch_is_not_recorded_as_a_provider_failure(monkeypatch):
    import src.flow.model.llm_manager as llm_manager

    recorded = []

    async def report(service, error):
        recorded.append(type(error).__name__)

    monkeypatch.setattr(llm_manager, "_report_ai_failure", report)
    reporters = llm_manager._reporters("OpenAI")  # the async one, and the sync one

    for reporter in reporters:
        stopped = reporter.on_llm_error(WhitespaceRunaway("ran away"))
        if stopped is not None:
            await stopped
    await asyncio.sleep(0.05)  # the sync reporter hands its report to the loop
    assert recorded == []

    # A real failure is still recorded by both: an answer cut off at the provider's limit.
    for reporter in reporters:
        failed = reporter.on_llm_error(_cut_off())
        if failed is not None:
            await failed
    await asyncio.sleep(0.05)
    assert recorded == ["LengthFinishReasonError", "LengthFinishReasonError"]


async def test_the_query_only_intent_call_has_one_more_attempt_not_three(monkeypatch):
    import src.flow.engines.serp.competitor as competitor

    calls = []

    class _Model:
        def with_structured_output(self, _schema):
            return self

        async def ainvoke(self, messages):
            calls.append(messages)
            raise WhitespaceRunaway("ran away")

    monkeypatch.setattr(competitor, "load_model", lambda **_kw: _Model())

    with pytest.raises(WhitespaceRunaway):
        await competitor._classify_competitor_intents("crm for small business", {})

    assert len(calls) == 2  # it used to go on to the competitors' call, and ask twice more


# --- every structured call on the way to an article ---------------------------------------------

WATCHED_CALLS = {
    "src/flow/engines/serp/competitor.py": 2,  # the intent of the search results
    "src/services/keyword_clustering_service.py": 1,
    "src/flow/engines/content/generation/topic_generation.py": 2,  # the titles, and their repair
    "src/flow/engines/content/generation/outline.py": 2,  # the outline, and its second attempt
    "src/flow/engines/content/generation/subheading_seo.py": 1,
    "src/flow/engines/content/utils/eeat.py": 1,
    "src/flow/engines/content/generation/humanize_content.py": 1,
    "src/flow/engines/content/generation/repair_content.py": 1,
}


@pytest.mark.parametrize(("path", "calls"), WATCHED_CALLS.items())
def test_the_structured_calls_of_a_run_are_made_under_the_watch(path, calls):
    source = (Path(__file__).resolve().parents[3] / path).read_text()
    assert source.count("ainvoke_watched(") == calls
    # A new structured call written as `await model.ainvoke(...)` would run unwatched.
    assert not re.search(r"await \w+\.ainvoke\(", source)


def test_the_outline_is_asked_for_as_compact_json():
    from src.flow.prompts.human.outline import get_outline_prompt

    human = get_outline_prompt().messages[1].prompt.template
    assert "written compactly: no indentation, no line breaks" in human
