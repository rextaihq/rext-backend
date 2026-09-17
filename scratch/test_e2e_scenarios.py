import json
import pytest
from fastapi.testclient import TestClient
from src.api.server import app

client = TestClient(app)

scenarios = [
    {
        "name": "Scenario 1: DevTools & Technical Documentation (FastAPI & Pydantic)",
        "title_tag": {
            "keyword": "Pydantic validation",
            "topic": "FastAPI Pydantic guide",
            "brand": "FastAPI Master",
            "tone": "Technical"
        },
        "grammar": {
            "text": "This are a code snippet showing how Pydantic str and len work with FastAPI."
        },
        "outline": {
            "topic": "Building Async APIs with FastAPI and Pydantic",
            "target_word_count": 1500,
            "tone": "Technical"
        },
        "headline": {
            "headline": "10 Advanced Pydantic Validation Tricks for FastAPI Developers"
        },
        "hreflang": {
            "language_region_urls": [
                {"url": "https://example.com/en/fastapi", "language": "en", "region": "us"}
            ],
            "default_url": "https://example.com/en/fastapi",
            "include_x_default": True,
            "output_format": "html"
        },
        "keyword_density": {
            "text": "Pydantic provides fast data validation in Python. Using Pydantic models ensures data integrity.",
            "target_keyword": "Pydantic"
        },
        "paragraph": {
            "text": "Pydantic is getting better and helping developers validate python code faster.",
            "goal": "improve clarity",
            "tone": "Professional"
        },
        "serp": {
            "title": "FastAPI Pydantic Masterclass 2026 - Comprehensive Guide",
            "description": "Master FastAPI and Pydantic data validation with asynchronous Python web services in 2026.",
            "url": "https://example.com/fastapi-pydantic"
        },
        "sitemap": {
            "urls": [
                "https://example.com/docs/fastapi",
                "https://example.com/docs/pydantic"
            ]
        }
    },
    {
        "name": "Scenario 2: E-Commerce Footwear Brand (EcoStride)",
        "title_tag": {
            "keyword": "sustainable running shoes",
            "topic": "Best Eco Sneakers",
            "brand": "EcoStride Footwear",
            "tone": "Friendly"
        },
        "grammar": {
            "text": "EcoStride sneakers is made from 100% recycled materials and feel amazing."
        },
        "outline": {
            "topic": "Ultimate Guide to Choosing Sustainable Running Shoes",
            "target_word_count": 2000,
            "tone": "Engaging"
        },
        "headline": {
            "headline": "7 Surprising Benefits of Switching to Sustainable Running Shoes"
        },
        "hreflang": {
            "language_region_urls": [
                {"url": "https://ecostride.com/us/shoes", "language": "en", "region": "us"},
                {"url": "https://ecostride.com/es/zapatos", "language": "es", "region": "es"}
            ],
            "default_url": "https://ecostride.com/us/shoes",
            "include_x_default": True,
            "output_format": "html"
        },
        "keyword_density": {
            "text": "Our sustainable running shoes feature eco friendly materials. EcoStride footwear delivers top performance.",
            "target_keyword": "sustainable running shoes"
        },
        "paragraph": {
            "text": "Our eco shoes are really good for running and they do not harm nature at all.",
            "goal": "make professional",
            "tone": "Inspiring"
        },
        "serp": {
            "title": "EcoStride Footwear - Top Rated Sustainable Running Shoes",
            "description": "Shop EcoStride sustainable running shoes crafted from recycled materials for ultimate comfort.",
            "url": "https://ecostride.com/sustainable-shoes"
        },
        "sitemap": {
            "urls": [
                "https://ecostride.com/collections/shoes",
                "https://ecostride.com/about-us"
            ]
        }
    },
    {
        "name": "Scenario 3: B2B Enterprise SaaS (FinPulse Analytics)",
        "title_tag": {
            "keyword": "enterprise financial reporting",
            "topic": "Automated Auditing",
            "brand": "FinPulse Analytics",
            "tone": "Authoritative"
        },
        "grammar": {
            "text": "FinPulse Analytics help finance teams generate error-free quarterly reports automatically."
        },
        "outline": {
            "topic": "Streamlining Enterprise Financial Reporting and Compliance",
            "target_word_count": 2500,
            "tone": "Authoritative"
        },
        "headline": {
            "headline": "How Automation is Revolutionizing Enterprise Financial Reporting"
        },
        "hreflang": {
            "language_region_urls": [
                {"url": "https://finpulse.com/de/reports", "language": "de", "region": "de"}
            ],
            "default_url": "https://finpulse.com/en/reports",
            "include_x_default": True,
            "output_format": "html"
        },
        "keyword_density": {
            "text": "Enterprise financial reporting requires accurate auditing data. FinPulse simplifies reporting.",
            "target_keyword": "enterprise financial reporting"
        },
        "paragraph": {
            "text": "Manual financial reporting takes too much time and often has lots of mistakes.",
            "goal": "shorten",
            "tone": "Executive"
        },
        "serp": {
            "title": "Automated Financial Reporting Solutions | FinPulse Enterprise",
            "description": "Streamline corporate compliance and auditing workflows with FinPulse enterprise financial reporting software.",
            "url": "https://finpulse.com/enterprise-reporting"
        },
        "sitemap": {
            "urls": [
                "https://finpulse.com/enterprise",
                "https://finpulse.com/pricing"
            ]
        }
    }
]


