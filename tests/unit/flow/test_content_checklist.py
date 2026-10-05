"""The checklist beside a finished article: readability band, density status,
the validator's findings and the claims to verify, on the saved article's
response and in the run's final state."""

import json
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import src.api.database.async_database as database_module
import src.flow.engines.content.generation.persist_content as persist_module
import src.services.content_service as service_module
import src.services.notification_helper as notification_module
import src.utils.loop_bridge as loop_module
from src.api.schema.content_schema import ContentResponse
from src.services.content_checklist import build_checklist, parse_seo_details, readability_band


@pytest.mark.parametrize(
    ("score", "band"),
    [
        (95, "very_easy"),
        (90, "very_easy"),
        (89.9, "easy"),
        (72, "fairly_easy"),
        (60, "standard"),
        (55.5, "fairly_difficult"),
        (30, "difficult"),
        (12, "very_difficult"),
        (-15, "very_difficult"),
        ("64.2", "standard"),
    ],
)
def test_readability_band(score, band):
    assert readability_band(score)["band"] == band


@pytest.mark.parametrize("score", [None, "", "n/a"])
def test_no_score_no_band(score):
    assert readability_band(score) is None


def test_band_carries_score_and_label():
    assert readability_band(64.234) == {"score": 64.2, "band": "standard", "label": "Standard"}


@pytest.mark.parametrize(
    ("raw", "parsed"),
    [
        (None, {}),
        ("", {}),
        ("not json", {}),
        ("[1, 2]", {}),
        ('{"a": 1}', {"a": 1}),
        ({"a": 1}, {"a": 1}),
    ],
)
def test_parse_seo_details(raw, parsed):
    assert parse_seo_details(raw) == parsed


ON_PAGE = {
    "seo_health_score": 88,
    "content_quality": {
        "focus_keyphrase": "headless cms",
        "keyphrase_density": 1.4,
        "keyphrase_occurrences": 9,
        "keyphrase_density_status": "ok",
        "keyphrase_density_detail": "Within range.",
    },
}
CHECKS = {
    "validation": {
        "passed": False,
        "gave_up": True,
        "stage": "post_humanize",
        "issues": [{"name": "word_count_band", "severity": "blocking", "detail": "Too short."}],
        "warnings": [],
    },
    "claims_to_verify": [
        {"category": "statistic", "sentence": "73% of teams switched.", "unsupported": "73%"}
    ],
}


def test_checklist_from_a_saved_row():
    checklist = build_checklist(
        readability_score=61, seo_details=json.dumps({**ON_PAGE, "content_checks": CHECKS})
    )

    assert checklist["readability"]["band"] == "standard"
    assert checklist["keyphrase_density"] == {
        "value": 1.4,
        "status": "ok",
        "occurrences": 9,
        "detail": "Within range.",
    }
    assert checklist["validation"]["gave_up"] is True
    assert checklist["claims_to_verify"][0]["unsupported"] == "73%"
    ContentResponse.model_validate({**_row(), "checklist": checklist})  # the response accepts it


def test_checklist_of_an_older_or_hand_written_article():
    for seo_details in (None, json.dumps(ON_PAGE)):
        checklist = build_checklist(readability_score=None, seo_details=seo_details)
        assert checklist["readability"] is None
        assert checklist["validation"] is None
        assert checklist["claims_to_verify"] == []
    assert build_checklist(readability_score=None, seo_details=None)["keyphrase_density"] is None


def _row():
    return {
        "id": uuid.uuid4(),
        "workspace_id": uuid.uuid4(),
        "created_by_user_id": uuid.uuid4(),
        "title": "T",
        "slug": "t",
        "status": "draft",
        "content_language": "English",
        "created_at": "2026-10-05T00:00:00Z",
    }


# --- the saved article's response ---------------------------------------------


async def test_get_content_adds_the_checklist(monkeypatch):
    seo = SimpleNamespace(
        readability_score=72.0, seo_details=json.dumps({**ON_PAGE, "content_checks": CHECKS})
    )
    content = SimpleNamespace(seo_data=seo, to_dict=lambda include_relationships: _row())
    service = service_module.ContentService(db=None)
    monkeypatch.setattr(service, "_get_content_or_404", AsyncMock(return_value=content))

    data = await service.get_content(uuid.uuid4(), uuid.uuid4())

    assert data["checklist"]["readability"]["band"] == "fairly_easy"
    assert data["checklist"]["validation"]["issues"][0]["name"] == "word_count_band"
    assert (
        ContentResponse.model_validate(data).checklist.claims_to_verify[0].category == "statistic"
    )


async def test_get_content_without_seo_data_has_no_checklist(monkeypatch):
    content = SimpleNamespace(seo_data=None, to_dict=lambda include_relationships: _row())
    service = service_module.ContentService(db=None)
    monkeypatch.setattr(service, "_get_content_or_404", AsyncMock(return_value=content))

    assert (await service.get_content(uuid.uuid4(), uuid.uuid4()))["checklist"] is None


# --- what the run saves ------------------------------------------------------------


