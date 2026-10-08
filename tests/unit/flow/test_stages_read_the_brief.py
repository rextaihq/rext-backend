"""The rewrite and the repair read the article's brief (FB2.21, revnix/rext-control#702, P1 step two).

Each stage used to state the reader, the tone, the length and the keywords in sentences of its
own, or not at all: the repair was told none of them, and a repair for the brand's address broke
the brand's prominence (revnix/rext-control#818's runs). The brief says each once, from the spec
the article is checked against; a stage adds only what it measured and what to do about it.
"""

import pytest

from src.flow.engines.content.generation import repair_content
from src.flow.engines.content.generation.generation_brief import brief_for_stage
from src.flow.engines.content.generation.humanize_content import _build_prompt_data
from src.flow.engines.content.generation.requirements_spec import build_requirements_spec
from src.flow.prompts.human.humanize import get_humanize_prompt

FOCUS = "content calendar template"
BRAND = {"brand_name": "Acme Tools", "brand_url": "https://www.acme.test/"}


def _outline(prominence="subtle", **extra):
    return {
        "title": "How to use a content calendar template",
        "focus_keyphrase": FOCUS,
        "keywords_to_include": [FOCUS, "editorial calendar", "posting schedule"],
        "target_audience": ["Marketing leads", "Small agencies"],
        "tone": "Practical, plain-spoken",
        "target_word_count": 1500,
        "brand_prominence": prominence,
        "promote_brand": prominence in ("prominent", "subtle"),
        "brand_voice_promotion": dict(BRAND),
        "final_cta": {"primary_cta": "Start planning today"},
        **extra,
    }


def _article(words):
    """An article of exactly ``words`` words, its heading's four included."""
    sentences, rest = divmod(words - 4, 6)
    text = ("Plan one week at a time. " * sentences + "Plan. " * rest).strip()
    return {
        "title": "How to use a content calendar template",
        "introduction": "",
        "body_markdown": f"## Plan the month\n\n{text}",
    }


def _data(outline, words=1500, **extra):
    spec = build_requirements_spec(outline, "blog", focus_keyword=FOCUS)
    brief = brief_for_stage(spec, outline, stage="rewrite")
    return (
        _build_prompt_data(
            content_payload=_article(words),
            word_target=1500,
            content_type="blog",
            focus_keyword=FOCUS,
            secondary_keywords=spec["secondary_keywords"],
            audience=outline["target_audience"],
            tone=outline["tone"],
            excluded_brand=spec.get("excluded_brand"),
            brief=brief,
            **extra,
        ),
        brief,
    )


# --- the rewrite ---------------------------------------------------------------------


def test_the_rewrite_is_given_the_brief_and_states_no_fact_a_second_time():
    data, brief = _data(_outline("subtle"))

    assert data["reader_instruction"] == brief
    human = get_humanize_prompt().format_messages(**data)[-1].content
    assert "THE ARTICLE'S BRIEF" in human
    assert "- Written for: Marketing leads, Small agencies" in human
    assert "- Tone: Practical, plain-spoken" in human
    assert human.count("editorial calendar, posting schedule") == 1
    # Said by the brief, so not again in the pass's own words.
    assert "READER AND TONE" not in human
    assert "secondary keywords; keep each at least once" not in human
    # What this pass measured is still its own to say.
    assert "FOCUS KEYPHRASE — MUST SURVIVE THIS REWRITE" in human


def test_without_a_brief_the_rewrite_says_what_it_said_before():
    spec = build_requirements_spec(_outline("subtle"), "blog", focus_keyword=FOCUS)
    data = _build_prompt_data(
        content_payload=_article(1500),
        word_target=1500,
        content_type="blog",
        focus_keyword=FOCUS,
        secondary_keywords=spec["secondary_keywords"],
        audience=["Marketing leads"],
        tone="Practical",
    )

    assert "READER AND TONE" in data["reader_instruction"]
    assert "secondary keywords; keep each at least once" in data["keyword_instruction"]


def test_the_brand_kept_out_is_said_by_the_brief_and_acted_on_by_the_rewrite():
    data, brief = _data(_outline("none"))

    assert "- Brand: Acme Tools, none:" in brief
    assert "The internal links the user approved stay" in brief
    assert data["brand_instruction"].startswith("BRAND EXCLUSION — the brief's brand line stands")
    assert 'if the draft names "Acme Tools"' in data["brand_instruction"]


