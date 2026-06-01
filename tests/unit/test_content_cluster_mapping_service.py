from src.services.content_cluster_mapping_service import (
    build_cluster_heading_map,
    format_cluster_heading_map_for_prompt,
    is_pillar_content_type,
)


def test_build_cluster_heading_map_maps_clusters_to_h1_h2_h3():
    clusters = [
        {
            "cluster_name": "seo content strategy",
            "topic_theme": "strategy",
            "main_intent": "informational",
            "total_score": 180,
            "keywords": [
                {"keyword": "seo content strategy", "score": 95},
                {"keyword": "content clusters", "score": 80},
                {"keyword": "keyword mapping", "score": 70},
            ],
            "rationale": "All keywords describe planning content around search intent.",
        },
        {
            "cluster_name": "content brief template",
            "topic_theme": "execution",
            "main_intent": "informational",
            "total_score": 120,
            "keywords": [
                {"keyword": "content brief template", "score": 88},
                {"keyword": "seo brief example", "score": 72},
            ],
        },
    ]

    result = build_cluster_heading_map(
        keyword_clusters=clusters,
        topic="SEO Content Strategy Guide",
        content_type="blog",
        questions=["How do content clusters improve SEO?"],
    )

    assert result["enabled"] is True
    assert result["h1"]["suggested_heading"] == "SEO Content Strategy Guide"
    assert result["h1"]["primary_keyword"] == "seo content strategy"
    assert len(result["h2_sections"]) == 2
    assert result["h2_sections"][0]["heading_level"] == "H2"
    assert result["h2_sections"][0]["suggested_heading"] == "seo content strategy"
    assert result["h2_sections"][0]["h3_topics"] == ["content clusters", "keyword mapping"]
    assert result["h2_sections"][0]["questions_to_answer"] == [
        "How do content clusters improve SEO?"
    ]


def test_build_cluster_heading_map_skips_pillar_content():
    result = build_cluster_heading_map(
        keyword_clusters=[
            {
                "cluster_name": "topic authority",
                "keywords": [{"keyword": "topic authority", "score": 90}],
            }
        ],
        topic="Topic Authority",
        content_type="pillar-page",
    )

    assert result["enabled"] is False
    assert result["skipped"] is True
    assert result["h2_sections"] == []


def test_is_pillar_content_type_handles_known_aliases():
    assert is_pillar_content_type("pillar-content")
    assert is_pillar_content_type("pillar page")
    assert is_pillar_content_type("pillarpage")
    assert not is_pillar_content_type("blog")


def test_format_cluster_heading_map_for_prompt_includes_heading_levels():
    heading_map = build_cluster_heading_map(
        keyword_clusters=[
            {
                "cluster_name": "best crm software",
                "main_intent": "commercial",
                "keywords": [
                    {"keyword": "best crm software", "score": 92},
                    {"keyword": "crm comparison", "score": 76},
                ],
            }
        ],
        topic="Best CRM Software",
        content_type="comparison",
    )

    prompt_text = format_cluster_heading_map_for_prompt(heading_map)

    assert "H1: Best CRM Software" in prompt_text
    assert "H2: best crm software" in prompt_text
    assert "H3 topics: crm comparison" in prompt_text
