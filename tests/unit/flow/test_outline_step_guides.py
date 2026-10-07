"""A How-To or tutorial outline that comes back with fewer than 3 steps is asked for once more.

On staging (rext-control#603) one How-To outline came back with one step and another with
none at all, tools included. Structured output here isn't strict, so the schema can't require
steps without failing the run; generate_outline retries once instead, only when it's thin.
"""

import pytest

import src.flow.engines.content.generation.outline as outline_module


@pytest.mark.unit
@pytest.mark.parametrize(
    ("content_type", "outline", "expected"),
    [
        ("how-to-guide", {"steps": {"steps": []}}, "had 0 steps"),
        ("how-to-guide", {"steps": {"steps": [{"title": "Gather"}]}}, "had 1 step"),
        ("tutorial", {"modules": {"modules": []}, "steps": None}, "had 0 modules"),
        ("tutorial", {"modules": {"modules": [{"title": "Basics"}]}, "steps": None}, None),
        ("how-to-guide", {"steps": {"steps": [{}, {}, {}]}}, None),
        ("blog", {"structure": {"sections": []}}, None),
    ],
)
def test_a_step_guide_without_steps_is_thin(content_type, outline, expected):
    assert outline_module._thin_structure(content_type, outline) == expected


class _Reply:
    def __init__(self, data):
        self._data = data

    def model_dump(self):
        return dict(self._data)


async def _generate(monkeypatch, content_type, replies):
    """generate_outline with the model's replies scripted; returns the outline and each call's messages."""
    calls = []
    queue = list(replies)

    class _Model:
        def with_structured_output(self, _schema):
            return self

        async def ainvoke(self, messages):
            calls.append(messages)
            reply = queue.pop(0)
            if isinstance(reply, Exception):
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
            "content_type": content_type,
            "outline": {"rejected_reason": "None"},
        },
    }
    result = await outline_module.generate_outline.__wrapped__(state)
    return result["content"]["outline"], calls


def _how_to(steps):
    return {"title": "x", "steps": {"steps": [{"title": f"Step {i}"} for i in range(steps)]}}


@pytest.mark.unit
async def test_an_empty_how_to_is_asked_for_once_more(monkeypatch):
    outline, calls = await _generate(monkeypatch, "how-to-guide", [_how_to(0), _how_to(5)])

    assert len(outline["steps"]["steps"]) == 5
    assert len(calls) == 2
    note = calls[1][-1].content
    assert calls[1][:-1] == calls[0]
    assert note.startswith("A first attempt at this outline had 0 steps.")


@pytest.mark.unit
async def test_the_retry_happens_once_at_most(monkeypatch):
    outline, calls = await _generate(monkeypatch, "how-to-guide", [_how_to(1), _how_to(2)])

    assert len(outline["steps"]["steps"]) == 2
    assert len(calls) == 2


@pytest.mark.unit
async def test_a_full_how_to_costs_one_call(monkeypatch):
    outline, calls = await _generate(monkeypatch, "how-to-guide", [_how_to(4)])

    assert len(outline["steps"]["steps"]) == 4
    assert len(calls) == 1


@pytest.mark.unit
async def test_a_tutorial_with_modules_and_no_steps_costs_one_call(monkeypatch):
    """Its steps are an optional deeper breakdown: the modules are the tutorial."""
    tutorial = {"title": "x", "modules": {"modules": [{"title": "Basics"}]}, "steps": None}

    outline, calls = await _generate(monkeypatch, "tutorial", [tutorial])

    assert outline["modules"]["modules"] == [{"title": "Basics"}]
    assert len(calls) == 1


@pytest.mark.unit
async def test_a_thinner_second_attempt_keeps_the_first(monkeypatch):
    outline, calls = await _generate(monkeypatch, "how-to-guide", [_how_to(2), _how_to(0)])

    assert len(outline["steps"]["steps"]) == 2
    assert len(calls) == 2


@pytest.mark.unit
async def test_a_failed_second_attempt_keeps_the_first(monkeypatch):
    failure = RuntimeError("the model returned nothing usable")

    outline, calls = await _generate(monkeypatch, "how-to-guide", [_how_to(1), failure])

    assert len(outline["steps"]["steps"]) == 1
    assert len(calls) == 2