@pytest.mark.parametrize(
    ("words", "asked"),
    [
        # Inside the band (1,320 to 1,680), under the target: left at its length. It used to be
        # told to expand by 100 words, which is how an article that passed went over.
        (1400, "within the 1320-1680 acceptable range"),
        (1600, "within the 1320-1680 acceptable range"),
        (1000, "under its range of 1320-1680"),
        (2100, "over its range of 1320-1680"),
    ],
)
def test_the_length_is_measured_against_the_band_the_brief_states(words, asked):
    data, brief = _data(_outline("subtle"), words=words)

    assert "between 1320 and 1680" in brief
    assert asked in data["length_instruction"]
    assert ("EXPAND" in data["length_instruction"]) is (words < 1320)
    assert ("TRIM" in data["length_instruction"]) is (words > 1680)


def test_an_article_over_its_range_is_told_a_longer_rewrite_fails():
    data, _ = _data(_outline("subtle"), words=2100)

    assert "longer than 1680 words has failed this requirement" in data["length_instruction"]


# --- the repair ----------------------------------------------------------------------


async def test_the_repair_is_given_the_brief_and_only_its_own_length(monkeypatch):
    captured = {}

    class _Model:
        def with_structured_output(self, schema):
            return self

    async def stop_after_the_prompt(model, messages, stage):
        captured["messages"] = messages
        raise RuntimeError("the prompt is all this test reads")

    monkeypatch.setattr(repair_content, "load_content_model", lambda: _Model())
    monkeypatch.setattr(repair_content, "ainvoke_watched", stop_after_the_prompt)
    outline = _outline("subtle")
    spec = build_requirements_spec(outline, "blog", focus_keyword=FOCUS)
    brief = brief_for_stage(spec, outline, stage="repair")

    repaired = await repair_content.run_targeted_repair(
        final_content=_article(1500),
        content_type="blog",
        failed_checks=[
            {"name": "brand_url_accuracy", "passed": False, "severity": "blocking", "detail": "x"}
        ],
        brief=brief,
    )

    assert repaired is None
    human = captured["messages"][-1].content
    assert "THE ARTICLE'S BRIEF" in human
    assert "Fix the listed issues; the brief stands." in human
    # What a repair for one thing must not undo: the user's choices, said once.
    assert "- Brand: Acme Tools, subtle:" in human
    assert (
        "- Secondary keywords (each at least once): editorial calendar, posting schedule" in human
    )
    # One length only: the one the article has now. The target is the rewrite's.
    assert "- Length:" not in human
    assert "LENGTH — the article is currently" in human


# -- Step three: the writer reads the brief ---------------------------------------------------


def _opening(brief):
    from src.flow.engines.content.generation.content_generation import writer_message_opening

    return writer_message_opening(
        brief,
        content_type="blog",
        topic="How to use a content calendar template",
        title_lock="TITLE — FIXED, USER-SELECTED\n",
        primary_keyword=FOCUS,
        target_word_count=1500,
        max_word_count=1680,
    )


def test_the_writers_message_opens_with_the_brief_the_later_stages_read():
    outline = _outline("subtle")
    spec = build_requirements_spec(outline, "blog", focus_keyword=FOCUS)
    brief = brief_for_stage(spec, outline, stage="writer")

    opening = _opening(brief)

    assert opening.startswith(brief)
    assert "Write the article this brief describes." in opening
    # The same facts in the same words the rewrite and the repair are given after it.
    rewrite = brief_for_stage(spec, outline, stage="rewrite")
    shared = [line for line in brief.splitlines() if line.startswith("- ")]
    assert shared and all(line in rewrite for line in shared)
    for line in (
        "- Written for: Marketing leads, Small agencies",
        "- Tone: Practical, plain-spoken",
        "- Secondary keywords (each at least once): editorial calendar, posting schedule",
        "- Brand: Acme Tools, subtle: one natural mention early in the body",
    ):
        assert line in opening
    # What the message said before stays where the brief does not say it.
    assert "Content Type: blog\n" in opening
    assert "TITLE — FIXED, USER-SELECTED" in opening
    assert f"Primary Keyword: {FOCUS}\n" in opening


def test_with_the_brief_the_writer_is_told_one_length_the_one_the_check_reads():
    outline = _outline("subtle")
    spec = build_requirements_spec(outline, "blog", focus_keyword=FOCUS)

    opening = _opening(brief_for_stage(spec, outline, stage="writer"))

    # The range the article is checked against: 12% either side of 1,500.
    assert (
        "- Length: about 1500 words; the introduction and the body together between 1320 and 1680"
        in opening
    )
    # Not a second range beside it that makes the target the least.
    assert "Target Word Count" not in opening
    assert "1500-1680" not in opening


def test_without_a_brief_the_writers_message_opens_as_it_did():
    opening = _opening("")

    assert opening.startswith(
        "Content Type: blog\nTopic: How to use a content calendar template\n\n"
    )
    assert (
        "Target Word Count: 1500-1680 words (stay within this range — do not go meaningfully "
        "under or over)\n\n"
    ) in opening
    assert opening.endswith("\n\n")
