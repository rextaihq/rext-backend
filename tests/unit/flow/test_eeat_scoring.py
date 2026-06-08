import pytest

from src.flow.engines.content.review.content.eeat_trust import _assemble_markdown
from src.flow.engines.content.utils.eeat import (
    build_scoring_prompt,
    calculate_eeat_trust_score,
    compute_weighted_score,
    get_eeat_priority,
    resolve_confidence,
    score_status,
    validate_and_normalize,
)
from src.flow.prompts.system.eeat_scoring import PILLAR_SIGNALS
from src.flow.model.structure.eeat import EEATSignalScore, EEATPillarScore, EEATTrustScore
from src.flow.model.structure.outlines import CONTENT_TYPE_TO_MODEL


def _make_pillar(score: float, signal_id: str) -> EEATPillarScore:
    return EEATPillarScore(
        score=score,
        signals=[
            EEATSignalScore(
                signal_id=signal_id,
                label="Test signal",
                max_points=100,
                awarded_points=score,
                evidence="Example evidence from markdown.",
            )
        ],
    )


def _make_trust_score(
    experience: float = 70,
    expertise: float = 80,
    authoritativeness: float = 60,
    trustworthiness: float = 85,
) -> EEATTrustScore:
    return EEATTrustScore(
        score=75.0,
        status="good",
        experience=_make_pillar(experience, "experience_first_person"),
        expertise=_make_pillar(expertise, "expertise_terminology"),
        authoritativeness=_make_pillar(authoritativeness, "authority_bio"),
        trustworthiness=_make_pillar(trustworthiness, "trust_limitations"),
        reasoning="Strong practitioner content with cited sources.",
        recommendations=["Add more quantified outcomes."],
        confidence=80.0,
    )


def test_assemble_markdown_combines_title_intro_body() -> None:
    markdown = _assemble_markdown(
        {
            "title": "AI Workflow Guide",
            "introduction": "We tested three pipelines in production.",
            "body_markdown": "## Results\nLatency dropped 30%.",
        }
    )

    assert markdown.startswith("# AI Workflow Guide")
    assert "We tested three pipelines" in markdown
    assert "## Results" in markdown


def test_assemble_markdown_empty_when_no_content() -> None:
    assert _assemble_markdown({}) == ""


@pytest.mark.parametrize(
    ("content_type", "expected"),
    [
        ("blog", "high"),
        ("how-to-guide", "high"),
        ("in-depth-review", "high"),
        ("glossary", "medium"),
        ("pricing-page", "low"),
        ("checkout-page", "low"),
        ("unknown-type", "high"),
    ],
)
def test_eeat_priority_mapping(content_type: str, expected: str) -> None:
    assert get_eeat_priority(content_type) == expected


def test_all_outline_content_types_have_priority() -> None:
    for content_type in CONTENT_TYPE_TO_MODEL:
        assert get_eeat_priority(content_type) in {"high", "medium", "low"}


def test_score_status_bands() -> None:
    assert score_status(80) == "good"
    assert score_status(75) == "good"
    assert score_status(60) == "needs_work"
    assert score_status(50) == "needs_work"
    assert score_status(30) == "poor"


def test_weighted_overall_score() -> None:
    overall = compute_weighted_score(
        {
            "experience": 80.0,
            "expertise": 80.0,
            "authoritativeness": 80.0,
            "trustworthiness": 80.0,
        }
    )
    assert overall == 80.0


def test_pillar_signals_sum_to_100() -> None:
    for pillar, signals in PILLAR_SIGNALS.items():
        total = sum(max_pts for _, _, max_pts in signals)
        assert total == 100, f"{pillar} signals sum to {total}, expected 100"


def test_resolve_confidence_prefers_llm_value() -> None:
    result = _make_trust_score()
    markdown = "# Guide\n\nIn my experience, we reduced latency by 30%."

    assert resolve_confidence(82.5, markdown, result) == 82.5


def test_validate_and_normalize_uses_llm_confidence() -> None:
    result = _make_trust_score()
    result.confidence = 77.0
    markdown = "# Guide\n\nIn my experience, we reduced latency by 30%."

    normalized = validate_and_normalize(result, markdown)
    assert normalized["confidence"] == 77.0


def test_validate_and_normalize_recomputes_weighted_score() -> None:
    result = _make_trust_score(
        experience=70,
        expertise=80,
        authoritativeness=60,
        trustworthiness=90,
    )
    markdown = "# Guide\n\nIn my experience, we reduced latency by 30%."

    normalized = validate_and_normalize(result, markdown)

    expected = compute_weighted_score(
        {
            "experience": 70.0,
            "expertise": 80.0,
            "authoritativeness": 60.0,
            "trustworthiness": 90.0,
        }
    )
    assert normalized["score"] == expected
    assert normalized["trust_score"] == expected
    assert normalized["status"] == score_status(expected)
    assert normalized["scoring_scope"] == "content_level_only"
    assert "experience" in normalized["signal_breakdown"]


def test_build_scoring_prompt_uses_markdown_not_html() -> None:
    prompt = build_scoring_prompt(
        "# Title\n\nBody with [source](https://example.com).",
        {"content_type": "blog", "title": "Title"},
    )

    assert "MARKDOWN TO EVALUATE" in prompt
    assert "# Title" in prompt
    assert "<html" not in prompt.lower()
    assert "experience_first_person" in prompt
    assert "confidence" in prompt.lower()
    assert "CALIBRATION" in prompt.upper() or "calibration" in prompt.lower()


@pytest.mark.asyncio
async def test_calculate_eeat_trust_score_returns_four_pillars(monkeypatch) -> None:
    class FakeLLM:
        def with_structured_output(self, _schema):
            return self

        async def ainvoke(self, _prompt):
            return _make_trust_score()

    monkeypatch.setattr(
        "src.flow.model.llm_manager.load_model",
        lambda max_tokens=4096: FakeLLM(),
    )

    result = await calculate_eeat_trust_score(
        "# AI Guide\n\nIn my experience, we tested workflows and cut latency 30%.",
        {"content_type": "how-to-guide", "title": "AI Guide"},
    )

    assert result["experience"] == 70.0
    assert result["expertise"] == 80.0
    assert result["authoritativeness"] == 60.0
    assert result["trustworthiness"] == 85.0
    assert 0 <= result["score"] <= 100
    assert result["status"] in {"good", "needs_work", "poor"}
    assert result["content_type"] == "how-to-guide"


@pytest.mark.asyncio
async def test_calculate_eeat_trust_score_empty_markdown_returns_empty() -> None:
    result = await calculate_eeat_trust_score("")
    assert result == {}
