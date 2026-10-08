"""A How-To or tutorial outline that comes back with fewer than 3 steps is asked for once more.

On staging (rext-control#603) one How-To outline came back with one step and another with
none at all, tools included. Structured output here isn't strict, so the schema can't require
steps without failing the run; generate_outline retries once instead, only when it's thin.
"""

import json

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


async def _generate(monkeypatch, content_type, replies, rejected_reason="None", previous=None):
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
            # A regeneration's state holds the outline the reviewer rejected.
            "outline": {**(previous or {}), "rejected_reason": rejected_reason},
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


@pytest.mark.unit
async def test_a_reviewers_shorter_how_to_is_kept(monkeypatch):
    """Their own ask sets the length: two steps on request isn't thin."""
    outline, calls = await _generate(
        monkeypatch, "how-to-guide", [_how_to(2)], rejected_reason="Combine it into two steps"
    )

    assert len(outline["steps"]["steps"]) == 2
    assert len(calls) == 1


@pytest.mark.unit
async def test_an_empty_how_to_after_feedback_is_still_asked_for_again(monkeypatch):
    outline, calls = await _generate(
        monkeypatch, "how-to-guide", [_how_to(0), _how_to(2)], rejected_reason="Make it shorter"
    )

    assert len(outline["steps"]["steps"]) == 2
    assert len(calls) == 2


@pytest.mark.unit
async def test_an_outage_during_the_second_attempt_is_the_runs_to_report(monkeypatch):
    """Not swallowed: the run shows its outage notice, never a thin outline it charged for."""
    outage = RuntimeError("the provider is down")
    monkeypatch.setattr(
        outline_module, "provider_outage", lambda error: "outage" if error is outage else None
    )

    with pytest.raises(RuntimeError, match="the provider is down"):
        await _generate(monkeypatch, "how-to-guide", [_how_to(1), outage])


# -- Pillar content without H3 subsections (rext-control#603's staging proof) --------------------
# The rule expects them and the schema holds them, but two pillar outlines of two came back with
# H2s only. Such an outline is asked for once more, the way an empty step guide is.


def _pillar(*levels, marker="first", keeps=None):
    """An outline of these levels. With ``keeps`` (the attempt before), its H2s take that one's
    H2 headings in order, as a model asked to keep every main section would write them."""
    kept = iter(
        section["heading"]
        for section in (keeps or {}).get("structure", {}).get("sections", [])
        if section["heading_level"] == "H2"
    )
    return {
        "title": "x",
        "structure": {
            "sections": [
                {
                    "heading": (next(kept, None) if level == "H2" else None) or f"{marker} {index}",
                    "heading_level": level,
                }
                for index, level in enumerate(levels)
            ]
        },
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    ("outline", "fewer", "expected"),
    [
        (_pillar("H2", "H2"), False, "had 0 H3 subsections"),
        (_pillar("H2", "H3", "H2"), False, None),
        (_pillar("H2", "h3"), False, None),
        # An H3 before any H2 is under no section: not a subsection.
        (_pillar("H3", "H2", "H2"), False, "had 0 H3 subsections"),
        # The reviewer asked for fewer: none is what was asked for.
        (_pillar("H2", "H2"), True, None),
        ({"title": "x"}, False, "had 0 H3 subsections"),
    ],
)
def test_a_pillar_outline_without_subsections_is_thin(outline, fewer, expected):
    thin = outline_module._thin_structure("pillar-content", outline, no_subsections_asked=fewer)
    assert thin == expected


@pytest.mark.unit
def test_a_blog_without_subsections_is_not_thin():
    """Its rule goes by the article's shape: a short blog may have none."""
    assert outline_module._thin_structure("blog", _pillar("H2", "H2")) is None


