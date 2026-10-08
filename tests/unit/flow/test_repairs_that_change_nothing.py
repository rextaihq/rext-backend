"""Repair attempts that changed nothing (FB2.16, rext-control#818).

Seven real articles each got two repair attempts, 41 to 76 seconds together, and 9 of the 14
fixed no check. Their own records say why: 7 were thrown away whole for breaking another check
(4 of them carried the fix), 3 asked again for a check the attempt before had already worked on
and left failing, and 2 were spent on the brand's address alone.

So: a repair that broke something keeps the part that fixes an issue and breaks nothing; no
attempt runs for a check already tried or for the headings' own alone; and the brand's first
mention is linked to its approved address in code.
"""

from unittest.mock import patch

import pytest

import src.flow.engines.content.generation.repair_content as repair_module
import src.flow.engines.content.generation.validation as v
import tests.unit.flow.test_link_preservation_and_repair_flow as flow
from src.flow.engines.content.generation.brand_link import ensure_brand_link
from src.flow.engines.content.generation.repair_content import (
    SUBHEADING_CHECKS,
    checks_already_tried,
    checks_worth_an_attempt,
    repair_content,
)
from src.flow.engines.content.generation.repair_salvage import salvage_repair
from src.flow.engines.content.generation.validation import validate_content
from src.flow.engines.router.content_quality import validation_router

# ── what of a repair is kept ─────────────────────────────────────────────────

ARTICLE = {
    "introduction": "An opening paragraph.",
    "body_markdown": "## One\n\nFirst WRONG paragraph.\n\nSecond paragraph.\n\n## Two\n\nThird paragraph.",
    "facts": [{"text": "a fact", "source_url": "https://source.test/a"}],
    "outbound_links": [],
    "meta_description": "As it was.",
}


def _failing(content: dict) -> set[str]:
    """Stand-in checks: "WRONG" is the issue to fix; "BROKEN" in the prose, or a fact the
    article never had, is a check that passed and now fails."""
    prose = f"{content.get('introduction')} {content.get('body_markdown')}"
    names = set()
    if "WRONG" in prose:
        names.add("the_issue")
    if "BROKEN" in prose:
        names.add("another_check")
    if any(f.get("source_url") != "https://source.test/a" for f in content.get("facts") or []):
        names.add("facts_and_external_links")
    return names


def _repaired(**body_swaps: str) -> dict:
    body = ARTICLE["body_markdown"]
    for old, new in body_swaps.items():
        body = body.replace(old, new)
    return {**ARTICLE, "body_markdown": body}


def test_a_repair_whose_echoed_lists_broke_a_check_keeps_its_prose():
    repaired = {
        **_repaired(**{"First WRONG paragraph.": "First paragraph, put right."}),
        "facts": [{"text": "a fact", "source_url": "https://invented.test/b"}],
        "meta_description": "Reworded.",
    }

    kept, how = salvage_repair(ARTICLE, repaired, _failing, {"the_issue"})

    assert how == {"how": "lists"}
    assert "put right" in kept["body_markdown"]
    assert kept["facts"] == ARTICLE["facts"]  # the article's own, not the echo
    assert kept["meta_description"] == "Reworded."
    assert _failing(kept) == set()


def test_a_fix_is_kept_and_the_damage_beside_it_is_not():
    repaired = _repaired(
        **{
            "First WRONG paragraph.": "First paragraph, put right.",
            "Second paragraph.": "Second paragraph, now BROKEN.",
            "Third paragraph.": "Third paragraph, reworded for no reason.",
        }
    )

    kept, how = salvage_repair(ARTICLE, repaired, _failing, {"the_issue"})

    assert how == {"how": "blocks", "kept": 1, "dropped": 1}
    assert kept["body_markdown"] == ARTICLE["body_markdown"].replace(
        "First WRONG paragraph.", "First paragraph, put right."
    )  # the fix alone: neither the damage nor the needless rewording


def test_a_fix_and_its_damage_in_one_block_leave_nothing_to_keep():
    repaired = _repaired(**{"First WRONG paragraph.": "First paragraph, right but BROKEN."})

    kept, how = salvage_repair(ARTICLE, repaired, _failing, {"the_issue"})

    assert kept is None
    assert how == {"how": "blocks", "kept": 0, "dropped": 1}