def test_validation_summary_prefers_the_final_check():
    review = {
        "validation": {
            "passed": False,
            "gave_up": True,
            "stage": "pre_repair",
            "failed_checks": [],
        },
        "final_validation": {
            "passed": False,
            "gave_up": True,
            "stage": "post_humanize",
            "failed_checks": [
                {
                    "name": "brand_integration_depth",
                    "passed": False,
                    "severity": "blocking",
                    "detail": "d",
                }
            ],
            "warnings": [{"name": "x", "passed": False, "severity": "warning", "detail": None}],
        },
    }

    summary = persist_module._validation_summary(review)

    assert summary == {
        "passed": False,
        "gave_up": True,
        "stage": "post_humanize",
        "issues": [{"name": "brand_integration_depth", "severity": "blocking", "detail": "d"}],
        "warnings": [{"name": "x", "severity": "warning", "detail": ""}],
    }
    assert (
        persist_module._validation_summary({"validation": review["validation"]})["stage"]
        == "pre_repair"
    )
    assert persist_module._validation_summary({}) is None


def _state(body):
    return {
        "serp_payload": {
            "query": "headless cms",
            "user_id": str(uuid.uuid4()),
            "workspace_id": str(uuid.uuid4()),
        },
        "content": {
            "selected_topic": "Headless CMS for small teams",
            "content_type": "blog",
            "outline": {"title": "Headless CMS for small teams"},
            "final_content": {
                "title": "Headless CMS for small teams",
                "introduction": "A short introduction.",
                "body_markdown": body,
            },
            "review": {
                "on_page_metrics": ON_PAGE,
                "readability_metrics": {"flesch_reading_ease": 66.0},
                "final_validation": {"passed": True, "gave_up": False, "stage": "post_humanize"},
            },
        },
    }


def test_claims_to_verify_lists_an_unsupported_figure():
    state = _state("## Why\n\nIn 2025, 73% of small teams moved to a headless CMS.")

    claims = persist_module._claims_to_verify(state, state["content"])

    assert claims and claims[0]["category"] == "statistic"
    assert "73%" in claims[0]["unsupported"]
    assert set(claims[0]) == {"category", "sentence", "unsupported"}


def test_claims_to_verify_never_raises(monkeypatch):
    import src.flow.engines.content.generation.requirements_spec as spec_module

    monkeypatch.setattr(spec_module, "build_requirements_spec", lambda *_a, **_k: 1 / 0)
    state = _state("Text.")

    assert persist_module._claims_to_verify(state, state["content"]) == []


async def test_persist_saves_the_checks_and_returns_the_checklist(monkeypatch):
    saved = {}

    class FakeService:
        def __init__(self, db):
            pass

        async def create_content(self, workspace_id, user_id, payload):
            saved["payload"] = payload
            return SimpleNamespace(id=uuid.uuid4())

    @asynccontextmanager
    async def fake_db():
        yield None

    monkeypatch.setattr(service_module, "ContentService", FakeService)
    monkeypatch.setattr(database_module, "get_pooled_langgraph_db_context", fake_db)
    monkeypatch.setattr(loop_module, "run_on_main_loop", lambda coro: coro)
    monkeypatch.setattr(notification_module, "notify_now", AsyncMock())
    state = _state("## Why\n\nIn 2025, 73% of small teams moved to a headless CMS.")

    result = await persist_module.persist_content(
        state, {"configurable": {"thread_id": str(uuid.uuid4())}}
    )

    details = json.loads(saved["payload"].seo_data.seo_details)
    assert details["seo_health_score"] == 88  # the on-page analysis is kept
    assert details["content_checks"]["validation"]["passed"] is True
    assert details["content_checks"]["claims_to_verify"][0]["category"] == "statistic"
    checklist = result["content"]["review"]["checklist"]
    assert checklist["readability"]["band"] == "standard"
    assert checklist["keyphrase_density"]["status"] == "ok"
    assert checklist == build_checklist(readability_score=66.0, seo_details=details)


def test_a_failure_the_final_check_does_not_rerun_is_carried_forward():
    review = {
        "validation": {
            "passed": False,
            "gave_up": True,
            "stage": "pre_repair",
            "failed_checks": [
                {
                    "name": "required_sections",
                    "passed": False,
                    "severity": "blocking",
                    "detail": "s",
                },
                # rechecked after humanizing, so the final verdict decides
                {"name": "word_count_band", "passed": False, "severity": "blocking", "detail": "w"},
            ],
        },
        "final_validation": {"passed": True, "gave_up": False, "stage": "post_humanize"},
    }

    summary = persist_module._validation_summary(review)

    assert summary["passed"] is False
    assert summary["gave_up"] is True
    assert [i["name"] for i in summary["issues"]] == ["required_sections"]
    assert summary["stage"] == "post_humanize"


def test_a_clean_final_check_after_a_clean_gate_passes():
    review = {
        "validation": {"passed": True, "gave_up": False, "failed_checks": []},
        "final_validation": {"passed": True, "gave_up": False, "stage": "post_humanize"},
    }

    assert persist_module._validation_summary(review)["passed"] is True


def test_claims_in_the_meta_description_are_listed():
    state = _state("## Why\n\nPlain advice.")
    state["content"]["final_content"]["meta_description"] = (
        "In 2025, 73% of small teams moved to a headless CMS."
    )

    claims = persist_module._claims_to_verify(state, state["content"])

    assert claims and "73%" in claims[0]["unsupported"]
