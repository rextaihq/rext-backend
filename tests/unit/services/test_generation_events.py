"""The writing pipeline's analytics events (revnix/rext-control#712).

A run that starts, an article that is saved and a run that ends without one are each sent
once, after the fact, with a short list of numbers and words: never a keyword, a title or any
text. A send is started and not waited for, and nothing is sent or read without the project's
key.
"""

from datetime import datetime, timedelta, timezone

import httpx
import openai
import pytest

import src.services.generation_events as events

THREAD = "01a11a53-a984-7af3-a679-c6e6567ce36a"
USER = "5b0c2f0e-7d1c-4c58-9d3e-0d2f6a1b9c11"
WORKSPACE = "c1cf2b30-e377-4252-b64c-e5a7190a807f"
BEGAN = datetime(2026, 10, 8, 7, 0, 0, tzinfo=timezone.utc)


def _state(**content):
    return {
        "serp_payload": {
            "user_id": USER,
            "workspace_id": WORKSPACE,
            "query": "remote work productivity tips",
            "country": "United States",
            "is_library": False,
        },
        "content": {events.RUN_STARTED_AT: BEGAN.isoformat(), **content},
    }


@pytest.fixture
def announced(monkeypatch):
    """Every event the code under test starts, as (name, properties, state, how)."""
    seen = []
    monkeypatch.setattr(
        events,
        "_announce",
        lambda name, properties, state, **how: seen.append((name, properties, state, how)),
    )
    return seen


@pytest.fixture
def sent(monkeypatch):
    """With the project's key set: what reaches the sender, the send itself run to its end."""
    taken = []
    monkeypatch.setenv("POSTHOG_PROJECT_KEY", "phc_test")

    async def report(name, properties, **how):
        taken.append({"name": name, "properties": properties, **how})
        return True

    monkeypatch.setattr(events, "report_event", report)
    waiting = []
    monkeypatch.setattr(events, "send_soon", waiting.append)
    monkeypatch.setattr(events, "_thread_id", lambda: THREAD)
    return taken, waiting


async def _run(waiting):
    for sending in waiting:
        await sending


@pytest.mark.parametrize(
    ("country", "code"),
    [
        ("United States", "US"),
        ("united kingdom", "GB"),
        ("us", "US"),
        ("GB", "GB"),
        # A supported market the search provider's list of codes does not have.
        ("Andorra", "AD"),
        ("Democratic Republic of the Congo", "CD"),
        ("São Tomé and Príncipe", "ST"),
        ("Global", None),
        ("Atlantis", None),
        # Two letters that are no market of ours are not passed on.
        ("zz", None),
        ("", None),
        (None, None),
    ],
)
def test_a_runs_country_is_sent_as_its_two_letter_code(country, code):
    assert events.country_code(country) == code


def test_every_supported_market_has_a_code_of_its_own():
    """Review round 1: 74 supported countries had none, and their runs were sent without one."""
    import typing

    from src.flow.states.countries import SUPPORTED_COUNTRIES

    markets = [name for name in typing.get_args(SUPPORTED_COUNTRIES) if name != "Global"]
    codes = {name: events.country_code(name) for name in markets}

    assert [name for name, code in codes.items() if not code] == []
    assert all(len(code) == 2 and code.isalpha() and code.isupper() for code in codes.values())
    assert len(set(codes.values())) == len(markets)


@pytest.mark.parametrize(
    ("answered", "sent_as"),
    [
        ("blog", "blog"),
        ("How-To Guide", "how-to-guide"),
        ("landing_page", "landing-page"),
        # Not a type the product offers: whatever a changed client sent stays here.
        ("customer-x-roadmap", None),
        ("sk-secret", None),
        ("", None),
        (None, None),
    ],
)
def test_only_an_offered_content_type_is_ever_sent(answered, sent_as):
    """Review round 1: the content-type step takes its answer as sent, and a short word is
    what the sender lets through."""
    assert events.offered_content_type(answered) == sent_as