def test_changes_that_fix_nothing_are_not_worth_keeping():
    repaired = _repaired(
        **{"Second paragraph.": "Second paragraph, reworded.", "Third paragraph.": "BROKEN."}
    )

    kept, _ = salvage_repair(ARTICLE, repaired, _failing, {"the_issue"})

    assert kept is None


def test_added_removed_and_merged_blocks_are_each_one_change():
    repaired = _repaired(
        **{
            "First WRONG paragraph.\n\nSecond paragraph.": "First and second, put right, as one.",
            "## Two\n\n": "## Two\n\nA new BROKEN paragraph.\n\n",
        }
    )

    kept, how = salvage_repair(ARTICLE, repaired, _failing, {"the_issue"})

    assert how == {"how": "blocks", "kept": 1, "dropped": 1}
    assert "First and second, put right, as one." in kept["body_markdown"]
    assert "BROKEN" not in kept["body_markdown"]
    assert kept["body_markdown"].endswith("## Two\n\nThird paragraph.")


def test_another_stages_check_counts_neither_as_broken_nor_as_fixed():
    def failing(content: dict) -> set[str]:
        return _failing(content) | {"word_count_band"}

    repaired = {
        **_repaired(**{"First WRONG paragraph.": "First paragraph, put right."}),
        "facts": [{"text": "a fact", "source_url": "https://invented.test/b"}],
    }

    kept, how = salvage_repair(
        ARTICLE, repaired, failing, {"the_issue"}, ignore=["word_count_band"]
    )

    assert how == {"how": "lists"} and "put right" in kept["body_markdown"]


# ── which checks get an attempt ──────────────────────────────────────────────


def _checks(*names: str) -> list[dict]:
    return [{"name": name} for name in names]


def _names(checks: list[dict]) -> list[str]:
    return [c["name"] for c in checks]


def test_a_check_a_kept_repair_left_failing_has_had_its_turn():
    history = [{"accepted": True, "unresolved_checks": ["brand_placement_policy"]}]

    assert checks_already_tried(history) == {"brand_placement_policy"}
    assert _names(
        checks_worth_an_attempt(_checks("brand_placement_policy", "unsupported_claims"), history)
    ) == ["unsupported_claims"]


@pytest.mark.parametrize(
    "entry",
    [
        {"accepted": False, "unresolved_checks": ["unsupported_claims"]},  # thrown away
        {"accepted": True, "no_result": True, "unresolved_checks": ["unsupported_claims"]},
        {  # fixed by the repair, lost with a block that broke something else
            "accepted": True,
            "unresolved_checks": ["unsupported_claims"],
            "lost_checks": ["unsupported_claims"],
        },
    ],
)
def test_a_check_whose_repair_was_not_kept_has_not(entry):
    assert checks_already_tried([entry]) == set()
    assert _names(checks_worth_an_attempt(_checks("unsupported_claims"), [entry])) == [
        "unsupported_claims"
    ]


def test_the_headings_own_checks_get_no_attempt_of_their_own():
    assert checks_worth_an_attempt(_checks(*SUBHEADING_CHECKS), None) == []
    assert _names(
        checks_worth_an_attempt(_checks("subheading_keyphrase", "brand_prominence"), [])
    ) == ["brand_prominence"]