@pytest.mark.unit
async def test_a_pillar_outline_of_h2s_only_is_asked_for_once_more(monkeypatch):
    # Four main sections, as a pillar outline has: with fewer, the holding step that follows
    # (outline_depth.py) raises H3s to H2 until there are four, and this is about the retry.
    first = _pillar("H2", "H2", "H2", "H2")
    second = _pillar("H2", "H3", "H3", "H2", "H2", "H2", marker="second", keeps=first)

    outline, calls = await _generate(monkeypatch, "pillar-content", [first, second])

    levels = [section["heading_level"] for section in outline["structure"]["sections"]]
    assert levels == ["H2", "H3", "H3", "H2", "H2", "H2"]
    assert len(calls) == 2
    note = calls[1][-1].content
    # The second call is the first one, the model's own outline, and what to add to it.
    assert calls[1][:-2] == calls[0]
    assert (
        json.loads(calls[1][-2].content)["structure"]["sections"] == first["structure"]["sections"]
    )
    assert note.startswith("A first attempt at this outline had 0 H3 subsections.")
    assert 'heading_level "H3"' in note
    assert "Keep every H2 section it has" in note


def _planned(*sections):
    """A pillar outline as the model writes it: H2s, each with its parts as key points."""
    return {
        "title": "x",
        "structure": {
            "sections": [
                {
                    "heading": heading,
                    "heading_level": "H2",
                    "purpose": f"Why {heading}",
                    "key_points": list(points),
                }
                for heading, points in sections
            ]
        },
    }


@pytest.mark.unit
async def test_a_pillar_outlines_key_points_become_its_subsections_without_a_second_call(
    monkeypatch,
):
    first = _planned(
        ("Plan", ["Pick one goal.", "Choose who it is for"]),
        ("Write", ["Subject lines", "The first sentence", "One call to action"]),
        ("Send", ["When to send"]),
        ("Measure", []),
    )

    outline, calls = await _generate(monkeypatch, "pillar-content", [first])

    sections = outline["structure"]["sections"]
    assert [(section["heading_level"], section["heading"]) for section in sections] == [
        ("H2", "Plan"),
        ("H3", "Pick one goal"),
        ("H3", "Choose who it is for"),
        ("H2", "Write"),
        ("H3", "Subject lines"),
        ("H3", "The first sentence"),
        ("H3", "One call to action"),
        ("H2", "Send"),
        ("H2", "Measure"),
    ]
    # A part is planned once: it left its section's key points; one that stands alone stays.
    assert sections[0]["key_points"] == []
    assert sections[7]["key_points"] == ["When to send"]
    # Each subsection has a purpose of its own, the point as it was written, and no parts.
    assert sections[1]["purpose"] == "Pick one goal."
    assert sections[2]["purpose"] == "Choose who it is for"
    assert sections[1]["key_points"] == []
    assert len(calls) == 1


@pytest.mark.unit
def test_only_the_first_key_points_become_subsections_and_the_rest_stay():
    outline = _planned(
        ("Plan", ["a", "b", "c", "d", "e", "f"]),
        ("Write", []),
        ("Send", ["only one"]),
        ("Measure", []),
    )

    made = outline_module._subsections_from_key_points(outline)

    sections = outline["structure"]["sections"]
    assert made == 4
    assert [section["heading"] for section in sections] == [
        "Plan",
        "a",
        "b",
        "c",
        "d",
        "Write",
        "Send",
        "Measure",
    ]
    assert sections[0]["key_points"] == ["e", "f"]


@pytest.mark.unit
def test_a_key_point_written_as_a_sentence_stays_a_key_point():
    sentence = (
        "Explain how list quality affects deliverability when a sender warms up a new domain."
    )
    two = "Start small. Then grow the list."
    outline = _planned(
        ("Plan", ["Segmentation of email lists", sentence, "Personalization techniques", two]),
        ("Send", [sentence, "When to send"]),
        ("Write", []),
        ("Measure", []),
    )

    made = outline_module._subsections_from_key_points(outline)

    sections = outline["structure"]["sections"]
    assert made == 2
    assert [section["heading"] for section in sections] == [
        "Plan",
        "Segmentation of email lists",
        "Personalization techniques",
        "Send",
        "Write",
        "Measure",
    ]
    # What is no heading stays where it was, as it was written; a section with one
    # heading-shaped point is left whole.
    assert sections[0]["key_points"] == [sentence, two]
    assert sections[3]["key_points"] == [sentence, "When to send"]