async def test_a_started_run_says_where_it_came_from_and_its_country(sent):
    taken, waiting = sent
    library = _state()
    library["serp_payload"]["is_library"] = True

    events.announce_started(_state())
    events.announce_started(library, country="United Kingdom")
    await _run(waiting)

    assert [event["name"] for event in taken] == ["content_generation_started"] * 2
    assert taken[0]["properties"] == {"from_library": False, "country": "US"}
    # A Library start's item has its own country.
    assert taken[1]["properties"] == {"from_library": True, "country": "GB"}
    first = taken[0]
    # Who and where; whether the event may name them, and their plan, is the sender's to read.
    assert str(first["user_id"]) == USER and str(first["workspace_id"]) == WORKSPACE
    assert set(first) == {"name", "properties", "key", "occurred_at", "user_id", "workspace_id"}
    # The run is its thread and when it began: a node run twice sends one event.
    assert first["key"] == f"{THREAD}:{BEGAN.isoformat()}"
    assert first["occurred_at"] == BEGAN


async def test_a_run_without_a_country_on_the_list_sends_none(sent):
    taken, waiting = sent
    state = _state()
    state["serp_payload"]["country"] = "Global"

    events.announce_started(state)
    await _run(waiting)

    assert taken[0]["properties"] == {"from_library": False}


async def test_a_saved_article_says_its_type_words_seconds_and_repairs(sent):
    taken, waiting = sent
    saved_at = BEGAN + timedelta(seconds=312, microseconds=400_000)

    events.announce_completed(
        _state(review={"repair_attempts": 2}),
        thread_id=THREAD,
        content_type="how-to-guide",
        word_count=1840,
        # A row's own time, as the database returns it.
        saved_at=saved_at.replace(tzinfo=None),
    )
    await _run(waiting)

    assert taken[0]["name"] == "content_generation_completed"
    assert taken[0]["properties"] == {
        "content_type": "how-to-guide",
        "word_count": 1840,
        "seconds": 312,
        "repairs": 2,
    }
    # The same save again (it is idempotent by thread) is the same event at the same time.
    assert taken[0]["occurred_at"] == saved_at
    assert taken[0]["key"] == f"{THREAD}:{BEGAN.isoformat()}"


async def test_a_thread_started_again_is_counted_at_its_own_save_not_the_first_runs(sent):
    """Review round 1: the second run saves into the row the first made, whose time is before
    this run began."""
    taken, waiting = sent
    first_runs_row = BEGAN - timedelta(hours=3)

    events.announce_completed(
        _state(), thread_id=THREAD, content_type="blog", word_count=1500, saved_at=first_runs_row
    )
    await _run(waiting)

    saved = taken[0]["occurred_at"]
    assert datetime.now(timezone.utc) - saved < timedelta(seconds=5)
    assert taken[0]["properties"]["seconds"] == round((saved - BEGAN).total_seconds())


async def test_an_article_with_no_repairs_and_no_start_mark_still_counts(sent):
    taken, waiting = sent
    older = _state()
    del older["content"][events.RUN_STARTED_AT]

    events.announce_completed(older, thread_id=THREAD, content_type=None, word_count=900)
    await _run(waiting)

    # A run that began before the mark existed has no seconds to give, and says nothing false.
    assert taken[0]["properties"] == {"word_count": 900, "repairs": 0}
    # The sender asks for a time on every event: with no saved row's, the moment of the save.
    assert datetime.now(timezone.utc) - taken[0]["occurred_at"] < timedelta(seconds=5)


async def test_a_failed_run_says_its_stage_and_a_class_of_reason(sent):
    taken, waiting = sent

    events.announce_failed(_state(), stage=events.OUTLINE, reason=events.PROVIDER)
    await _run(waiting)

    properties = taken[0]["properties"]
    assert taken[0]["name"] == "content_generation_failed"
    assert (properties["stage"], properties["reason"]) == ("outline", "provider")
    assert isinstance(properties["seconds"], int) and properties["seconds"] >= 0
    assert set(properties) == {"stage", "reason", "seconds"}