# The seven runs' own records (`content.review.repair_history`, staging, 7 and 8 October 2026):
# per attempt, whether its result was kept, what it was asked for, what it fixed and broke.
A, D = True, False
RUNS = {
    "01a118e4 how-to": [
        (
            A,
            ["brand_placement_policy", "facts_and_external_links", "subheading_keyphrase"],
            ["facts_and_external_links"],
            [],
        ),
        (D, ["brand_placement_policy", "subheading_keyphrase"], [], ["facts_and_external_links"]),
    ],
    "01a118e5-2b89 best-tools": [
        (
            D,
            ["unsupported_claims"],
            ["unsupported_claims"],
            ["facts_and_external_links", "links_preserved"],
        ),
        (D, ["unsupported_claims"], ["unsupported_claims"], ["facts_and_external_links"]),
    ],
    "01a118e5-f7a1 blog": [
        (
            D,
            ["brand_prominence", "brand_url_accuracy", "subheading_keyphrase"],
            ["brand_prominence", "brand_url_accuracy"],
            ["facts_and_external_links"],
        ),
        (
            A,
            ["brand_prominence", "brand_url_accuracy", "subheading_keyphrase"],
            ["brand_prominence", "brand_url_accuracy"],
            [],
        ),
    ],
    "01a1189d how-to": [
        (
            A,
            ["brand_placement_policy", "facts_and_external_links"],
            ["facts_and_external_links"],
            [],
        ),
        (A, ["brand_placement_policy"], [], []),
    ],
    "01a1189f best-tools": [
        (A, ["brand_absent", "unsupported_claims"], ["unsupported_claims"], []),
        (A, ["brand_absent"], [], []),
    ],
    "01a1189e blog": [
        (
            D,
            ["brand_url_accuracy", "subheading_keyphrase", "unsupported_claims"],
            ["brand_url_accuracy", "unsupported_claims"],
            ["facts_and_external_links"],
        ),
        (
            A,
            ["brand_url_accuracy", "subheading_keyphrase", "unsupported_claims"],
            ["brand_url_accuracy", "unsupported_claims"],
            [],
        ),
    ],
    "01a118be blog": [
        (D, ["brand_url_accuracy"], [], ["brand_prominence", "facts_and_external_links"]),
        (D, ["brand_url_accuracy"], [], ["brand_prominence", "facts_and_external_links"]),
    ],
}
IN_CODE = {"brand_url_accuracy"}  # the brand's address is settled before the checks run


def _replay(attempts: list[tuple], *, fixes_survive: bool) -> tuple[list[int], set[str]]:
    """Which of a run's attempts the rule runs, and which checks end up fixed by a repair.

    `fixes_survive`: a thrown-away attempt's fix is kept in part (what taking a repair apart
    is for); False replays the records as they were, every thrown-away attempt lost whole.
    """
    history: list[dict] = []
    ran, fixed = [], set()
    for number, (accepted, asked, resolved, _broke) in enumerate(attempts, start=1):
        failing = [name for name in asked if name not in IN_CODE and name not in fixed]
        if not checks_worth_an_attempt(_checks(*failing), history):
            continue
        ran.append(number)
        kept = accepted or (fixes_survive and bool(set(resolved) - IN_CODE))
        got = (set(resolved) & set(failing)) if kept else set()
        fixed |= got
        history.append(
            {"accepted": kept, "unresolved_checks": [n for n in failing if n not in got]}
        )
    return ran, fixed


def test_on_the_seven_runs_every_fix_is_kept_and_most_idle_attempts_are_gone():
    fixed_then = {
        (run, name)
        for run, attempts in RUNS.items()
        for accepted, _asked, resolved, _broke in attempts
        if accepted
        for name in resolved
        if name not in IN_CODE
    }
    idle_then = sum(
        1
        for attempts in RUNS.values()
        for accepted, _a, resolved, _b in attempts
        if not (accepted and resolved)
    )
    assert idle_then == 9  # of 14

    for fixes_survive in (False, True):
        ran = {
            run: _replay(attempts, fixes_survive=fixes_survive) for run, attempts in RUNS.items()
        }
        fixed_now = {(run, name) for run, (_ran, fixed) in ran.items() for name in fixed}
        assert fixed_then <= fixed_now, fixes_survive  # no fix a repair made is lost

        attempts_now = sum(len(numbers) for numbers, _fixed in ran.values())
        idle_now = sum(
            1
            for run, (numbers, _fixed) in ran.items()
            for number in numbers
            if not (
                (RUNS[run][number - 1][0] or fixes_survive)
                and set(RUNS[run][number - 1][2]) - IN_CODE
            )
        )
        if fixes_survive:
            # One attempt a run where there is something to fix, none for the address alone.
            assert attempts_now == 6 and idle_now == 0
        else:
            # Even with every thrown-away attempt still lost whole: 9 attempts, 4 idle.
            assert attempts_now == 9 and idle_now == 4
        assert idle_now <= idle_then / 2


# ── the brand's address, in code ─────────────────────────────────────────────

BRAND = {"brand_name": "Nextly", "brand_url": "https://nextly.test"}
SPEC = {"brand_context": BRAND}


