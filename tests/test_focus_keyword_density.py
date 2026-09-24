"""Regression tests for focus-keyword pinning and keyword-density enforcement.

Covers the failure this suite exists to prevent: an article generated for a
model-invented keyphrase, then labelled with the user's query, so the phrase
actually reported as the focus keyphrase is barely present in the prose.

All deterministic — no model calls, no DB. Node-level tests invoke the real
validate/final-validate node functions directly, with repair calls mocked.
"""

from src.flow.engines.content.generation.focus_keyword import (
    focus_keyword_from_outline,
    normalize_focus_keyword,
    pin_focus_keyword,
    resolve_focus_keyword,
)
from src.flow.engines.content.generation.keyword_density import (
    CONTENT_TYPE_FAMILIES,
    analyze_keyword_density,
    build_density_prompt_instruction,
    count_keyphrase_occurrences,
    count_words,
    resolve_content_family,
    resolve_density_policy,
)
from src.flow.engines.content.generation.requirements_spec import build_requirements_spec
from src.flow.engines.content.generation.validation import (
    apply_density_report,
    check_keyword_density,
    check_keyword_presence,
)

USER_QUERY = "best project management software"


def _filler(words: int) -> str:
    """Neutral prose containing none of the keyphrase's words."""
    return " ".join(["alpha", "bravo", "charlie", "delta", "echo"] * (words // 5 + 1)).split()


def _article(keyphrase: str, occurrences: int, total_words: int) -> str:
    """Body text of ~`total_words` words containing `occurrences` exact keyphrase uses."""
    phrase_words = len(keyphrase.split())
    filler_needed = max(0, total_words - occurrences * phrase_words)
    filler = _filler(filler_needed)[:filler_needed]
    chunk = max(1, len(filler) // max(1, occurrences))
    parts = []
    for i in range(occurrences):
        parts.append(" ".join(filler[i * chunk : (i + 1) * chunk]))
        parts.append(keyphrase)
    parts.append(" ".join(filler[occurrences * chunk :]))
    return " ".join(p for p in parts if p)


def _spec(content_type: str = "blog", keyword: str = USER_QUERY, target_words: int = 1200):
    return build_requirements_spec(
        {"focus_keyphrase": keyword, "target_word_count": target_words},
        content_type,
    )


# ── the focus keyword is the user's query, verbatim ──────────────────────────


def test_focus_keyword_equals_user_query_exactly():
    state = {
        "serp_payload": {"query": USER_QUERY},
        "seo_result": {"keyword_recommendations": {"selected_keyword": USER_QUERY}},
        "content": {},
    }
    assert resolve_focus_keyword(state) == USER_QUERY


def test_selected_keyword_outranks_outline_and_topic():
    """A model-invented outline keyphrase must never win over the user's choice."""
    state = {
        "serp_payload": {"query": "raw typed query"},
        "seo_result": {"keyword_recommendations": {"selected_keyword": USER_QUERY}},
        "content": {
            "selected_topic": "12 Project Tools Teams Actually Stick With In 2026",
            "outline": {"focus_keyphrase": "project tools"},
        },
    }
    assert resolve_focus_keyword(state) == USER_QUERY


def test_payload_query_used_when_keyword_selection_was_skipped():
    """Library/bulk runs never hit the keyword-selection interrupt."""
    state = {"serp_payload": {"query": USER_QUERY}, "seo_result": {}, "content": {}}
    assert resolve_focus_keyword(state) == USER_QUERY


def test_keyword_case_and_punctuation_are_never_rewritten():
    state = {"serp_payload": {"query": "Best CRM for B2B SaaS"}, "content": {}}
    assert resolve_focus_keyword(state) == "Best CRM for B2B SaaS"


def test_only_transport_whitespace_is_normalized():
    assert normalize_focus_keyword("  best   crm software \n") == "best crm software"
    assert normalize_focus_keyword(None) == ""


# ── pinning: topic → outline → generation → validation ───────────────────────


def test_pin_replaces_model_invented_outline_keyphrase():
    outline = {
        "title": "Some Model Chosen Title",
        "focus_keyphrase": "pm tools",
        "keywords_to_include": ["pm tools", "team collaboration"],
    }
    pin_focus_keyword(outline, USER_QUERY)
    assert outline["focus_keyphrase"] == USER_QUERY
    assert focus_keyword_from_outline(outline) == USER_QUERY


def test_pin_makes_keyword_lead_the_approved_keyword_list():
    """generate_content derives its 'Primary Keyword' prompt line from this list."""
    outline = {"focus_keyphrase": "pm tools", "keywords_to_include": ["pm tools", "gantt charts"]}
    pin_focus_keyword(outline, USER_QUERY)
    assert outline["keywords_to_include"][0] == USER_QUERY
    assert "gantt charts" in outline["keywords_to_include"]


def test_pin_does_not_duplicate_an_already_present_keyword():
    outline = {"focus_keyphrase": USER_QUERY, "keywords_to_include": [USER_QUERY, "gantt charts"]}
    pin_focus_keyword(outline, USER_QUERY)
    assert outline["keywords_to_include"].count(USER_QUERY) == 1


def test_pin_updates_nested_seo_block_shapes():
    """Some outline schemas nest the SEO block; a stale nested copy must not win."""
    outline = {"seo": {"focus_keyphrase": "pm tools"}, "keywords_to_include": ["pm tools"]}
    pin_focus_keyword(outline, USER_QUERY)
    assert outline["seo"]["focus_keyphrase"] == USER_QUERY
    assert focus_keyword_from_outline(outline) == USER_QUERY


def test_keyword_survives_into_the_requirements_spec():
    outline = {"focus_keyphrase": "pm tools", "keywords_to_include": ["pm tools"]}
    pin_focus_keyword(outline, USER_QUERY)
    assert build_requirements_spec(outline, "blog")["target_keyword"] == USER_QUERY


def test_spec_override_wins_over_an_unpinned_outline():
    """Covers outlines produced before pinning existed."""
    spec = build_requirements_spec({"focus_keyphrase": "pm tools"}, "blog", USER_QUERY)
    assert spec["target_keyword"] == USER_QUERY


# ── density calculation, incl. multi-word keyphrases ─────────────────────────


def test_multi_word_keyphrase_counted_as_one_occurrence():
    text = "We reviewed the best project management software for remote teams."
    assert count_keyphrase_occurrences(text, USER_QUERY) == 1


def test_multi_word_keyphrase_counted_across_repetitions():
    text = _article(USER_QUERY, occurrences=7, total_words=900)
    assert count_keyphrase_occurrences(text, USER_QUERY) == 7


def test_partial_word_matches_do_not_count():
    """The classic substring false positive: 'crm' inside 'crms' / 'scrm'."""
    assert count_keyphrase_occurrences("crms and scrm and microcrm", "crm") == 0
    assert count_keyphrase_occurrences("a crm helps", "crm") == 1


def test_out_of_order_words_do_not_count():
    text = "software management project is not the phrase"
    assert count_keyphrase_occurrences(text, "project management software") == 0


def test_urls_and_code_excluded_from_density():
    """A keyphrase in a slug or code block is not keyphrase usage in the copy."""
    text = (
        "See [the guide](https://example.com/best-project-management-software) here.\n\n"
        "```\nbest project management software\n```\n"
    )
    assert count_keyphrase_occurrences(text, USER_QUERY) == 0


def test_link_anchor_text_does_count():
    text = "Read our [best project management software](https://example.com/guide) roundup."
    assert count_keyphrase_occurrences(text, USER_QUERY) == 1


def test_density_matches_the_yoast_formula():
    text = _article("crm", occurrences=10, total_words=1000)
    report = analyze_keyword_density(text, "crm", "blog")
    assert report["word_count"] == count_words(text)
    expected = round(report["occurrences"] / report["word_count"] * 100, 3)
    assert report["density"] == expected


def test_weighted_density_reflects_phrase_length():
    """A 4-word phrase occupies 4x the text a 1-word phrase does per occurrence."""
    text = _article(USER_QUERY, occurrences=10, total_words=1000)
    report = analyze_keyword_density(text, USER_QUERY, "blog")
    assert report["weighted_density"] == round(report["density"] * 4, 3)


def test_title_and_meta_add_occurrences_but_not_word_count():
    body = _article(USER_QUERY, occurrences=5, total_words=1000)
    plain = analyze_keyword_density(body, USER_QUERY, "blog")
    with_meta = analyze_keyword_density(
        body, USER_QUERY, "blog", extra_text=f"{USER_QUERY} in 2026\n{USER_QUERY} compared."
    )
    assert with_meta["occurrences"] == plain["occurrences"] + 2
    assert with_meta["word_count"] == plain["word_count"]


# ── too low / too high detection ─────────────────────────────────────────────


def test_very_low_density_is_detected():
    text = _article(USER_QUERY, occurrences=1, total_words=2000)
    report = analyze_keyword_density(text, USER_QUERY, "blog")
    assert report["status"] == "too_low"
    assert report["occurrence_delta"] > 0


def test_keyword_stuffing_is_detected():
    text = _article(USER_QUERY, occurrences=120, total_words=1500)
    report = analyze_keyword_density(text, USER_QUERY, "blog")
    assert report["status"] == "too_high"
    assert report["occurrence_delta"] < 0


def test_natural_usage_passes():
    policy = resolve_density_policy(1500, "blog", len(USER_QUERY.split()))
    mid = (policy["min_occurrences"] + policy["max_occurrences"]) // 2
    text = _article(USER_QUERY, occurrences=mid, total_words=1500)
    assert analyze_keyword_density(text, USER_QUERY, "blog")["status"] == "ok"


def test_presence_without_density_is_still_a_failure():
    """The exact bug: keyword present once in a long article, so presence passes."""
    final_content = {"introduction": "", "body_markdown": _article(USER_QUERY, 1, 2500)}
    spec = _spec()
    assert check_keyword_presence(final_content, spec)["passed"] is True
    density = check_keyword_density(final_content, spec)
    assert density["passed"] is False
    assert density["severity"] == "blocking"


def test_stuffing_is_blocking_not_a_warning():
    final_content = {"introduction": "", "body_markdown": _article(USER_QUERY, 150, 1200)}
    result = check_keyword_density(final_content, _spec())
    assert result["passed"] is False
    assert result["severity"] == "blocking"


def test_density_check_skipped_without_a_keyword():
    spec = build_requirements_spec({}, "blog")
    assert check_keyword_density({"body_markdown": "some words here"}, spec)["passed"] is True


def test_empty_content_is_not_applicable_rather_than_a_crash():
    report = analyze_keyword_density("", USER_QUERY, "blog")
    assert report["status"] == "not_applicable"
    assert report["density"] == 0.0


# ── length-aware bands ───────────────────────────────────────────────────────


def test_band_tiers_shift_with_article_length():
    short = resolve_density_policy(250, "blog", 1)
    long_ = resolve_density_policy(4000, "blog", 1)
    assert short["tier"] == "very_short"
    assert long_["tier"] == "very_long"
    # Short pages tolerate (and need) a higher relative density than long ones.
    assert short["min_density"] > long_["min_density"]
    assert short["max_density"] > long_["max_density"]


def test_occurrence_bounds_scale_with_length():
    short = resolve_density_policy(400, "blog", 1)
    long_ = resolve_density_policy(4000, "blog", 1)
    assert long_["min_occurrences"] > short["min_occurrences"]
    assert long_["max_occurrences"] > short["max_occurrences"]


def test_short_page_is_not_failed_for_writing_naturally():
    """A 250-word page using the phrase 3x is correct, not thin and not stuffed."""
    text = _article(USER_QUERY, occurrences=3, total_words=250)
    assert analyze_keyword_density(text, USER_QUERY, "contact-us")["status"] == "ok"


def test_long_article_needs_more_than_two_occurrences():
    """Yoast's 2-occurrence floor is not enough on long copy; the percentage takes over."""
    text = _article(USER_QUERY, occurrences=2, total_words=3000)
    assert analyze_keyword_density(text, USER_QUERY, "blog")["status"] == "too_low"


def test_very_short_content_accepts_a_single_occurrence():
    policy = resolve_density_policy(60, "blog", 1)
    assert policy["min_occurrences"] == 1


def test_longer_keyphrases_get_a_damped_ceiling():
    """Repeating a 5-word phrase as often as a 1-word one is unreadable."""
    one_word = resolve_density_policy(1500, "blog", 1)
    five_word = resolve_density_policy(1500, "blog", 5)
    assert five_word["max_density"] < one_word["max_density"]
    assert five_word["max_occurrences"] < one_word["max_occurrences"]


def test_band_is_always_coherent_across_lengths_and_phrase_lengths():
    for words in (0, 50, 120, 300, 900, 1800, 3500, 8000):
        for phrase_words in range(1, 7):
            policy = resolve_density_policy(words, "blog", phrase_words)
            assert policy["min_density"] < policy["max_density"]
            assert policy["min_occurrences"] <= policy["max_occurrences"]
            assert policy["min_density"] <= policy["target_density"] <= policy["max_density"]


# ── all 34 content types ─────────────────────────────────────────────────────


def test_all_34_content_types_have_a_family():
    from src.flow.model.structure.outlines import CONTENT_TYPE_TO_MODEL

    assert len(CONTENT_TYPE_TO_MODEL) == 34
    missing = set(CONTENT_TYPE_TO_MODEL) - set(CONTENT_TYPE_FAMILIES)
    assert not missing, f"content types with no density family: {sorted(missing)}"


def test_unknown_content_type_falls_back_to_the_default_family():
    """A new content type must work without being added to any table here."""
    assert resolve_content_family("some-brand-new-type") == "informational"
    policy = resolve_density_policy(1500, "some-brand-new-type", 2)
    assert policy["min_occurrences"] >= 2


def test_content_type_aliases_resolve():
    assert resolve_content_family("Landing Page") == "transactional"
    assert resolve_content_family("article") == "informational"  # alias of blog


def test_every_content_type_grades_natural_usage_as_ok():
    from src.flow.model.structure.outlines import CONTENT_TYPE_TO_MODEL

    for content_type in CONTENT_TYPE_TO_MODEL:
        for words in (300, 1200, 3000):
            policy = resolve_density_policy(words, content_type, len(USER_QUERY.split()))
            mid = (policy["min_occurrences"] + policy["max_occurrences"]) // 2
            text = _article(USER_QUERY, occurrences=mid, total_words=words)
            report = analyze_keyword_density(text, USER_QUERY, content_type)
            assert report["status"] == "ok", f"{content_type} @ {words}w: {report['detail']}"


def test_every_content_type_detects_both_failure_directions():
    from src.flow.model.structure.outlines import CONTENT_TYPE_TO_MODEL

    for content_type in CONTENT_TYPE_TO_MODEL:
        thin = _article(USER_QUERY, occurrences=1, total_words=2000)
        assert analyze_keyword_density(thin, USER_QUERY, content_type)["status"] == "too_low"
        stuffed = _article(USER_QUERY, occurrences=150, total_words=2000)
        assert analyze_keyword_density(stuffed, USER_QUERY, content_type)["status"] == "too_high"


# ── prompt/gate agreement + reporting ────────────────────────────────────────


def test_prompt_instruction_quotes_the_exact_keyword_and_the_gate_band():
    policy = resolve_density_policy(1500, "blog", len(USER_QUERY.split()))
    instruction = build_density_prompt_instruction(USER_QUERY, 1500, "blog")
    assert USER_QUERY in instruction
    assert str(policy["min_occurrences"]) in instruction
    assert str(policy["max_occurrences"]) in instruction


def test_prompt_instruction_is_empty_without_a_keyword():
    assert build_density_prompt_instruction("", 1500, "blog") == ""


def test_measured_density_is_written_onto_final_content():
    """Overwrites the LLM's self-reported guess with the measured value."""
    final_content = {
        "introduction": "",
        "body_markdown": _article(USER_QUERY, 12, 1200),
        "keyphrase_density": 99.9,  # model's unverified guess
    }
    updated = apply_density_report(final_content, _spec())
    assert updated["keyphrase_density"] != 99.9
    assert updated["keyword_density_report"]["keyphrase"] == USER_QUERY
    assert updated["keyword_density_report"]["occurrences"] == 12


# ── node-level: the pipeline grades and repairs against the user's query ────


def _state(body: str, outline_keyphrase: str = "pm tools", content_type: str = "blog") -> dict:
    """A post-generation state whose outline carries a model-invented keyphrase."""
    return {
        "serp_payload": {"query": USER_QUERY},
        "seo_result": {"keyword_recommendations": {"selected_keyword": USER_QUERY}},
        "content": {
            "selected_topic": "Best Project Management Software for Remote Teams",
            "content_type": content_type,
            "outline": {"focus_keyphrase": outline_keyphrase, "target_word_count": 0},
            "final_content": {
                "title": "Best Project Management Software for Remote Teams",
                "introduction": "",
                "body_markdown": body,
            },
            "review": {},
        },
    }


def _check(result: dict, stage: str, name: str) -> dict | None:
    validation = result["content"]["review"][stage]
    for c in validation["failed_checks"] + validation["warnings"]:
        if c["name"] == name:
            return c
    return None


async def test_validate_node_grades_the_user_query_not_the_outline_keyphrase():
    from src.flow.engines.content.generation.validation import validate_content

    # Heavy use of the model's phrase, almost none of the user's: must fail.
    body = _article("pm tools", 30, 1500) + " " + USER_QUERY
    result = await validate_content(_state(body))
    failed = _check(result, "validation", "keyword_density")
    assert failed is not None
    assert USER_QUERY in failed["detail"]
    assert result["content"]["final_content"]["keyword_density_report"]["keyphrase"] == USER_QUERY


async def test_validate_node_passes_natural_usage_of_the_user_query():
    from src.flow.engines.content.generation.validation import validate_content

    policy = resolve_density_policy(1500, "blog", len(USER_QUERY.split()))
    mid = (policy["min_occurrences"] + policy["max_occurrences"]) // 2
    result = await validate_content(_state(_article(USER_QUERY, mid, 1500)))
    assert _check(result, "validation", "keyword_density") is None
    assert _check(result, "validation", "keyword_presence") is None


async def test_final_validate_repairs_density_lost_during_humanization(monkeypatch):
    """Humanizer dropped the phrase; one post-humanize repair must restore it."""
    from src.flow.engines.content.generation import validation

    calls = {}
    policy = resolve_density_policy(1500, "blog", len(USER_QUERY.split()))
    mid = (policy["min_occurrences"] + policy["max_occurrences"]) // 2

    async def fake_repair(**kwargs):
        calls.update(kwargs)
        return {**kwargs["final_content"], "body_markdown": _article(USER_QUERY, mid, 1500)}

    monkeypatch.setattr(validation, "run_targeted_repair", fake_repair)
    result = await validation.final_validate_content(_state(_article(USER_QUERY, 1, 1500)))

    assert calls["focus_keyword"] == USER_QUERY
    assert "keyword_density" in [c["name"] for c in calls["failed_checks"]]
    assert _check(result, "final_validation", "keyword_density") is None
    report = result["content"]["final_content"]["keyword_density_report"]
    assert report["status"] == "ok"


async def test_final_validate_discards_a_repair_that_makes_things_worse(monkeypatch):
    from src.flow.engines.content.generation import validation

    original = _article(USER_QUERY, 1, 1500)
    state = _state(original)
    state["content"]["outline"]["target_word_count"] = 1500  # word band is enforced
    policy = resolve_density_policy(3000, "blog", len(USER_QUERY.split()))
    mid = (policy["min_occurrences"] + policy["max_occurrences"]) // 2

    async def bloating_repair(**kwargs):
        # Fixes density, but doubles the length: a previously passing check
        # (word_count_band) now fails, so the repair must be thrown away even
        # though the total failure count did not go up.
        return {**kwargs["final_content"], "body_markdown": _article(USER_QUERY, mid, 3000)}

    monkeypatch.setattr(validation, "run_targeted_repair", bloating_repair)
    result = await validation.final_validate_content(state)
    assert result["content"]["final_content"]["body_markdown"] == original
    assert _check(result, "final_validation", "word_count_band") is None


def test_humanizer_prompt_carries_exact_keyword_and_band():
    from src.flow.engines.content.generation.humanize_content import _build_prompt_data

    data = _build_prompt_data(
        content_payload={"introduction": "", "body_markdown": _article(USER_QUERY, 6, 1200)},
        word_target=1200,
        content_type="blog",
        focus_keyword=USER_QUERY,
    )
    assert f'"{USER_QUERY}"' in data["keyword_instruction"]
    assert "currently appears 6 time(s)" in data["keyword_instruction"]


def test_repair_prompt_carries_exact_keyword_only_for_keyword_failures():
    from src.flow.engines.content.generation.repair_content import _build_keyword_block

    assert USER_QUERY in _build_keyword_block([{"name": "keyword_density"}], USER_QUERY)
    assert _build_keyword_block([{"name": "brand_presence"}], USER_QUERY) == ""