async def test_no_text_of_the_run_is_ever_among_the_properties(sent):
    taken, waiting = sent
    state = _state(
        selected_topic="Remote Work Productivity Tips: Mastering the 3-3-3 Rule",
        error="Search results could not be loaded for this keyword.",
        outline={"title": "Remote Work Productivity Tips"},
    )

    events.announce_started(state)
    events.announce_failed(state, stage=events.ANALYSIS, reason=events.PROVIDER)
    events.announce_completed(state, thread_id=THREAD, content_type="blog", word_count=1500)
    await _run(waiting)

    words = " ".join(str(value) for event in taken for value in event["properties"].values())
    for text in ("remote", "Remote", "Search results", "3-3-3"):
        assert text not in words


def test_without_the_projects_key_nothing_is_started_or_read(monkeypatch):
    monkeypatch.delenv("POSTHOG_PROJECT_KEY", raising=False)
    started = []
    monkeypatch.setattr(events, "send_soon", started.append)

    events.announce_started(_state())
    events.announce_failed(_state(), stage=events.ARTICLE, reason=events.INTERNAL)
    events.announce_completed(_state(), thread_id=THREAD, content_type="blog", word_count=1)

    assert started == []


def test_an_event_that_cannot_be_started_never_reaches_the_run(monkeypatch):
    monkeypatch.setenv("POSTHOG_PROJECT_KEY", "phc_test")

    def broken(sending):
        sending.close()
        raise RuntimeError("no loop")

    monkeypatch.setattr(events, "send_soon", broken)

    events.announce_started(_state())  # does not raise


def test_every_event_and_property_sent_from_here_is_on_the_senders_list(monkeypatch):
    """The sender drops what is not listed and logs its name: a property missing from its
    list would vanish without a failing test."""
    from src.services.server_events import EVENT_PROPERTIES

    monkeypatch.setenv("POSTHOG_PROJECT_KEY", "phc_test")
    seen = {}

    def started(sending):
        frame = sending.cr_frame.f_locals
        seen.setdefault(frame["name"], set()).update(frame["properties"])
        sending.close()

    monkeypatch.setattr(events, "send_soon", started)
    monkeypatch.setattr(events, "_thread_id", lambda: THREAD)

    events.announce_started(_state())
    events.announce_completed(
        _state(review={"repair_attempts": 1}), thread_id=THREAD, content_type="blog", word_count=9
    )
    events.announce_failed(_state(), stage=events.TITLES, reason=events.REFUSED)

    assert set(seen) == {events.STARTED, events.COMPLETED, events.FAILED}
    for name, properties in seen.items():
        assert properties == EVENT_PROPERTIES[name]


# -- Where the pipeline says them ------------------------------------------------------------


async def test_a_new_run_notes_when_it_began():
    from src.flow.engines.rext import _begin_run

    before = datetime.now(timezone.utc)
    update = await _begin_run({"content": {"outline": {}}})

    began = events.run_started_at(update)
    assert before <= began <= datetime.now(timezone.utc)
    # A run started again on a finished thread gets its own beginning, beside what it clears.
    again = await _begin_run({"content": {"error_code": "insufficient_credits"}})
    assert again["content"]["error_code"] is None
    assert events.run_started_at(again) >= began