@pytest.mark.unit
async def test_a_pillar_outline_short_of_four_main_sections_gets_no_subsections_from_its_points(
    monkeypatch,
):
    """The holding step would raise them to main sections: such an outline is asked for again."""
    first = _planned(
        ("Plan", ["Pick one goal", "Choose who it is for"]),
        ("Write", ["Subject lines", "The first sentence"]),
        ("Send", ["When to send", "How often"]),
    )
    assert outline_module._subsections_from_key_points(_planned(("Plan", ["a", "b"]))) == 0

    outline, calls = await _generate(monkeypatch, "pillar-content", [first, first])

    assert len(calls) == 2
    assert all(section["heading_level"] == "H2" for section in outline["structure"]["sections"])


@pytest.mark.unit
def test_subsections_are_made_only_while_the_articles_target_stays_where_it_is():
    from src.flow.model.structure.outlines import get_outline_model

    schema = get_outline_model("pillar-content")
    outline = _planned(*[(f"Section {n}", ["a", "b", "c", "d"]) for n in range(7)])
    sections = outline["structure"]["sections"]
    target = outline_module._summed_word_target(schema, sections)
    room = outline_module._room_for_subsections(schema, sections)

    # One more entry than the room would move the target (or pass the writer's limit).
    assert outline_module._summed_word_target(schema, [*sections, *([{}] * room)]) == target
    assert (
        outline_module._summed_word_target(schema, [*sections, *([{}] * (room + 1))]) != target
        or len(sections) + room == outline_module.MAX_EXPANDED_SECTIONS
    )

    made = outline_module._subsections_from_key_points(outline, room=room)

    assert 0 < made <= room
    assert outline_module._summed_word_target(schema, outline["structure"]["sections"]) == target
    assert len(outline["structure"]["sections"]) <= outline_module.MAX_EXPANDED_SECTIONS
    # Served in order: the first sections have theirs, and none has a single one.
    families = []
    for section in outline["structure"]["sections"]:
        if section["heading_level"] == "H2":
            families.append(0)
        else:
            families[-1] += 1
    assert families[0] == 4 and 1 not in families


@pytest.mark.unit
def test_no_room_leaves_the_outline_whole():
    outline = _planned(*[(f"Section {n}", ["a", "b"]) for n in range(4)])

    assert outline_module._subsections_from_key_points(outline, room=1) == 0
    assert len(outline["structure"]["sections"]) == 4


@pytest.mark.unit
def test_an_outline_whose_sections_have_no_parts_is_left_as_it_is():
    outline = _pillar("H2", "H2", "H2", "H2")
    before = [dict(section) for section in outline["structure"]["sections"]]

    assert outline_module._subsections_from_key_points(outline) == 0
    assert outline["structure"]["sections"] == before


@pytest.mark.unit
async def test_a_pillar_outline_with_subsections_costs_one_call(monkeypatch):
    pillar = _pillar("H2", "H3", "H2", "H2", "H2")

    outline, calls = await _generate(monkeypatch, "pillar-content", [pillar])

    levels = [section["heading_level"] for section in outline["structure"]["sections"]]
    assert levels == ["H2", "H3", "H2", "H2", "H2"]
    assert len(calls) == 1


@pytest.mark.unit
async def test_a_retried_pillar_outline_short_of_four_main_sections_is_still_held(monkeypatch):
    """The retry and the holding step in their order: the second attempt takes the first one's
    place for its subsections, and is then held to four main sections like any first outline."""
    first = _pillar("H2", "H2")
    second = _pillar("H2", "H3", "H3", "H2", "H3", "H3", marker="second", keeps=first)

    outline, calls = await _generate(monkeypatch, "pillar-content", [first, second])

    sections = outline["structure"]["sections"]
    assert [section["heading"] for section in sections] == [
        "first 0",
        "second 1",
        "second 2",
        "first 1",
        "second 4",
        "second 5",
    ]
    assert [section["heading_level"] for section in sections] == [
        "H2",
        "H2",
        "H2",
        "H2",
        "H3",
        "H3",
    ]
    assert len(calls) == 2


