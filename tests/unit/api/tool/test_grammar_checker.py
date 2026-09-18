from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.api.tool.schema.schema import GrammarCheckerResponse, GrammarIssue
from src.api.tool.tools import _is_protected_term, grammar_checker

client = TestClient(app)


# ---------------------------------------------------------------------------
# 1. Protected Technical Terms & Code Preservation Tests
# ---------------------------------------------------------------------------


def test_protected_technical_terms():
    # Technical brand names & package names
    assert _is_protected_term("Pydantic", "Using Pydantic for validation.") is True
    assert _is_protected_term("FastAPI", "Built with FastAPI framework.") is True

    # Python builtins & keywords
    assert _is_protected_term("str", "Returns a str object.") is True
    assert _is_protected_term("len", "Calculates len(data).") is True

    # Code identifiers (PascalCase, camelCase, snake_case)
    assert _is_protected_term("ContentIdea", "The ContentIdea class.") is True
    assert _is_protected_term("user_id", "Filter by user_id.") is True

    # Inline code & fenced code blocks
    assert _is_protected_term("custom_var", "Use `custom_var` here.") is True

    # Plain natural language words (not protected)
    assert _is_protected_term("recieve", "Did you recieve it?") is False
    assert _is_protected_term("This are", "This are a test.") is False


# ---------------------------------------------------------------------------
# 2. Grammar Checker Function Tests (Zero False Positives for Tech Terms)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grammar_checker_preserves_tech_terms():
    # Mock LLM output that might attempt false positive flags on Pydantic, str, ContentIdea, len
    mock_llm_response = GrammarCheckerResponse(
        corrected_text="Using Pedantic with STR and Content Idea and Len.",
        issues=[
            GrammarIssue(
                original_phrase="Pydantic", suggested_correction="Pedantic", issue_type="spelling"
            ),
            GrammarIssue(original_phrase="str", suggested_correction="STR", issue_type="spelling"),
            GrammarIssue(
                original_phrase="ContentIdea",
                suggested_correction="Content Idea",
                issue_type="spelling",
            ),
            GrammarIssue(original_phrase="len", suggested_correction="Len", issue_type="spelling"),
        ],
    )

    with patch("src.api.tool.tools._get_model") as mock_get_model:
        mock_model = MagicMock()
        mock_model.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=mock_llm_response
        )
        mock_get_model.return_value = mock_model

        input_text = "Using Pydantic with str and ContentIdea and len."
        res = await grammar_checker(input_text)

        # All false positives on tech terms must be filtered out
        assert len(res.issues) == 0
        assert res.corrected_text == input_text


@pytest.mark.asyncio
async def test_grammar_checker_detects_genuine_error():
    # Mock LLM returning a valid grammar issue alongside a false positive
    mock_llm_response = GrammarCheckerResponse(
        corrected_text="This is a test sentence with Pydantic.",
        issues=[
            GrammarIssue(
                original_phrase="This are", suggested_correction="This is", issue_type="grammar"
            ),
            GrammarIssue(
                original_phrase="Pydantic", suggested_correction="Pedantic", issue_type="spelling"
            ),
        ],
    )

    with patch("src.api.tool.tools._get_model") as mock_get_model:
        mock_model = MagicMock()
        mock_model.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=mock_llm_response
        )
        mock_get_model.return_value = mock_model

        input_text = "This are a test sentence with Pydantic."
        res = await grammar_checker(input_text)

        # Genuine error accepted, tech term false positive rejected
        assert len(res.issues) == 1
        assert res.issues[0].original_phrase == "This are"
        assert res.issues[0].suggested_correction == "This is"
        assert res.issues[0].issue_type == "grammar"
        assert res.corrected_text == "This is a test sentence with Pydantic."


# ---------------------------------------------------------------------------
# 3. API Route Endpoint Test
# ---------------------------------------------------------------------------


def test_grammar_checker_route_endpoint():
    mock_llm_response = GrammarCheckerResponse(
        corrected_text="This is a test.",
        issues=[
            GrammarIssue(
                original_phrase="This are", suggested_correction="This is", issue_type="grammar"
            )
        ],
    )

    with patch("src.api.tool.tools._get_model") as mock_get_model:
        mock_model = MagicMock()
        mock_model.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=mock_llm_response
        )
        mock_get_model.return_value = mock_model

        response = client.post("/api/v1/tools/grammar-checker", json={"text": "This are a test."})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "corrected_text" in data["data"]
        assert "issues" in data["data"]
        assert data["data"]["corrected_text"] == "This is a test."