async def test_a_thread_started_again_counts_its_own_repairs_only(sent):
    """Review round 2: the count is kept in the thread's review, which a new run inherits. The
    run's first node clears it, so a second article repaired once says one, not three."""
    from src.flow.engines.rext import _begin_run
    from src.flow.states.reducers.custom_reducer import deep_merge_dicts

    taken, waiting = sent
    first_run = {"final_content": {}, "review": {"repair_attempts": 2, "repair_history": [{}, {}]}}
    content = deep_merge_dicts(first_run, (await _begin_run({"content": first_run}))["content"])
    # The second run's one repair, as the repair step counts it.
    content["review"]["repair_attempts"] = content["review"].get("repair_attempts", 0) + 1

    events.announce_completed(
        {**_state(), "content": content}, thread_id=THREAD, content_type="blog", word_count=1500
    )
    await _run(waiting)

    assert taken[0]["properties"]["repairs"] == 1


async def test_the_runs_end_points_before_the_titles_say_why(announced, monkeypatch):
    from src.flow.engines import rext

    async def no_log(**_):
        return None

    monkeypatch.setattr(
        "src.services.monitoring_service.MonitoringService.persist_error_log", no_log
    )

    await rext._insufficient_credits(_state())
    await rext._insufficient_credits(
        {**_state(), "seo_result": {"keyword_recommendations": {"titles_unpaid": True}}}
    )
    await rext._credit_check_failed(_state())
    await rext._no_serp_data({**_state(), "serp_result": {"serp_status": "no_results"}})
    await rext._no_serp_data({**_state(), "serp_result": {"serp_status": "lookup_failed"}})

    assert [(name, p["stage"], p["reason"]) for name, p, _, _ in _plain(announced)] == [
        ("content_generation_failed", "analysis", "refused"),
        ("content_generation_failed", "titles", "refused"),
        ("content_generation_failed", "analysis", "internal"),
        ("content_generation_failed", "analysis", "refused"),
        ("content_generation_failed", "analysis", "provider"),
    ]


def _plain(announced):
    """The announced events as their callers gave them (the seconds vary)."""
    return [
        (name, {k: v for k, v in properties.items() if k != "seconds"}, state, how)
        for name, properties, state, how in announced
    ]


async def test_a_run_without_titles_says_whose_it_is_to_fix(announced):
    from src.flow.engines.content.generation import topic_generation

    await topic_generation.topics_failed(_state())
    await topic_generation.topics_failed(_state(error=topic_generation.KEYWORD_TOO_LONG_MESSAGE))

    assert [(p["stage"], p["reason"]) for _, p, _, _ in _plain(announced)] == [
        ("titles", "internal"),
        ("titles", "refused"),
    ]


async def test_an_outage_says_which_step_it_stopped(announced):
    from src.flow.engines.content.generation.provider_unavailable import stop_on_outage

    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")

    def out():
        return openai.RateLimitError(
            "Error code: 429",
            response=httpx.Response(429, request=request),
            body={"type": "insufficient_quota", "code": "credit_balance_exhausted"},
        )

    async def generate_outline(state):
        raise out()

    async def generate_content(state):
        raise out()

    async def other(state):
        raise ValueError("not an outage")

    await stop_on_outage(generate_outline)(_state())
    await stop_on_outage(generate_content)(_state())
    with pytest.raises(ValueError):
        await stop_on_outage(other)(_state())

    assert [(p["stage"], p["reason"]) for _, p, _, _ in _plain(announced)] == [
        ("outline", "provider"),
        ("article", "provider"),
    ]


def test_a_charge_refused_inside_the_content_steps_says_which_one(announced):
    """The run ends there with no node of its own, so the route says it."""
    from langgraph.graph import END

    from src.flow.engines.content.content_engine import create_content_engine

    branches = create_content_engine().builder.branches
    refused = {**_state(), "content": {"error_code": "insufficient_credits"}}
    for node in ("generate_outline", "generate_content"):
        (route,) = (spec.path for spec in branches[node].values())
        assert route.invoke(refused) == END
        # A run that goes on, or one an outage stopped (its own node says that), adds nothing.
        route.invoke(_state())

    assert [(p["stage"], p["reason"]) for _, p, _, _ in _plain(announced)] == [
        ("outline", "refused"),
        ("article", "refused"),
    ]
