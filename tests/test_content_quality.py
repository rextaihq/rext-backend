from types import SimpleNamespace

from src.utils.content_quality import assess_content_quality, build_thin_content_document


def _fake_result(raw_markdown: str, fit_markdown: str = None, url: str = "https://example.com"):
    """Build a fake crawl4ai-style result without actually crawling anything."""
    return SimpleNamespace(
        url=url,
        markdown=SimpleNamespace(
            raw_markdown=raw_markdown,
            fit_markdown=fit_markdown if fit_markdown is not None else raw_markdown,
        ),
    )


def test_thin_content_flagged_for_coming_soon_page():
    result = _fake_result("Coming soon! We are launching shortly.")
    assessment = assess_content_quality(result)
    assert assessment["is_thin"] is True
    assert "too_few_words" in assessment["reasons"]


def test_real_content_passes():
    # Varied, realistic prose — not one sentence repeated, so unique-word ratio stays high.
    paragraphs = [
        "This guide walks you through setting up a modern web application from scratch.",
        "We start by choosing the right framework based on your team's experience "
        "and project needs.",
        "Next, configure your database connection and run the initial migrations "
        "to create your schema.",
        "Once the backend is running, connect the frontend and verify the API "
        "responses work as expected.",
        "Finally, we cover deployment strategies including containerization and "
        "continuous integration pipelines.",
        "Testing is a critical part of this process, so we also review unit and "
        "integration test patterns.",
        "Security considerations like input validation and authentication are "
        "discussed in the later sections.",
        "Performance tuning tips help you scale the application as your user base grows over time.",
        "We also touch on monitoring and logging so you can catch issues before your users do.",
        "By the end of this guide, you'll have a solid foundation for building "
        "production-ready software.",
    ]
    result = _fake_result(" ".join(paragraphs))
    assessment = assess_content_quality(result)
    assert assessment["is_thin"] is False


def test_repetitive_filler_flagged_even_with_enough_words():
    result = _fake_result("buy now buy now buy now " * 20)  # 80 words, but only 3 unique
    assessment = assess_content_quality(result)
    assert assessment["is_thin"] is True
    assert "repetitive_content" in assessment["reasons"]


def test_boilerplate_heavy_page_flagged():
    # long raw markdown, but crawl4ai's BM25 filter barely found any "real" content in it
    result = _fake_result(
        raw_markdown=" ".join(["word"] * 300), fit_markdown=" ".join(["word"] * 10)
    )
    assessment = assess_content_quality(result)
    assert assessment["is_thin"] is True
    assert "mostly_boilerplate" in assessment["reasons"]


def test_thin_content_document_has_useful_metadata():
    result = _fake_result("too short")
    assessment = assess_content_quality(result)
    doc = build_thin_content_document(result, assessment)
    assert doc.metadata["status"] == "thin_content"
    assert doc.metadata["url"] == "https://example.com"
    assert doc.page_content == ""
