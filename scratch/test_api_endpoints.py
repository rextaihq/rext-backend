import sys
import os

sys.path.insert(0, os.path.abspath("."))

from fastapi.testclient import TestClient
from src.api.server import app

client = TestClient(app)

def test_endpoints():
    print("--- Testing API Endpoint: POST /api/v1/tools/count_metrics ---")
    res = client.post("/api/v1/tools/count_metrics", json={"text": "Hello world. This is a test sentence."})
    print("Status:", res.status_code)
    print("Response:", res.json())

    print("\n--- Testing API Endpoint: POST /api/v1/tools/question-generator ---")
    res = client.post("/api/v1/tools/question-generator", json={"text": "Artificial intelligence is revolutionizing content marketing."})
    print("Status:", res.status_code)
    print("Response:", res.json())

    print("\n--- Testing API Endpoint: POST /api/v1/tools/content-idea-generator ---")
    res = client.post("/api/v1/tools/content-idea-generator", json={"topic": "SaaS Growth", "content_type": "Blog Post", "ideas_count": 3})
    print("Status:", res.status_code)
    print("Response:", res.json())

    print("\n--- Testing API Endpoint: POST /api/v1/tools/grammar-checker ---")
    res = client.post("/api/v1/tools/grammar-checker", json={"text": "This are a test error."})
    print("Status:", res.status_code)
    print("Response:", res.json())

    print("\n--- Testing API Endpoint: POST /api/v1/tools/hook-generator ---")
    res = client.post("/api/v1/tools/hook-generator", json={"topic_description": "Time management", "goal_of_content": "Increase focus", "number_of_variations": 3})
    print("Status:", res.status_code)
    print("Response:", res.json())

    print("\n--- Testing API Endpoint: POST /api/v1/tools/seo-blog-titles ---")
    res = client.post("/api/v1/tools/seo-blog-titles", json={"keyword": "react native", "number_of_topics": 3, "min_words": 4, "max_words": 10})
    print("Status:", res.status_code)
    print("Response:", res.json())

    print("\n--- Testing API Endpoint: POST /api/v1/tools/link-checker ---")
    res = client.post("/api/v1/tools/link-checker", json={"url": "https://httpbin.org/status/200"})
    print("Status:", res.status_code)
    print("Response:", res.json())

if __name__ == "__main__":
    test_endpoints()