def _fixed(**prose: str) -> dict:
    content = {"introduction": "", "body_markdown": "", **prose}
    return ensure_brand_link(content, BRAND, stage="test")


def test_a_first_mention_without_a_link_gets_the_approved_one():
    body = "## Picking a CMS\n\nMany teams start small. Later they move to Nextly for its editor. Nextly grows with them."
    content = {"introduction": "An opening.", "body_markdown": body}
    assert not v.check_brand_url_accuracy(content, SPEC)["passed"]

    fixed = _fixed(**content)

    assert fixed["body_markdown"] == body.replace(
        "move to Nextly for", "move to [Nextly](https://nextly.test) for"
    )
    assert v.check_brand_url_accuracy(fixed, SPEC)["passed"]


@pytest.mark.parametrize(
    "written",
    [
        "https://nextly.test/",
        "http://www.nextly.test",
        "https://nextly.test/?utm_source=x",
        "https://nextly.test/pricing",
    ],
)
def test_a_link_to_the_brands_site_under_another_spelling_is_pointed_at_the_approved_address(
    written,
):
    content = {"introduction": f"Teams like [Nextly]({written}) for its editor. It is quick."}

    fixed = _fixed(**content)

    assert (
        fixed["introduction"]
        == "Teams like [Nextly](https://nextly.test) for its editor. It is quick."
    )
    assert v.check_brand_url_accuracy(fixed, SPEC)["passed"]


def test_a_mention_already_linked_right_is_left_alone():
    content = {"introduction": "Teams like [Nextly](https://nextly.test) for its editor."}

    assert _fixed(**content) == {"body_markdown": "", **content}


@pytest.mark.parametrize(
    "body",
    [
        "## Why Nextly\n\nIt is quick.",  # a heading
        "| Tool | Price |\n| Nextly | $9 |",  # a table
        "Read [the Nextly review](https://reviews.test/nextly) first.",  # another link's words
        "Read [Nextly docs](https://nextly.test/docs) first.",  # a deep link of the brand's own
        "Read [Nextly](https://reviews.test/nextly) first.",  # the name, linked somewhere else
        "Run `nextly init` to start.",  # inline code
        "Install it:\n\n```\nNextly init\n```\n\nThen go on.",  # a code block
        "![Nextly's editor](https://img.test/e.png)",  # an image
        "See https://nextly.test/docs for more.",  # a bare address
        "Write to hello@nextly.test for more.",  # an address
        "Their nextly-powered site is quick.",  # the name inside another word
        "Teams use nextly every day.",  # not written as the brand writes it
    ],
)
def test_a_mention_where_a_link_does_not_belong_is_left_for_the_repair(body):
    assert _fixed(body_markdown=body)["body_markdown"] == body


@pytest.mark.parametrize(
    ("brand", "body"),
    [
        ("Buffer", "Slow buffering hurts. Bufferapp is one fix."),
        ("Later", "Decide later what to post. Laterally, nothing changes."),
    ],
)
def test_letters_inside_another_word_are_not_the_brand(brand, body):
    content = {"introduction": "", "body_markdown": body}
    context = {"brand_name": brand, "brand_url": "https://brand.test"}

    assert ensure_brand_link(content, context, stage="test") is content


def test_another_link_in_the_sentence_is_left_as_it_is():
    body = "Nextly is covered in [our pricing guide](https://nextly.test/pricing) in full."

    fixed = _fixed(body_markdown=body)

    assert fixed["body_markdown"] == (
        "[Nextly](https://nextly.test) is covered in "
        "[our pricing guide](https://nextly.test/pricing) in full."
    )
    assert v.check_brand_url_accuracy(fixed, SPEC)["passed"]


@pytest.mark.parametrize(
    ("body", "linked"),
    [
        ("Many pick Nextly.", "Many pick [Nextly](https://nextly.test)."),
        ("Many like Nextly's editor.", "Many like [Nextly](https://nextly.test)'s editor."),
        ("One option (Nextly) is quick.", "One option ([Nextly](https://nextly.test)) is quick."),
        ("- Nextly: the quick one", "- [Nextly](https://nextly.test): the quick one"),
    ],
)
def test_the_name_is_linked_with_the_punctuation_around_it_left_alone(body, linked):
    assert _fixed(body_markdown=body)["body_markdown"] == linked