@pytest.mark.unit
async def test_a_second_pillar_attempt_without_subsections_keeps_the_first(monkeypatch):
    again = _pillar("H2", marker="second")

    outline, calls = await _generate(monkeypatch, "pillar-content", [_pillar("H2", "H2"), again])

    assert [section["heading"] for section in outline["structure"]["sections"]] == [
        "first 0",
        "first 1",
    ]
    assert len(calls) == 2


@pytest.mark.unit
async def test_a_reviewer_who_asked_for_fewer_subsections_gets_none_without_a_retry(monkeypatch):
    outline, calls = await _generate(
        monkeypatch,
        "pillar-content",
        [_pillar("H2", "H2")],
        rejected_reason="Remove the H3s, keep it to main sections",
    )

    assert len(outline["structure"]["sections"]) == 2
    assert len(calls) == 1


@pytest.mark.unit
async def test_other_feedback_on_a_pillar_outline_still_expects_subsections(monkeypatch):
    first = _pillar("H2", "H2")
    second = _pillar("H2", "H3", "H2", marker="second", keeps=first)

    outline, calls = await _generate(
        monkeypatch,
        "pillar-content",
        [first, second],
        rejected_reason="Make the tone friendlier",
    )

    assert outline["structure"]["sections"][1]["heading_level"] == "H3"
    assert len(calls) == 2


@pytest.mark.unit
async def test_a_second_pillar_attempt_that_folds_main_sections_but_keeps_four_is_taken(
    monkeypatch,
):
    """Adding H3s, a model often folds two H2s into one: four main sections are still an article."""
    first = _pillar("H2", "H2", "H2", "H2", "H2", "H2")
    # The second and the fourth H2 of the first are now H3s under the ones before them.
    folded = ["H2", "H3", "H3", "H2", "H3", "H3", "H2", "H2"]
    names = ["first 0", "first 1", "new 2", "first 2", "first 3", "new 5", "first 4", "first 5"]
    second = {
        "title": "x",
        "structure": {
            "sections": [
                {"heading": name, "heading_level": level} for name, level in zip(names, folded)
            ]
        },
    }

    outline, calls = await _generate(monkeypatch, "pillar-content", [first, second])

    sections = outline["structure"]["sections"]
    assert [section["heading"] for section in sections] == names
    assert [section["heading_level"] for section in sections] == [
        "H2",
        "H3",
        "H3",
        "H2",
        "H3",
        "H3",
        "H2",
        "H2",
    ]
    assert len(calls) == 2


@pytest.mark.unit
async def test_a_second_pillar_attempt_that_drops_sections_for_one_subsection_keeps_the_first(
    monkeypatch,
):
    """Four H2s and one H3 where there were six H2s: topics were dropped, not folded."""
    second = _pillar("H2", "H3", "H2", "H2", "H2", marker="second")

    outline, calls = await _generate(
        monkeypatch, "pillar-content", [_pillar("H2", "H2", "H2", "H2", "H2", "H2"), second]
    )

    assert [section["heading"] for section in outline["structure"]["sections"]] == [
        f"first {i}" for i in range(6)
    ]
    assert len(calls) == 2


@pytest.mark.unit
async def test_a_second_pillar_attempt_that_loses_a_main_section_keeps_the_first(monkeypatch):
    """More entries than the first, but two of its topics are in none of them."""
    first = _pillar("H2", "H2", "H2", "H2", "H2", "H2")
    second = _pillar("H2", "H3", "H3", "H2", "H3", "H2", "H2", marker="second", keeps=first)

    outline, calls = await _generate(monkeypatch, "pillar-content", [first, second])

    assert [section["heading"] for section in outline["structure"]["sections"]] == [
        f"first {i}" for i in range(6)
    ]
    assert len(calls) == 2


