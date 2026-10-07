"""The outline step, lighter (rext-control#697): the models write nothing that is thrown away,
a regeneration is shown the rejected plan only, and the step's remaining parts log their time."""

import logging

import pytest

import src.flow.engines.content.generation.outline as outline_module
import src.services.keyword_clustering_service as clustering_module
from src.flow.model.structure.intent import SEOIntentOutput, SEOIntentResult
from src.flow.model.structure.keyword_clustering import (
    ClusterKeywordItem,
    KeywordClusterGroup,
    KeywordClusteringLLMOutput,
)

pytestmark = pytest.mark.unit


# --- what the models no longer write ----------------------------------------------------


def test_the_intent_call_writes_no_confidence():
    # One word per search result, on every analysis, that nothing read.
    assert "confidence" not in SEOIntentOutput.model_fields


def test_a_cached_intent_answer_from_before_still_loads():
    kept = {"domain": "a.test", "intent": "COMMERCIAL", "confidence": "high", "is_brand": True}
    result = SEOIntentResult(**kept)
    assert (result.domain, result.intent, result.is_brand) == ("a.test", "COMMERCIAL", True)


def test_the_clustering_call_writes_no_page_type():
    # The page type of a cluster is worked out from its keywords; the model's was overwritten.
    assert "likely_serp_page_type" not in KeywordClusterGroup.model_fields
    assert "12 words" in KeywordClusterGroup.model_fields["rationale"].description


async def test_the_clusters_are_built_without_the_models_page_type(monkeypatch):
    asked = []

    class _Model:
        def with_structured_output(self, schema):
            assert schema is KeywordClusteringLLMOutput
            return self

        async def ainvoke(self, messages):
            asked.append(messages)
            return KeywordClusteringLLMOutput(
                clusters=[
                    KeywordClusterGroup(
                        cluster_name="podcast equipment",
                        topic_theme="equipment",
                        intent="INFORMATIONAL",
                        keywords=[
                            ClusterKeywordItem(keyword="Podcast Microphone", relevance_score=90),
                            ClusterKeywordItem(keyword="not a candidate", relevance_score=99),
                        ],
                        rationale="Both are gear a new podcaster buys",
                        natural_heading="What equipment you need",
                        outline_placement="H2",
                        intent_match_score=88,
                    )
                ]
            )

    monkeypatch.setattr(clustering_module, "load_model", lambda: _Model())

    clusters = await clustering_module.KeywordClusteringService()._cluster_with_llm(
        keywords_data=[{"keyword": "podcast microphone", "score": 70}],
        query="how to start a podcast",
        primary_intent="informational",
        primary_intent_upper="INFORMATIONAL",
        intent_matched_signals={},
        content_type="how-to-guide",
        selected_topic="How to start a podcast",
    )

    assert [k["keyword"] for k in clusters[0]["keywords"]] == ["podcast microphone"]
    assert clusters[0]["rationale"] == "Both are gear a new podcaster buys"
    assert clusters[0]["recommended_heading"] == "What equipment you need"
    assert "likely_serp_page_type" not in clusters[0]  # _score_and_filter_clusters sets it
    request = asked[0][-1].content
    assert "outline placement" in request and "one-phrase rationale" in request
    assert "provide a natural heading, likely SERP page type" not in request


# --- the outline call ---------------------------------------------------------------------


class _Reply:
    def __init__(self, data):
        self._data = data

    def model_dump(self):
        return dict(self._data)


async def _generate(monkeypatch, replies, stored_outline):
    """generate_outline for a How-To with the model's replies scripted; returns each call's messages."""
    calls = []
    queue = list(replies)

    class _Model:
        def with_structured_output(self, _schema):
            return self

        async def ainvoke(self, messages):
            calls.append(messages)
            return _Reply(queue.pop(0))

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
            "outline": stored_outline,
        },
    }
    await outline_module.generate_outline.__wrapped__(state)
    return calls


def _how_to(steps):
    return {"title": "x", "steps": {"steps": [{"title": f"Step {i}"} for i in range(steps)]}}


REJECTED = {
    "title": "How to start a podcast",
    "steps": {"steps": [{"title": "Pick the REJECTED-PLAN topic"}]},
    "target_word_count": 1800,
    "_render": {"sections": [{"heading": "DISPLAY-COPY of the plan"}]},
    "cluster_heading_map": {"sections": [{"heading": "HEADING-MAP entry"}]},
    "internal_links": [{"title": "EVERY-PUBLISHED-ARTICLE", "url": "https://a.test/x"}],
    "persona_recommendations": [{"persona_id": "p1", "name": "PERSONA-LIST entry"}],
    "selected_persona_id": "p1",
    "brand_voice_promotion": {"brand_name": "BRAND-FIT entry"},
    "rejected_reason": "Make it shorter",
    "status": "rejected",
    "iteration_count": 1,
}


def test_a_rejected_outline_is_shown_as_its_plan():
    shown = outline_module._previous_outline_for_prompt(REJECTED)
    assert shown == {
        "title": "How to start a podcast",
        "steps": {"steps": [{"title": "Pick the REJECTED-PLAN topic"}]},
        "target_word_count": 1800,
    }
    assert outline_module._previous_outline_for_prompt(None) == {}
    assert outline_module._previous_outline_for_prompt({"rejected_reason": "None"}) == {}


async def test_a_regeneration_reads_the_plan_and_none_of_the_lookups(monkeypatch):
    calls = await _generate(monkeypatch, [_how_to(4)], dict(REJECTED))

    prompt = "\n".join(m.content for m in calls[0])
    assert "Previous Rejection Reason: Make it shorter" in prompt
    assert "REJECTED-PLAN" in prompt
    for dropped in (
        "DISPLAY-COPY",
        "HEADING-MAP",
        "EVERY-PUBLISHED-ARTICLE",
        "PERSONA-LIST",
        "BRAND-FIT",
        "iteration_count",
    ):
        assert dropped not in prompt


# --- the timing lines -------------------------------------------------------------------


def _timing_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.name == "rext.stage_timing"]


async def test_the_lookups_after_the_outline_log_their_time(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="rext.stage_timing")

    await _generate(monkeypatch, [_how_to(4)], {"rejected_reason": "None"})

    stages = [line.split()[1] for line in _timing_lines(caplog)]
    assert stages == ["stage=outline_model", "stage=outline_lookups"]


async def test_a_second_attempt_logs_its_own_time(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="rext.stage_timing")

    await _generate(monkeypatch, [_how_to(0), _how_to(5)], {"rejected_reason": "None"})

    lines = _timing_lines(caplog)
    assert [line.split()[1] for line in lines] == [
        "stage=outline_model",
        "stage=outline_model",
        "stage=outline_lookups",
    ]
    assert lines[1].endswith(" outcome=ok regenerating=False attempt=2")
