"""A run can't keep a stage's work unpaid, and a run whose credits can't be read doesn't start (G62).

With runs started in parallel, a stage's charge can be refused after another run spent the
balance. That stage's work isn't handed on, and the run ends there. The start check in
library_router fails closed.
"""

from uuid import UUID

import pytest
from langgraph.graph import END

import src.utils.credit_manager as credit_module
from src.flow.engines.router.credits import out_of_credits, unless_out_of_credits
from src.flow.engines.router.keyword_router import keyword_router
from src.flow.engines.router.library_router import library_router

USER_ID = "00000000-0000-0000-0000-000000000001"
WORKSPACE_ID = "00000000-0000-0000-0000-000000000002"


def _state(**payload):
    return {
        "serp_payload": {"user_id": USER_ID, "workspace_id": WORKSPACE_ID, "query": "q", **payload}
    }


@pytest.fixture
def quiet_credits(monkeypatch):
    """No credit events or owner notices leave the test."""
    monkeypatch.setattr(credit_module, "_emit_credit_event", lambda *a, **k: None)

    async def _notify(*a, **k):
        return None

    monkeypatch.setattr(credit_module, "notify_credit_owner", _notify)


def _balance(monkeypatch, value=None, raises=None):
    async def _get_balance(uid, workspace_id=None):
        assert uid == UUID(USER_ID)
        if raises:
            raise raises
        return value

    monkeypatch.setattr(credit_module, "_get_balance", _get_balance)


def _notify_now(monkeypatch, raises=None):
    sent = []

    async def notify_now(**kwargs):
        if raises:
            raise raises
        sent.append(kwargs)

    monkeypatch.setattr("src.services.notification_helper.notify_now", notify_now)
    return sent


# --- the start check fails closed --------------------------------------------------------


async def test_a_credit_check_that_raises_keeps_the_run_from_starting(monkeypatch, quiet_credits):
    _balance(monkeypatch, raises=RuntimeError("database unavailable"))
    sent = _notify_now(monkeypatch)

    assert await library_router(_state()) == "credit_check_failed"
    assert sent == []


async def test_a_caller_the_workspace_wont_pay_for_is_out_of_credits(monkeypatch, quiet_credits):
    _balance(
        monkeypatch,
        raises=credit_module.InsufficientCreditsError("membership", 15, 0),
    )

    assert await library_router(_state()) == "insufficient_credits"


async def test_a_short_balance_still_stops_the_run(monkeypatch, quiet_credits):
    _balance(monkeypatch, value=14)

    assert await library_router(_state()) == "insufficient_credits"


async def test_a_paid_run_starts_even_if_its_start_notice_fails(monkeypatch, quiet_credits):
    _balance(monkeypatch, value=15)
    _notify_now(monkeypatch, raises=RuntimeError("notifications down"))

    assert await library_router(_state()) == "serp_engine"


async def test_a_library_start_goes_to_its_item(monkeypatch, quiet_credits):
    _balance(monkeypatch, value=15)
    sent = _notify_now(monkeypatch)

    assert await library_router(_state(is_library=True)) == "load_library_item"
    assert sent == []  # a Library start announces itself once its item loads


async def test_the_failed_check_tells_the_user_to_try_again():
    from src.flow.engines.rext import CREDIT_CHECK_FAILED, _credit_check_failed

    result = await _credit_check_failed({})
    assert result == {
        "content": {"error": CREDIT_CHECK_FAILED, "error_code": "credit_check_failed"}
    }


async def test_the_failed_check_tells_a_streaming_page_at_once(monkeypatch):
    # The generation view that is streaming hears it as run.failed, as for an empty search (E27).
    import langgraph.config

    from src.flow.engines.rext import CREDIT_CHECK_FAILED, _credit_check_failed

    sent = []
    monkeypatch.setattr(langgraph.config, "get_stream_writer", lambda: sent.append)

    await _credit_check_failed({})

    assert sent == [
        {
            "type": "run",
            "step": "run.failed",
            "error_code": "credit_check_failed",
            "message": CREDIT_CHECK_FAILED,
        }
    ]


# --- a refused stage charge hands no work on -------------------------------------------


async def test_a_refused_charge_returns_no_node_result(monkeypatch, quiet_credits):
    _balance(monkeypatch, value=50)  # the pre-flight passes; another run spends meanwhile

    async def consume(user_id, cost, stage, workspace_id=None):
        raise credit_module.InsufficientCreditsError(stage, cost, 0)

    monkeypatch.setattr(credit_module, "consume_stage_credits", consume)

    @credit_module.deduct_credits("generate_outline")
    async def generate_outline(state):
        return {"content": {"outline": {"sections": ["paid work"]}}}

    result = await generate_outline(_state())

    assert "outline" not in result["content"]
    assert result["content"]["error_code"] == "insufficient_credits"
    assert out_of_credits(result)


