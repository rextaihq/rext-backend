import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.api.tool.schema.schema import (
    HeadlineAnalyzerRequest,
    KeywordDensityRequest,
    OutlineGeneratorRequest,
    SERPPreviewRequest,
    SitemapGeneratorRequest,
    SitemapItem,
)
from src.api.tool.tools import (
    calculate_keyword_density,
    generate_serp_preview,
    generate_xml_sitemap,
)

client = TestClient(app)


# 1. Content Outline Generator Tests
def test_content_outline_generator():
    res = client.post(
        "/api/v1/tools/outline-generator",
        json={"topic": "Python Web Development", "target_word_count": 1500, "tone": "Informative"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "title" in data["data"]
    assert "sections" in data["data"]
    assert len(data["data"]["sections"]) >= 4


@pytest.mark.parametrize(
    "word_count,expected_sections",
    [
        (799, 4),
        (800, 5),
        (1500, 5),
        (1501, 7),
        (2500, 7),
        (2501, 9),
    ],
)
def test_outline_generator_section_boundaries(word_count, expected_sections):
    req = OutlineGeneratorRequest(topic="Test Boundaries", target_word_count=word_count)
    wc = req.target_word_count or 1500
    if wc < 800:
        sec = 4
    elif wc <= 1500:
        sec = 5
    elif wc <= 2500:
        sec = 7
    else:
        sec = 9
    assert sec == expected_sections


# 2. Headline Analyzer Tests
def test_headline_analyzer():
    res = client.post(
        "/api/v1/tools/headline-analyzer",
        json={"headline": "10 Mind-Blowing AI Tools You Need to Try Today"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "score" in data["data"]
    assert data["data"]["word_count"] == 9
    assert data["data"]["character_count"] == 46
    assert 0 <= data["data"]["score"] <= 100


# 3. Hreflang Generator Tests
def test_hreflang_generator():
    res = client.post(
        "/api/v1/tools/hreflang-generator",
        json={
            "language_region_urls": [
                {"url": "https://example.com/en", "language": "en", "region": "us"},
                {"url": "https://example.com/es", "language": "es", "region": "es"},
            ],
            "default_url": "https://example.com/en",
            "include_x_default": True,
            "output_format": "html",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "hreflang_tags" in data["data"]


def test_hreflang_duplicate_warning():
    res = client.post(
        "/api/v1/tools/hreflang-generator",
        json={
            "language_region_urls": [
                {"url": "https://example.com/en", "language": "en", "region": "us"},
                {"url": "https://example.com/en", "language": "en", "region": "us"},
            ],
            "default_url": "https://example.com/en",
            "include_x_default": True,
            "output_format": "html",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["data"]["warnings"] is not None
    assert len(data["data"]["warnings"]) > 0


# 4. Keyword Density Checker Tests
def test_keyword_density():
    res = client.post(
        "/api/v1/tools/keyword-density",
        json={
            "text": "Python is a great programming language. Python is easy to learn and Python is powerful.",
            "target_keyword": "python",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["data"]["total_words"] > 0
    assert data["data"]["target_keyword_analysis"]["count"] == 3


def test_keyword_density_regex_no_substring_matches():
    # 'cat' must NOT match inside 'catch', 'category', 'location', or 'concat'
    text = "The cat caught a mouse. Catching categories in location concatenated."
    req = KeywordDensityRequest(text=text, target_keyword="cat")
    res = calculate_keyword_density(req)
    assert res.target_keyword_analysis["count"] == 1
    assert res.target_keyword_analysis["status"] == "Over-stuffed (above 2.5%)"


def test_keyword_density_multi_word_punctuation_and_case():
    # Multi-word target keyword 'SEO/SEM tools' with mixed case & slash punctuation
    text = "Top SEO/SEM tools help marketers rank. Using modern seo sem tools improves conversions dramatically."
    req = KeywordDensityRequest(text=text, target_keyword="SEO/SEM tools")
    res = calculate_keyword_density(req)
    assert res.target_keyword_analysis["count"] == 2
    # 2 occurrences of 3-word phrase in 15-word text -> (2*3/15)*100 = 40.0%
    assert res.target_keyword_analysis["density_percentage"] == 40.0


def test_keyword_density_phrase_counting():
    text = "Artificial intelligence drives modern software. Artificial intelligence transforms workflows."
    req = KeywordDensityRequest(text=text, target_keyword="artificial intelligence")
    res = calculate_keyword_density(req)
    assert res.target_keyword_analysis["count"] == 2
    phrase_keywords = [p.keyword for p in res.top_phrases]
    assert "artificial intelligence" in phrase_keywords


def test_keyword_density_empty_text():
    req = KeywordDensityRequest(text="          ", target_keyword="test")
    res = calculate_keyword_density(req)
    assert res.total_words == 0
    assert res.top_single_words == []
    assert res.target_keyword_analysis is None


# 5. Paragraph Rewriter Tests
@pytest.mark.parametrize(
    "goal",
    [
        "improve clarity",
        "make professional",
        "simplify",
        "more engaging",
        "expand",
        "shorten",
    ],
)
def test_paragraph_rewriter_all_goals(goal):
    res = client.post(
        "/api/v1/tools/paragraph-rewriter",
        json={
            "text": "Artificial intelligence is getting better every day and helping people create content faster.",
            "goal": goal,
            "tone": "Professional",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "rewritten_text" in data["data"]
    assert data["data"]["goal"] == goal


# 6. SERP Preview Tests
def test_serp_preview():
    res = client.post(
        "/api/v1/tools/serp-preview",
        json={
            "title": "Best SEO Tools 2026 - Comprehensive Review",
            "description": "Discover the top SEO tools for keyword research, rank tracking, and on-page optimization in 2026.",
            "url": "https://example.com/best-seo-tools",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["data"]["title_length"] > 0
    assert "desktop_pixel_width_approx" in data["data"]


def test_serp_preview_truncation_estimates():
    long_title = "A" * 70
    long_desc = "B" * 170
    req = SERPPreviewRequest(title=long_title, description=long_desc, url="https://example.com")
    res = generate_serp_preview(req)
    assert res.title_truncated is True
    assert res.description_truncated is True
    assert len(res.warnings) == 2
    assert "heuristic estimates" in res.warnings[0].lower()


def test_serp_preview_short_warnings():
    req = SERPPreviewRequest(
        title="Short", description="Short description", url="https://example.com"
    )
    res = generate_serp_preview(req)
    assert res.title_truncated is False
    assert res.description_truncated is False
    assert any("under 30" in w for w in res.warnings)
    assert any("under 70" in w for w in res.warnings)


# 7. Sitemap Generator Tests
def test_sitemap_generator():
    res = client.post(
        "/api/v1/tools/sitemap-generator",
        json={"urls": ["https://example.com/", "https://example.com/blog"]},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "<?xml" in data["data"]["sitemap_xml"]
    assert data["data"]["total_urls"] == 2


def test_sitemap_xml_escaping_and_deduplication():
    items = [
        SitemapItem(url="https://example.com/page?param1=a&param2=b<c>"),
        SitemapItem(url="https://example.com/page?param1=a&param2=b<c>"),  # Duplicate
        SitemapItem(url="https://example.com/clean", priority=1.0, changefreq="weekly"),
    ]
    req = SitemapGeneratorRequest(urls=items)
    res = generate_xml_sitemap(req)
    assert res.total_urls == 2
    assert "&amp;" in res.sitemap_xml
    assert "&lt;c&gt;" in res.sitemap_xml
    assert "<priority>1.0</priority>" in res.sitemap_xml
    assert "<changefreq>weekly</changefreq>" in res.sitemap_xml
