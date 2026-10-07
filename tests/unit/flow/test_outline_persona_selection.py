"""The persona chosen in the outline step is the one the article is written as.

Covers the three ways the choice can arrive at the review node — kept, changed,
or cleared — and the middleware that turns it into the author identity handed to
the writer model.
"""

import pytest

import src.flow.engines.content.review.outline as review_module
from src.flow.engines.agent.middleware.persona_middleware import PersonaInjectionMiddleware


def _state(selected_persona_id="recommended-persona"):
    return {
        "content": {
            "content_type": "blog",
            "outline": {
                "title": "Technical SEO audits",
                "sections": [],
                "selected_persona_id": selected_persona_id,
                "persona_recommendations": [
                    {"persona_id": "recommended-persona", "name": "Sara", "score": 61.0},
                    {"persona_id": "other-persona", "name": "Amir", "score": 12.0},
                ],
            },
        }
    }


def _approved_outline(monkeypatch, review_response, state=None):
    monkeypatch.setattr(review_module, "interrupt", lambda _payload: review_response)
    result = review_module.review_outline(state or _state())
    return result["content"]["outline"]


@pytest.mark.unit
def test_recommended_persona_is_kept_when_the_user_changes_nothing(monkeypatch):
    outline = _approved_outline(monkeypatch, {"action": "approve"})

    assert outline["selected_persona_id"] == "recommended-persona"


@pytest.mark.unit
def test_user_can_choose_a_different_persona(monkeypatch):
    outline = _approved_outline(
        monkeypatch, {"action": "approve", "selected_persona_id": "other-persona"}
    )

    assert outline["selected_persona_id"] == "other-persona"


@pytest.mark.unit
def test_user_can_clear_the_persona(monkeypatch):
    """An explicit null means "no author persona" — not "use the recommendation"."""
    outline = _approved_outline(monkeypatch, {"action": "approve", "selected_persona_id": None})

    assert outline["selected_persona_id"] is None


@pytest.mark.unit
def test_blank_persona_id_is_treated_as_cleared(monkeypatch):
    outline = _approved_outline(monkeypatch, {"action": "approve", "selected_persona_id": "   "})

    assert outline["selected_persona_id"] is None


@pytest.mark.unit
def test_persona_recommendations_reach_the_review_interrupt(monkeypatch):
    captured = {}

    def _interrupt(payload):
        captured.update(payload)
        return {"action": "approve"}

    monkeypatch.setattr(review_module, "interrupt", _interrupt)
    review_module.review_outline(_state())

    assert captured["persona_recommendations"][0]["persona_id"] == "recommended-persona"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_middleware_writes_with_no_persona_when_the_user_cleared_it():
    """No fallback to "whichever persona is newest" — that ignored the user."""
    middleware = PersonaInjectionMiddleware.__new__(PersonaInjectionMiddleware)

    persona = await middleware._fetch_best_persona(
        "workspace-1", {"title": "x", "selected_persona_id": None}
    )

    assert persona is None


# -- The persona is always the workspace's own (FB2.18, rext-control#699) ----------------

WORKSPACE = "11111111-1111-1111-1111-111111111111"
PERSONA = "22222222-2222-2222-2222-222222222222"


def _sql(query) -> str:
    return " ".join(str(query).split())


@pytest.mark.unit
def test_the_chosen_persona_is_looked_up_inside_the_workspace_only():
    from src.flow.engines.agent.middleware.persona_middleware import persona_query

    sql = _sql(persona_query(WORKSPACE, PERSONA))

    assert "persona.workspace_id = :workspace_id_1" in sql
    assert "persona.id = :id_1" in sql
    # No "newest persona" in place of a choice that finds nothing.
    assert "ORDER BY" not in sql and "LIMIT" not in sql


@pytest.mark.unit
def test_without_a_choice_the_newest_persona_of_the_workspace_is_used():
    from src.flow.engines.agent.middleware.persona_middleware import persona_query

    sql = _sql(persona_query(WORKSPACE, None))

    assert "persona.workspace_id = :workspace_id_1" in sql and "persona.id =" not in sql
    assert "ORDER BY persona.created_at DESC" in sql and "LIMIT" in sql


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _Db:
    """Answers each statement with the next prepared value, and keeps the statements."""

    def __init__(self, *values):
        self.values = list(values)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(_sql(statement))
        return _Result(self.values.pop(0))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_another_workspaces_persona_is_not_saved_on_an_article():
    from uuid import UUID

    from src.services.content_service import ContentService

    service = ContentService(_Db(None, UUID(PERSONA)))

    assert await service._workspace_persona_id(UUID(WORKSPACE), UUID(PERSONA)) is None
    assert await service._workspace_persona_id(UUID(WORKSPACE), UUID(PERSONA)) == UUID(PERSONA)
    assert await service._workspace_persona_id(UUID(WORKSPACE), None) is None
    assert len(service.db.statements) == 2
    for sql in service.db.statements:
        assert "persona.id = :id_1" in sql and "persona.workspace_id = :workspace_id_1" in sql


@pytest.mark.unit
@pytest.mark.asyncio
async def test_publishing_reads_the_author_persona_inside_the_articles_workspace():
    from types import SimpleNamespace
    from uuid import UUID

    from src.services.content_service import ContentService

    service = ContentService(_Db(None))
    content = SimpleNamespace(id="c", persona_id=UUID(PERSONA), workspace_id=UUID(WORKSPACE))

    assert await service.author_persona_for(content) is None
    assert "persona.workspace_id = :workspace_id_1" in service.db.statements[0]


# -- The length the gate accepts is the content type's own -------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("content_type", "words", "kept"),
    [
        ("contact-us", 250, True),  # under the old 500 floor; this type takes 200 to 1,500
        ("white-paper", 7000, True),  # over the old 5,000 ceiling; takes up to 15,000
        ("landing-page", 3000, False),  # a landing page takes 400 to 1,200
        ("blog", 100, False),
        ("pricing-page", 300, True),  # no range of its own: the wide default
    ],
)
def test_the_length_the_screen_offers_is_the_length_the_gate_keeps(
    monkeypatch, content_type, words, kept
):
    state = _state()
    state["content"]["content_type"] = content_type
    state["content"]["outline"]["target_word_count"] = 900

    outline = _approved_outline(
        monkeypatch, {"action": "approve", "target_word_count": words}, state
    )

    assert outline["target_word_count"] == (words if kept else 900)


@pytest.mark.unit
def test_a_length_past_what_the_writer_can_return_is_brought_down_to_it(monkeypatch):
    from src.flow.model.llm_manager import CONTENT_GENERATION_MAX_TOKENS
    from src.flow.model.structure.outlines import WRITER_MAX_TARGET_WORDS

    state = _state()
    state["content"]["content_type"] = "white-paper"
    state["content"]["outline"]["target_word_count"] = 3000

    outline = _approved_outline(
        monkeypatch, {"action": "approve", "target_word_count": 12000}, state
    )

    assert outline["target_word_count"] == WRITER_MAX_TARGET_WORDS
    # The two numbers move together: a longer article needs a larger response first.
    assert WRITER_MAX_TARGET_WORDS * 2 <= CONTENT_GENERATION_MAX_TOKENS


@pytest.mark.unit
def test_the_workspace_id_is_bound_as_a_uuid_though_the_state_holds_text():
    from uuid import UUID

    from src.flow.engines.agent.middleware.persona_middleware import persona_query

    params = persona_query(WORKSPACE, PERSONA).compile().params

    assert params == {"workspace_id_1": UUID(WORKSPACE), "id_1": UUID(PERSONA)}
