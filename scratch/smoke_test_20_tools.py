import sys

from fastapi.testclient import TestClient

from src.api.server import app

client = TestClient(app)

tools_smoke_payloads = [
    # 1. Word Counter Endpoint
    (
        "POST",
        "/api/v1/tools/count_metrics",
        {"text": "FastAPI and Pydantic make a powerful team for Python microservices."},
        lambda d: d.get("words") == 10 and d.get("characters") > 0,
    ),
    # 2. Meta Description Generator Endpoint
    (
        "POST",
        "/api/v1/tools/meta-description/generate",
        {"page_title": "FastAPI Masterclass 2026", "target_keywords": ["FastAPI", "Python", "API"]},
        lambda d: "meta_description" in d and "validation" in d,
    ),
    # 3. Title Tag Generator Endpoint
    (
        "POST",
        "/api/v1/tools/title-tags",
        {
            "keyword": "FastAPI guide",
            "topic": "Asynchronous Python APIs",
            "brand": "FastAPI Master",
            "tone": "Technical",
        },
        lambda d: len(d.get("titles", [])) == 5 and all(50 <= len(t) <= 60 for t in d["titles"]),
    ),
    # 4. Schema Generator Endpoint
    (
        "POST",
        "/api/v1/tools/schema-generator",
        {
            "schema_type": "Article",
            "name": "FastAPI Guide",
            "description": "Complete FastAPI tutorial",
            "url": "https://example.com/guide",
        },
        lambda d: d.get("@type") == "Article" and "@context" in d,
    ),
    # 5. Readability Checker Endpoint
    (
        "POST",
        "/api/v1/tools/readability-checker",
        {
            "content": "FastAPI is a modern, fast web framework for building APIs with Python based on standard Python type hints."
        },
        lambda d: "readability_score" in d and "word_count" in d,
    ),
    # 6. Canonical Tag Generator Endpoint
    (
        "POST",
        "/api/v1/tools/canonical-tag-generator",
        {"url": "https://example.com/canonical-page?ref=123"},
        lambda d: "canonical_tag" in d and "example.com" in d["canonical_tag"],
    ),
    # 7. Question Generator Endpoint
    (
        "POST",
        "/api/v1/tools/question-generator",
        {"text": "Pydantic is a data validation library for Python."},
        lambda d: "questions" in d and len(d["questions"]) >= 1,
    ),
    # 8. Link Checker Endpoint
    (
        "POST",
        "/api/v1/tools/link-checker",
        {"url": "https://httpbin.org/status/200"},
        lambda d: "working" in d,
    ),
    # 9. Content Idea Generator Endpoint
    (
        "POST",
        "/api/v1/tools/content-idea-generator",
        {
            "topic": "Asynchronous Microservices in Python",
            "content_type": "blog_post",
            "ideas_count": 3,
        },
        lambda d: "ideas" in d and len(d["ideas"]) >= 1,
    ),
    # 10. Robots.txt Generator Endpoint
    (
        "POST",
        "/api/v1/tools/robots-txt/generate",
        {
            "user_agent": "*",
            "allow": ["/public"],
            "disallow": ["/admin"],
            "sitemap_url": "https://example.com/sitemap.xml",
        },
        lambda d: "robots_txt" in d and "User-agent: *" in d["robots_txt"],
    ),
    # 11. Grammar Checker Endpoint
    (
        "POST",
        "/api/v1/tools/grammar-checker",
        {"text": "Pydantic str and len is awesome and helps developers validate code faster."},
        lambda d: "corrected_text" in d and "issues" in d,
    ),
    # 12. Hook Generator Endpoint
    (
        "POST",
        "/api/v1/tools/hook-generator",
        {
            "topic_description": "Async Web Development with FastAPI",
            "goal_of_content": "Engage Python Developers",
            "number_of_variations": 3,
        },
        lambda d: "hooks" in d and len(d["hooks"]) >= 1,
    ),
    # 13. Blog Topic Generator Endpoint
    (
        "POST",
        "/api/v1/tools/seo-blog-titles",
        {"keyword": "FastAPI Async", "num_titles": 3},
        lambda d: "blog_titles" in d and len(d["blog_titles"]) >= 1,
    ),
    # 14. Content Outline Generator Endpoint
    (
        "POST",
        "/api/v1/tools/outline-generator",
        {
            "topic": "Building Async Microservices with FastAPI",
            "target_word_count": 1500,
            "tone": "Technical",
        },
        lambda d: "title" in d and len(d.get("sections", [])) >= 3,
    ),
    # 15. Headline Analyzer Endpoint
    (
        "POST",
        "/api/v1/tools/headline-analyzer",
        {"headline": "10 Proven Ways to Master Asynchronous Programming in FastAPI"},
        lambda d: "score" in d and "sentiment" in d,
    ),
    # 16. Hreflang Tag Generator Endpoint
    (
        "POST",
        "/api/v1/tools/hreflang-generator",
        {
            "language_region_urls": [
                {"url": "https://example.com/en/fastapi", "language": "en", "region": "us"},
                {"url": "https://example.com/es/fastapi", "language": "es", "region": "es"},
            ],
            "default_url": "https://example.com/en/fastapi",
            "include_x_default": True,
            "output_format": "html",
        },
        lambda d: "hreflang_tags" in d and len(d["hreflang_tags"]) >= 2,
    ),
    # 17. Keyword Density Checker Endpoint
    (
        "POST",
        "/api/v1/tools/keyword-density",
        {
            "text": "FastAPI is fast. FastAPI simplifies web API development in Python.",
            "target_keyword": "FastAPI",
        },
        lambda d: (
            d.get("total_words") > 0 and ("target_keyword_analysis" in d or "top_single_words" in d)
        ),
    ),
    # 18. Paragraph Rewriter Endpoint
    (
        "POST",
        "/api/v1/tools/paragraph-rewriter",
        {
            "text": "Pydantic helps programmers write python code fast and validate inputs efficiently.",
            "goal": "improve clarity",
            "tone": "Professional",
        },
        lambda d: "rewritten_text" in d and len(d["rewritten_text"]) > 0,
    ),
    # 19. SERP Preview Tool Endpoint
    (
        "POST",
        "/api/v1/tools/serp-preview",
        {
            "title": "FastAPI & Pydantic Tutorial 2026 - Comprehensive Guide",
            "description": "Learn how to build high performance asynchronous web APIs using FastAPI and Pydantic in Python.",
            "url": "https://example.com/fastapi-tutorial",
        },
        lambda d: d.get("title_length") > 0 and "desktop_pixel_width_approx" in d,
    ),
    # 20. Sitemap Generator Endpoint
    (
        "POST",
        "/api/v1/tools/sitemap-generator",
        {
            "urls": [
                {"url": "https://example.com/page1", "changefreq": "daily", "priority": 0.8},
                {"url": "https://example.com/page2", "changefreq": "weekly", "priority": 0.5},
            ]
        },
        lambda d: "sitemap_xml" in d and "<?xml" in d["sitemap_xml"],
    ),
]


