"""A failed check reads as words for the person, never as the repair step's instruction (G53).

The staging article f82b2431 showed its checks panel the model's prompt: "1 factual
claim(s) are not supported … Fix each one in place — remove or soften it, never replace it
with a guessed value, and do not add a generic disclaimer: …". The check's detail stays the
repair step's; the checklist (API and dashboard) shows a line written for the reader.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.api.models.content_models.content_seo_data import ContentSEOData
from src.flow.engines.content.generation import validation
from src.flow.engines.content.generation.claim_integrity import (
    Claim,
    describe_unsupported_claims,
)
from src.flow.engines.content.generation.persist_content import _validation_summary
from src.services.check_wording import USER_WORDING, public_seo_details, user_detail
from src.services.content_checklist import build_checklist

REPAIR_WORDING = (
    "Fix each one in place",
    "guessed value",
    "generic disclaimer",
    "claim(s)",
    "->",
    "[absolute_superlative]",
)


def _repair_detail(count: int) -> str:
    claims = [
        Claim("absolute_superlative", f"Tool {i} is the best tool on the market.", "the best")
        for i in range(count)
    ]
    return describe_unsupported_claims(claims)


def _no_repair_wording(text: str) -> None:
    for phrase in REPAIR_WORDING:
        assert phrase not in text, f"repair wording {phrase!r} reached the reader: {text!r}"


# The names the checks' results carry (`_fail("<name>", ...)`), which is what is saved: one
# differs from its function (`check_facts_and_external_links_integration` -> "facts_and_external_links").
CHECK_NAMES = sorted(
    set(
        re.findall(
            r'_(?:fail|pass)\(\s*"([a-z_]+)"', Path(validation.__file__).read_text(encoding="utf-8")
        )
    )
)
FROM_DETAIL = {"unsupported_claims", "meta_description_length"}


def test_every_check_has_words_for_the_reader():
    assert len(CHECK_NAMES) >= 25 and "facts_and_external_links" in CHECK_NAMES
    missing = [n for n in CHECK_NAMES if n not in FROM_DETAIL and n not in USER_WORDING]
    assert not missing
    for name in CHECK_NAMES:
        assert not user_detail(name, "").endswith("this check didn't pass."), name


@pytest.mark.parametrize(
    ("detail", "line"),
    [
        (
            "Meta description is 98 characters; aim for 120-156.",
            "The meta description is too short: search results have room for more.",
        ),
        (
            "Meta description is 171 characters; the maximum is 156. Rewrite it as a complete, "
            "shorter description that keeps the exact focus keyphrase.",
            "The meta description is too long: search results cut it off.",
        ),
    ],
)
def test_a_meta_description_reads_as_too_short_or_too_long(detail, line):
    assert user_detail("meta_description_length", detail) == line
    assert user_detail("meta_description_length", line) == line


@pytest.mark.parametrize(
    ("count", "line"),
    [
        (1, "1 claim isn't backed by a source: soften it or add a source."),
        (3, "3 claims aren't backed by a source: soften them or add sources."),
    ],
)
def test_unsupported_claims_read_as_a_count_and_what_to_do(count, line):
    detail = _repair_detail(count)
    assert "Fix each one in place" in detail  # the repair step keeps its instruction
    assert user_detail("unsupported_claims", detail) == line
    # The reader's line maps to itself, so a row saved in these words reads the same.
    assert user_detail("unsupported_claims", line) == line


def test_every_line_is_short_and_plain():
    for name in CHECK_NAMES:
        line = user_detail(name, _repair_detail(2))
        _no_repair_wording(line)
        assert "(s)" not in line and len(line) <= 90, line


def test_an_unknown_check_never_passes_its_detail_through():
    assert user_detail("new_check", "Rewrite paragraph 3 and never guess.") == (
        "New check: this check didn't pass."
    )


REVIEW = {
    "final_validation": {
        "passed": False,
        "gave_up": True,
        "stage": "post_humanize",
        "failed_checks": [
            {"name": "unsupported_claims", "severity": "blocking", "detail": _repair_detail(1)},
        ],
        "warnings": [
            {
                "name": "brand_context_heuristic",
                "severity": "warning",
                "detail": "Negative-sounding word(s) near brand mention: slow — verify tone manually.",
            }
        ],
    }
}


def test_the_saved_summary_carries_the_readers_words():
    summary = _validation_summary(REVIEW)
    assert summary["issues"] == [
        {
            "name": "unsupported_claims",
            "severity": "blocking",
            "detail": "1 claim isn't backed by a source: soften it or add a source.",
        }
    ]
    assert summary["warnings"][0]["detail"] == USER_WORDING["brand_context_heuristic"]


def _old_seo_details() -> str:
    """An article saved before this: the repair step's detail in its content checks."""
    return json.dumps(
        {
            "seo_score": 81,
            "content_checks": {
                "validation": {
                    "passed": False,
                    "gave_up": True,
                    "stage": "post_humanize",
                    "issues": [
                        {
                            "name": "unsupported_claims",
                            "severity": "blocking",
                            "detail": _repair_detail(1),
                        }
                    ],
                    "warnings": [],
                },
                "claims_to_verify": [{"category": "absolute_superlative"}],
            },
        }
    )


def test_the_api_checklist_of_an_older_article_reads_as_words_for_the_reader():
    checklist = build_checklist(readability_score=62, seo_details=_old_seo_details())
    issues = checklist["validation"]["issues"]
    assert [i["detail"] for i in issues] == [
        "1 claim isn't backed by a source: soften it or add a source."
    ]
    _no_repair_wording(json.dumps(checklist))


def test_the_api_seo_details_of_an_older_article_lose_the_repair_wording():
    row = ContentSEOData(seo_details=_old_seo_details(), readability_score=62)
    returned = row.to_dict()["seo_details"]
    _no_repair_wording(returned)
    parsed = json.loads(returned)
    assert parsed["seo_score"] == 81
    assert parsed["content_checks"]["claims_to_verify"] == [{"category": "absolute_superlative"}]
    # The row itself is untouched.
    assert "Fix each one in place" in row.seo_details


def test_seo_details_without_content_checks_come_back_as_they_are():
    plain = json.dumps({"seo_score": 70})
    assert public_seo_details(plain) == plain
    assert public_seo_details("not json, content_checks") == "not json, content_checks"
    assert public_seo_details(None) is None