def run_e2e_tests():
    print("==========================================================================")
    print("STARTING E2E SCENARIO TESTING FOR ALL NEW & UPDATED SEO Writing TOOLS")
    print("==========================================================================\n")

    report_results = []

    for idx, sc in enumerate(scenarios, 1):
        print(f"--- RUNNING SCENARIO {idx}: {sc['name']} ---")

        # 1. Title Tag Generator Test
        res = client.post("/api/v1/tools/title-tags", json=sc["title_tag"])
        assert res.status_code == 200, f"Title tags failed: {res.text}"
        data = res.json()["data"]
        titles = data["titles"]
        assert len(titles) == 5, f"Expected 5 titles, got {len(titles)}"
        for t in titles:
            t_len = len(t.strip())
            assert 50 <= t_len <= 60, f"Title length violation: '{t}' ({t_len} chars)"
        print(f"  [PASS] Title Tag Generator: 5 titles generated, all strictly 50-60 chars.")

        # 2. Grammar Checker Test
        res = client.post("/api/v1/tools/grammar-checker", json=sc["grammar"])
        assert res.status_code == 200, f"Grammar checker failed: {res.text}"
        g_data = res.json()["data"]
        # Check that protected tech terms were NOT flagged (0 false positives on Pydantic, str, len, etc.)
        for issue in g_data["issues"]:
            orig = issue["original_phrase"].lower()
            assert orig not in ["pydantic", "str", "len", "contentidea"], f"False positive flag on tech term: {orig}"
        print(f"  [PASS] Grammar Checker: Corrected text: '{g_data['corrected_text']}'. Zero false positives on tech terms.")

        # 3. Content Outline Generator Test
        res = client.post("/api/v1/tools/outline-generator", json=sc["outline"])
        assert res.status_code == 200, f"Outline generator failed: {res.text}"
        o_data = res.json()["data"]
        assert "title" in o_data and len(o_data["sections"]) >= 4
        print(f"  [PASS] Content Outline Generator: Sections count = {o_data['sections_count']}.")

        # 4. Headline Analyzer Test
        res = client.post("/api/v1/tools/headline-analyzer", json=sc["headline"])
        assert res.status_code == 200, f"Headline analyzer failed: {res.text}"
        h_data = res.json()["data"]
        assert 0 <= h_data["score"] <= 100
        print(f"  [PASS] Headline Analyzer: Score = {h_data['score']}/100, Sentiment = {h_data['sentiment']}.")

        # 5. Hreflang Tag Generator Test
        res = client.post("/api/v1/tools/hreflang-generator", json=sc["hreflang"])
        assert res.status_code == 200, f"Hreflang generator failed: {res.text}"
        hr_data = res.json()["data"]
        assert len(hr_data["hreflang_tags"]) >= 1
        print(f"  [PASS] Hreflang Tag Generator: Generated {len(hr_data['hreflang_tags'])} tags.")

        # 6. Keyword Density Checker Test
        res = client.post("/api/v1/tools/keyword-density", json=sc["keyword_density"])
        assert res.status_code == 200, f"Keyword density failed: {res.text}"
        kd_data = res.json()["data"]
        assert kd_data["total_words"] > 0
        print(f"  [PASS] Keyword Density Checker: Total words = {kd_data['total_words']}.")

        # 7. Paragraph Rewriter Test
        res = client.post("/api/v1/tools/paragraph-rewriter", json=sc["paragraph"])
        assert res.status_code == 200, f"Paragraph rewriter failed: {res.text}"
        pr_data = res.json()["data"]
        assert "rewritten_text" in pr_data
        print(f"  [PASS] Paragraph Rewriter: Goal = '{pr_data['goal']}'.")

        # 8. SERP Preview Tool Test
        res = client.post("/api/v1/tools/serp-preview", json=sc["serp"])
        assert res.status_code == 200, f"SERP preview failed: {res.text}"
        sp_data = res.json()["data"]
        assert sp_data["title_length"] > 0
        print(f"  [PASS] SERP Preview Tool: Title len = {sp_data['title_length']}, Pixel width = {sp_data['desktop_pixel_width_approx']}px.")

        # 9. Sitemap Generator Test
        res = client.post("/api/v1/tools/sitemap-generator", json=sc["sitemap"])
        assert res.status_code == 200, f"Sitemap generator failed: {res.text}"
        sm_data = res.json()["data"]
        assert "<?xml" in sm_data["sitemap_xml"]
        print(f"  [PASS] Sitemap Generator: Valid XML with {sm_data['total_urls']} URLs.\n")

        report_results.append(sc["name"])

    print("==========================================================================")
    print(f"ALL {len(report_results)} SCENARIOS PASSED 100% END-TO-END!")
    print("==========================================================================")

if __name__ == "__main__":
    run_e2e_tests()