def run_smoke_tests():
    print("==========================================================================")
    print("STARTING SMOKE TEST FOR ALL 20 TOOL ENDPOINTS (EXACT ROUTE MATCHING)")
    print("==========================================================================\n")

    passed_count = 0
    failed_count = 0

    for idx, (method, endpoint, payload, check_fn) in enumerate(tools_smoke_payloads, 1):
        print(f"[{idx:02d}/20] Testing {method} {endpoint} ... ", end="")
        try:
            res = client.request(method, endpoint, json=payload)
            if res.status_code != 200:
                print(f"FAILED (HTTP {res.status_code}): {res.text}")
                failed_count += 1
                continue

            body = res.json()
            if not body.get("success"):
                print(f"FAILED (Envelope success=False): {body}")
                failed_count += 1
                continue

            data = body.get("data", {})
            if check_fn(data):
                print("PASSED")
                passed_count += 1
            else:
                print(f"FAILED (Validation Check Failed): {data}")
                failed_count += 1
        except Exception as e:
            print(f"ERROR: {e}")
            failed_count += 1

    print("\n==========================================================================")
    print(f"SMOKE TEST SUMMARY: {passed_count}/20 PASSED ({failed_count} FAILED)")
    print("==========================================================================")

    if failed_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    run_smoke_tests()
