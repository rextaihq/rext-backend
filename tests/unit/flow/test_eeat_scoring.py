from src.flow.engines.content.utils.eeat import deterministic_eeat_score


def test_deterministic_eeat_uses_content_level_evidence() -> None:
    html = """
    <article>
      <h1>AI workflow testing guide</h1>
      <p>By Jane Smith</p>
      <p>We tested three workflows in 2026 and compared failure rates.</p>
      <p>See the <a href="https://example.com/report">benchmark report</a>.</p>
    </article>
    """

    result = deterministic_eeat_score(
        html,
        {
            "title": "AI workflow testing guide",
            "content_type": "blog",
            "facts": [
                {
                    "text": "Three workflows were tested.",
                    "source_url": "https://example.com/report",
                }
            ],
        },
    )

    assert result["scoring_scope"] == "content_level_only"
    assert result["signal_summary"]["source_count"] == 1
    assert result["author_identity"] > 0
    assert 0 <= result["score"] <= 100


def test_deterministic_eeat_caps_evidence_without_sources() -> None:
    html = """
    <article>
      <h1>Best accounting software</h1>
      <p>This is the best tool for every business and saves 99% of time.</p>
    </article>
    """

    result = deterministic_eeat_score(
        html,
        {
            "title": "Best accounting software",
            "content_type": "in-depth-review",
            "facts": [{"text": "The software saves 99% of time."}],
        },
    )

    assert result["signal_summary"]["source_count"] == 0
    assert result["evidence_strength"] < 55
    assert result["content_accuracy"] < 75
