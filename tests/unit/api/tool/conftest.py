import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.runnables import RunnableLambda

from src.api.cache.redis_client import cache
from src.api.tool import limits, tools
from src.api.tool.schema.schema import (
    GrammarCheckerResponse,
    HeadlineAnalyzerResponse,
    IdeaGeneratorResponse,
    OutlineGeneratorResponse,
    OutlineSection,
    ParagraphRewriterResponse,
)


@pytest.fixture(autouse=True)
def free_tool_counts(monkeypatch):
    """Each test starts with no free-tool call counted, in memory rather than a shared Redis."""
    monkeypatch.setattr(cache, "redis", None)
    monkeypatch.setattr(limits, "COUNTS", limits.DayCounts())


# What each free tool's model answers here, so no test reaches the provider (G76, rext-control#613):
# numbered lines for the tools that read a list, a filled schema for those with structured output. A
# test that wants another answer patches tools._get_model itself, as the grammar checker's tests do.
LINES = "\n".join(
    [
        "1. How to Plan Your First Project Step by Step",
        "2. Seven Common Mistakes and How to Avoid Them",
        "3. What Changes When You Start Measuring Results",
        "4. A Simple Checklist for Getting It Right",
        "5. Why Small Teams Win with a Clear Plan",
    ]
)


def _structured(schema):
    answers = {
        OutlineGeneratorResponse: lambda: OutlineGeneratorResponse(
            title="A Practical Guide",
            meta_description="Everything to know, in order.",
            estimated_word_count=0,
            sections_count=0,
            sections=[
                OutlineSection(title=f"Part {n}", key_points=["A point"]) for n in range(1, 6)
            ],
        ),
        HeadlineAnalyzerResponse: lambda: HeadlineAnalyzerResponse(
            headline="",
            character_count=0,
            word_count=0,
            score=72,
            sentiment="Positive",
            reading_level="Grade 6",
        ),
        ParagraphRewriterResponse: lambda: ParagraphRewriterResponse(
            original_text="", rewritten_text="A clearer version of the paragraph.", goal=""
        ),
        IdeaGeneratorResponse: lambda: IdeaGeneratorResponse(
            topic="", ideas=["A first idea", "A second idea", "A third idea"]
        ),
        GrammarCheckerResponse: lambda: GrammarCheckerResponse(corrected_text="", issues=[]),
    }
    return answers[schema]()


class FakeToolModel(FakeListChatModel):
    """A chat model for the tool tests: LINES as text, or a filled schema for with_structured_output."""

    def with_structured_output(self, schema, **kwargs):
        return RunnableLambda(lambda _prompt: _structured(schema))


@pytest.fixture(autouse=True)
def fake_tool_model(monkeypatch):
    monkeypatch.setattr(tools, "_get_model", lambda tool: FakeToolModel(responses=[LINES]))