async def test_a_paid_charge_keeps_the_node_result(monkeypatch, quiet_credits):
    _balance(monkeypatch, value=50)
    charged = []

    async def consume(user_id, cost, stage, workspace_id=None):
        charged.append(stage)

    monkeypatch.setattr(credit_module, "consume_stage_credits", consume)

    @credit_module.deduct_credits("generate_outline")
    async def generate_outline(state):
        return {"content": {"outline": {"sections": ["paid work"]}}}

    result = await generate_outline(_state())

    assert result == {"content": {"outline": {"sections": ["paid work"]}}}
    assert charged == ["generate_outline"]


def test_a_run_out_of_credits_ends_instead_of_going_on():
    route = unless_out_of_credits("review_outline")
    assert route({"content": {"error_code": "insufficient_credits"}}) == END
    assert route({"content": {"outline": {}}}) == "review_outline"
    assert route({}) == "review_outline"


def test_the_keyword_gate_ends_a_run_whose_title_charge_was_refused():
    state = {
        "seo_result": {"keyword_recommendations": {"is_changed": False, "titles_unpaid": True}}
    }
    assert keyword_router(state) == "INSUFFICIENT"


def test_an_earlier_runs_out_of_credits_error_doesnt_end_a_paid_answer():
    # A topped-up retry on the same thread: the old error is still in the checkpoint.
    state = {
        "content": {"error_code": "insufficient_credits"},
        "seo_result": {"keyword_recommendations": {"is_changed": False, "titles_unpaid": False}},
    }
    assert keyword_router(state) == "END"


async def test_a_new_run_starts_without_an_earlier_runs_error():
    from src.flow.engines.rext import _begin_run

    stale = {"content": {"error": "Insufficient credits", "error_code": "insufficient_credits"}}
    cleared = {
        "content": {
            "error": None,
            "error_code": None,
            "credits_deducted": False,
            "image_credit_deducted": False,
        }
    }
    assert await _begin_run(stale) == cleared
    assert await _begin_run({"content": {"outline": {}}}) == {}


async def test_a_new_run_on_a_finished_thread_pays_for_its_drafting():
    # A finished article's checkpoint keeps its paid marks; generate_content skips the
    # upfront charges and the image's while they are set, so a new run must clear them.
    from src.flow.engines.rext import _begin_run

    finished = {
        "content": {"final_content": {}, "credits_deducted": True, "image_credit_deducted": True}
    }
    assert await _begin_run(finished) == {
        "content": {
            "error": None,
            "error_code": None,
            "credits_deducted": False,
            "image_credit_deducted": False,
        }
    }


def test_the_graphs_end_the_run_where_a_charge_is_refused():
    from src.flow.engines.content.content_engine import create_content_engine
    from src.flow.engines.rext import create_rext_engine

    content_edges = {(e.source, e.target) for e in create_content_engine().get_graph().edges}
    assert ("generate_outline", "__end__") in content_edges
    assert ("generate_content", "__end__") in content_edges
    assert ("generate_outline", "review_outline") in content_edges
    assert ("generate_content", "validate_content") in content_edges

    rext_edges = {(e.source, e.target) for e in create_rext_engine().get_graph().edges}
    assert ("__start__", "begin_run") in rext_edges
    assert ("begin_run", "credit_check_failed") in rext_edges
    assert ("seo_engine", "insufficient_credits") in rext_edges


def test_the_keyword_gate_ends_a_run_whose_serp_charge_was_refused():
    # A re-analysis whose earlier pass was paid: this pass's refused SERP charge still ends it.
    state = {
        "seo_result": {
            "serp_backlinks": {"volume_status": "insufficient_credits"},
            "keyword_recommendations": {"is_changed": True, "titles_unpaid": False},
        }
    }
    assert keyword_router(state) == "INSUFFICIENT"
    paid = {"seo_result": {"serp_backlinks": {"volume_status": "ok"}}}
    assert keyword_router(paid) == "END"


def test_a_refused_serp_charge_saves_nothing_and_opens_no_gate():
    from src.flow.engines.seo.seo_engine import create_seo_engine

    edges = {(e.source, e.target) for e in create_seo_engine().get_graph().edges}
    assert ("fetch_dataforseo_backlinks", "__end__") in edges
    assert ("fetch_dataforseo_backlinks", "save_keyword_research") in edges


@pytest.mark.parametrize(
    ("state", "blocked_at"),
    [
        ({}, "library_router credit gate"),
        (
            {"seo_result": {"serp_backlinks": {"volume_status": "insufficient_credits"}}},
            "serp_seo charge",
        ),
        (
            {"seo_result": {"keyword_recommendations": {"titles_unpaid": True}}},
            "title_generation charge",
        ),
        (
            {
                "serp_payload": {"is_library": True},
                "content": {"error_code": "insufficient_credits"},
            },
            "library start charges",
        ),
    ],
    ids=["start gate", "serp charge", "title charge", "library charges"],
)
async def test_the_out_of_credits_record_names_where_the_run_stopped(
    monkeypatch, state, blocked_at
):
    from src.flow.engines.rext import _insufficient_credits
    from src.services.monitoring_service import MonitoringService

    recorded = []

    async def persist_error_log(**kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr(MonitoringService, "persist_error_log", persist_error_log)

    await _insufficient_credits(state)

    assert recorded[0]["metadata"]["blocked_at"] == blocked_at