def test_a_name_of_several_words_is_linked_whole():
    content = {"introduction": "", "body_markdown": "Teams write with Rext AI every day."}
    context = {"brand_name": "Rext AI", "brand_url": "https://rext.test"}

    fixed = ensure_brand_link(content, context, stage="test")

    assert fixed["body_markdown"] == "Teams write with [Rext AI](https://rext.test) every day."


def test_no_brand_or_no_address_changes_nothing():
    content = {"introduction": "Teams like Nextly.", "body_markdown": ""}

    assert ensure_brand_link(content, None, stage="test") is content
    assert ensure_brand_link(content, {"brand_name": "Nextly"}, stage="test") is content
    assert ensure_brand_link(content, {"brand_url": "https://nextly.test"}, stage="test") is content


# ── in the pipeline ──────────────────────────────────────────────────────────


def _failed(*names: str) -> list[dict]:
    return [{"name": n, "passed": False, "severity": "blocking", "detail": "x"} for n in names]


async def _validated_with(history: list[dict], attempts: int) -> dict:
    """The fabricated-citation article, validated with a repair history already behind it."""
    state = flow._state(flow._with_fabricated_citation())
    state["content"]["review"] = {"repair_attempts": attempts, "repair_history": history}
    return await validate_content(state)


async def test_no_second_attempt_for_a_check_the_first_one_worked_on():
    history = [{"attempt": 1, "accepted": True, "unresolved_checks": ["facts_and_external_links"]}]

    validated = await _validated_with(history, attempts=1)

    validation = validated["content"]["review"]["validation"]
    assert [c["name"] for c in validation["failed_checks"]] == ["facts_and_external_links"]
    assert validation["repair_required"] is False
    assert validation["gave_up"] is True  # it still fails, and no attempt runs for it
    assert validation_router(validated) == "humanize_content"


@pytest.mark.parametrize(
    "first",
    [
        {"attempt": 1, "accepted": False, "regressed_checks": ["keyword_density"]},
        {
            "attempt": 1,
            "accepted": True,
            "no_result": True,
            "unresolved_checks": ["facts_and_external_links"],
        },
    ],
)
async def test_a_second_attempt_still_follows_one_that_was_not_kept(first):
    validated = await _validated_with([first], attempts=1)

    validation = validated["content"]["review"]["validation"]
    assert validation["repair_required"] is True and validation["gave_up"] is False
    assert validation_router(validated) == "repair_content"


async def test_a_repair_is_asked_only_for_what_has_not_had_its_turn():
    validated = await _validated_with(
        [{"attempt": 1, "accepted": True, "unresolved_checks": ["unsupported_claims"]}], attempts=1
    )
    validated["content"]["review"]["validation"]["failed_checks"] = _failed(
        "facts_and_external_links", "unsupported_claims", "subheading_keyphrase"
    )
    survey = f" A [recent survey]({flow.FABRICATED}) says most teams agree."
    repairer = flow._fake_model(flow._echo(**{survey: ""}))

    with patch.object(repair_module, "load_content_model", return_value=repairer):
        out = await repair_content(validated)

    issues = flow._human_text(repairer.calls[0]).split("LINKS THAT MUST SURVIVE")[0]
    assert "facts_and_external_links" in issues and "unsupported_claims" not in issues
    attempt = out["content"]["review"]["repair_history"][-1]
    assert attempt["targeted_checks"] == ["facts_and_external_links", "subheading_keyphrase"]
    assert "unsupported_claims" not in attempt["unresolved_checks"]


async def test_a_model_that_returned_nothing_is_recorded_so_the_check_gets_another_turn():
    state = flow._state(flow._with_fabricated_citation())

    with patch.object(repair_module, "run_targeted_repair", return_value=None):
        out = await repair_content(await validate_content(state))

    (attempt,) = out["content"]["review"]["repair_history"]
    assert attempt["no_result"] is True and attempt["accepted"] is True
    assert validation_router(await validate_content(out)) == "repair_content"