def _named(*sections):
    return {
        "title": "x",
        "structure": {
            "sections": [
                {"heading": heading, "heading_level": level} for heading, level in sections
            ]
        },
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    "topics",
    [
        ["Введение", "Стратегия", "Шаблоны", "Метрики", "Автоматизация"],
        ["入门指南", "营销策略", "邮件模板", "效果衡量", "自动化流程"],
    ],
)
async def test_main_sections_are_known_by_their_words_in_any_script(monkeypatch, topics):
    first = _named(*[(topic, "H2") for topic in topics])
    # Four H2s and H3s, with the first outline's last topic nowhere in it.
    lost = _named(
        (topics[0], "H2"),
        ("a", "H3"),
        ("b", "H3"),
        (topics[1], "H2"),
        (topics[2], "H2"),
        (topics[3], "H2"),
    )
    # The second topic folded under the first, the order as it was.
    kept = _named(
        (topics[0], "H2"),
        (topics[1], "H3"),
        ("b", "H3"),
        (topics[2], "H2"),
        (topics[3], "H2"),
        (topics[4], "H2"),
    )

    outline, _ = await _generate(monkeypatch, "pillar-content", [first, lost])
    assert len(outline["structure"]["sections"]) == 5

    outline, _ = await _generate(monkeypatch, "pillar-content", [first, kept])
    assert [section["heading_level"] for section in outline["structure"]["sections"]] == [
        "H2",
        "H3",
        "H3",
        "H2",
        "H2",
        "H2",
    ]


@pytest.mark.unit
async def test_a_second_pillar_attempt_that_reorders_the_main_sections_keeps_the_first(
    monkeypatch,
):
    first = _named(("Plan", "H2"), ("Write", "H2"), ("Send", "H2"), ("Measure", "H2"))
    moved = _named(
        ("Plan", "H2"),
        ("a", "H3"),
        ("b", "H3"),
        ("Send", "H2"),
        ("Write", "H2"),
        ("Measure", "H2"),
    )

    outline, calls = await _generate(monkeypatch, "pillar-content", [first, moved])

    assert [section["heading"] for section in outline["structure"]["sections"]] == [
        "Plan",
        "Write",
        "Send",
        "Measure",
    ]
    assert len(calls) == 2


@pytest.mark.unit
def test_a_heading_keeps_the_marks_that_make_its_words():
    """A vowel sign makes another word: two topics never fall together, and case and
    punctuation never keep two wordings of one apart."""
    key = outline_module._heading_key
    assert key({"heading": "कला"}) != key({"heading": "कल"})
    assert key({"heading": "Email Marketing: Tips & Tricks"}) == key(
        {"heading": "email marketing tips tricks"}
    )
    assert key({"heading": "  —  "}) == ""


@pytest.mark.unit
async def test_a_second_pillar_attempt_with_fewer_than_four_main_sections_keeps_the_first(
    monkeypatch,
):
    second = _pillar("H2", "H3", "H3", "H2", "H3", "H2", marker="second")

    outline, calls = await _generate(
        monkeypatch, "pillar-content", [_pillar("H2", "H2", "H2", "H2", "H2", "H2"), second]
    )

    assert [section["heading"] for section in outline["structure"]["sections"]] == [
        f"first {i}" for i in range(6)
    ]
    assert len(calls) == 2


@pytest.mark.unit
async def test_a_shorter_second_pillar_attempt_keeps_the_first(monkeypatch):
    """It brought a subsection but lost main sections: the fuller plan stays."""
    shorter = _pillar("H2", "H3", marker="second")

    outline, calls = await _generate(
        monkeypatch, "pillar-content", [_pillar("H2", "H2", "H2"), shorter]
    )

    assert [section["heading"] for section in outline["structure"]["sections"]] == [
        "first 0",
        "first 1",
        "first 2",
    ]
    assert len(calls) == 2


