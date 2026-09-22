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