async def test_the_brands_address_is_settled_before_the_checks_and_costs_no_attempt():
    article = flow._article()
    body = article["body_markdown"].replace(
        "Good crm software makes", "Good crm software such as Nextly makes"
    )
    state = flow._state({**article, "body_markdown": body})
    content = state["content"]
    spec = v.build_requirements_spec(
        content["outline"], "blog", flow.KW, flow.TITLE, generation_meta=content["generation_meta"]
    )

    with patch.object(v, "build_requirements_spec", return_value={**spec, "brand_context": BRAND}):
        validated = await validate_content(state)

    final = validated["content"]["final_content"]
    assert "such as [Nextly](https://nextly.test) makes" in final["body_markdown"]
    failed = [c["name"] for c in validated["content"]["review"]["validation"]["failed_checks"]]
    assert "brand_url_accuracy" not in failed


# ── a fact goes with the claim a repair removed ──────────────────────────────

# Words the rest of the article does not use: the facts check calls a fact stated when a fifth of
# its words appear anywhere in the prose.
FIGURE = "Zentrix Quorvex benchmarks measured 76 percent uplift."
FIGURE_SENTENCE = f" {FIGURE} ([study]({flow.CITATION}))."


def _with_a_cited_figure() -> dict:
    """The article with a figure in its prose that the facts list records with its source."""
    article = flow._article()
    return {
        **article,
        "body_markdown": article["body_markdown"].replace(
            flow._para(6), f"{flow._para(6)}{FIGURE_SENTENCE}"
        ),
        "facts": [{"text": FIGURE, "source_url": flow.CITATION}],
    }


def test_a_fact_whose_sentence_the_repair_removed_goes_with_it():
    before = _with_a_cited_figure()
    after = {**before, "body_markdown": before["body_markdown"].replace(FIGURE_SENTENCE, "")}

    kept = repair_module.without_facts_removed_with_a_claim(before, after)

    assert kept["facts"] == []
    assert kept["body_markdown"] == after["body_markdown"]


def test_a_fact_still_stated_or_never_stated_is_left_alone():
    before = _with_a_cited_figure()
    reworded = {
        **before,
        "body_markdown": before["body_markdown"].replace("benchmarks measured", "benchmarks found"),
    }
    assert repair_module.without_facts_removed_with_a_claim(before, reworded) is reworded

    # A fact the article never stated is the facts check's to report, not this one's to hide.
    never = {
        **before,
        "facts": [{"text": "Quorvex audits saw 91 percent churn.", "source_url": flow.CITATION}],
    }
    assert repair_module.without_facts_removed_with_a_claim(never, never) is never
    assert (
        repair_module.without_facts_removed_with_a_claim(before, {**before, "facts": []})["facts"]
        == []
    )


async def _repair_removing_the_figure(failed: list[str]) -> dict:
    """A repair, asked to fix `failed`, that takes the figure's sentence out."""
    validated = await validate_content(flow._state(_with_a_cited_figure()))
    validation = validated["content"]["review"]["validation"]
    assert "facts_and_external_links" not in [c["name"] for c in validation["failed_checks"]]
    validation["failed_checks"] = _failed(*failed)
    repairer = flow._fake_model(flow._echo(**{FIGURE_SENTENCE: ""}))
    with patch.object(repair_module, "load_content_model", return_value=repairer):
        return await repair_content(validated)


async def test_removing_an_unsupported_claim_and_its_figure_is_kept():
    out = await _repair_removing_the_figure(["unsupported_claims"])

    (attempt,) = out["content"]["review"]["repair_history"]
    assert attempt["accepted"] is True and attempt["regressed_checks"] == []
    final = out["content"]["final_content"]
    assert FIGURE not in final["body_markdown"]
    assert final["facts"] == []
    again = (await validate_content(out))["content"]["review"]["validation"]
    assert "facts_and_external_links" not in [c["name"] for c in again["failed_checks"]]


async def test_a_figure_lost_while_fixing_something_else_is_still_a_step_back():
    # Not asked to remove a claim: a cited figure that disappears is damage, and is not kept.
    out = await _repair_removing_the_figure(["brand_prominence"])

    (attempt,) = out["content"]["review"]["repair_history"]
    assert attempt["regressed_checks"] == ["facts_and_external_links"]
    assert attempt["accepted"] is False
    assert FIGURE in out["content"]["final_content"]["body_markdown"]
    assert out["content"]["final_content"]["facts"] == [
        {"text": FIGURE, "source_url": flow.CITATION}
    ]