@pytest.mark.unit
async def test_feedback_about_one_subsection_leaves_the_others_expected(monkeypatch):
    """Removing the H3 under the introduction isn't removing them all."""
    first = _pillar("H2", "H2")
    second = _pillar("H2", "H2", "H3", "H3", marker="second", keeps=first)

    outline, calls = await _generate(
        monkeypatch,
        "pillar-content",
        [first, second],
        rejected_reason="Remove the H3 under the introduction",
        previous=_pillar("H2", "H3", "H2", "H3", "H3", marker="rejected"),
    )

    assert outline["structure"]["sections"][2]["heading_level"] == "H3"
    assert len(calls) == 2


@pytest.mark.unit
async def test_feedback_that_removes_the_only_subsection_gets_none_without_a_retry(monkeypatch):
    outline, calls = await _generate(
        monkeypatch,
        "pillar-content",
        [_pillar("H2", "H2")],
        rejected_reason="Remove the H3 under the introduction",
        previous=_pillar("H2", "H3", "H2", marker="rejected"),
    )

    assert len(outline["structure"]["sections"]) == 2
    assert len(calls) == 1


@pytest.mark.unit
async def test_feedback_about_the_subsections_of_one_section_leaves_the_others(monkeypatch):
    first = _pillar("H2", "H2")
    second = _pillar("H2", "H2", "H3", "H3", marker="second", keeps=first)

    outline, calls = await _generate(
        monkeypatch,
        "pillar-content",
        [first, second],
        rejected_reason="Remove the H3s under the introduction",
        previous=_pillar("H2", "H3", "H3", "H2", "H3", "H3", marker="rejected"),
    )

    assert outline["structure"]["sections"][2]["heading_level"] == "H3"
    assert len(calls) == 2


# -- A blog's plan inside the range the product shows for a blog (rext-control#837) ---------


def _blog(*budgets, minutes=None):
    outline = {
        "title": "x",
        "structure": {
            "sections": [
                {"heading": f"Part {n}", "heading_level": "H2", "suggested_word_count": words}
                for n, words in enumerate(budgets, 1)
            ]
        },
    }
    if minutes is not None:
        outline["target_reading_time_minutes"] = minutes
    return outline


@pytest.mark.unit
async def test_a_blog_planned_over_its_range_comes_back_inside_it_with_its_reading_time(
    monkeypatch,
):
    outline, calls = await _generate(
        monkeypatch, "blog", [_blog(400, 400, 400, 400, 400, 400, 400, 400, minutes=16)]
    )

    budgets = [section["suggested_word_count"] for section in outline["structure"]["sections"]]
    assert budgets == [250] * 8
    assert outline["target_word_count"] == 2000
    # 16 minutes was for 3,200 words: 2,000 of them read in 10.
    assert outline["target_reading_time_minutes"] == 10
    assert len(calls) == 1


@pytest.mark.unit
async def test_a_blog_planned_inside_its_range_is_as_the_model_wrote_it(monkeypatch):
    outline, _ = await _generate(monkeypatch, "blog", [_blog(300, 350, 300, 400, 300, minutes=8)])

    budgets = [section["suggested_word_count"] for section in outline["structure"]["sections"]]
    assert budgets == [300, 350, 300, 400, 300]
    assert outline["target_word_count"] == 1650
    assert outline["target_reading_time_minutes"] == 8


@pytest.mark.unit
async def test_a_reading_time_brought_down_is_never_under_what_the_outlines_model_accepts(
    monkeypatch,
):
    """Review round 2: the blog's model takes two minutes at least."""
    outline, _ = await _generate(
        monkeypatch, "blog", [_blog(400, 400, 400, 400, 400, 400, 400, 400, minutes=2)]
    )

    assert outline["target_word_count"] == 2000
    assert outline["target_reading_time_minutes"] == 2
