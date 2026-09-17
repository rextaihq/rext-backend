import asyncio
import sys
import os

# Add src to python path
sys.path.insert(0, os.path.abspath("."))

from src.api.tool.tools import (
    count_text_metrics,
    generate_questions,
    generate_content_ideas,
    grammar_checker,
    generate_hooks,
    generate_seo_blog_titles,
    broken_link_checker,
)
from src.api.tool.schema.schema import (
    IdeaGeneratorRequest,
    HookGeneratorRequest,
    SEOBlogTitleRequest,
)

async def test_all():
    print("--- 1. Testing Get Metrics ---")
    try:
        res = count_text_metrics("This is a test. It has two sentences.")
        print("Metrics success:", res)
    except Exception as e:
        print("Metrics error:", e)

    print("\n--- 2. Testing Generate Questions ---")
    try:
        res = await generate_questions("Artificial intelligence is transforming content creation for modern marketers.")
        print("Questions success:", res)
    except Exception as e:
        print("Questions error:", e)

    print("\n--- 3. Testing Content Idea Generator ---")
    try:
        req = IdeaGeneratorRequest(topic="AI Marketing", content_type="Blog Post", ideas_count=3)
        res = await generate_content_ideas(req)
        print("Content Ideas success:", res)
    except Exception as e:
        print("Content Ideas error:", e)

    print("\n--- 4. Testing Grammar Checker ---")
    try:
        res = grammar_checker("This are a test sentence with bad grammar.")
        print("Grammar Checker success:", res)
    except Exception as e:
        print("Grammar Checker error:", e)

    print("\n--- 5. Testing Hook Generator ---")
    try:
        req = HookGeneratorRequest(topic_description="AI tools for writing", goal_of_content="Increase productivity", number_of_variations=3)
        res = await generate_hooks(req)
        print("Hook Generator success:", res)
    except Exception as e:
        print("Hook Generator error:", e)

    print("\n--- 6. Testing Blog Topic Generator ---")
    try:
        req = SEOBlogTitleRequest(keyword="python programming", number_of_topics=3, min_words=4, max_words=10)
        res = await generate_seo_blog_titles(req)
        print("Blog Topic Generator success:", res)
    except Exception as e:
        print("Blog Topic Generator error:", e)

    print("\n--- 7. Testing Broken Link Checker ---")
    try:
        res = await broken_link_checker("https://httpbin.org/status/200")
        print("Broken Link Checker (working link) success:", res)
        res_broken = await broken_link_checker("https://httpbin.org/status/404")
        print("Broken Link Checker (broken link) success:", res_broken)
    except Exception as e:
        print("Broken Link Checker error:", e)

if __name__ == "__main__":
    asyncio.run(test_all())
