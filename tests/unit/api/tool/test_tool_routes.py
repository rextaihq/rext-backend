import pytest
from fastapi.testclient import TestClient

from src.api.server import app

client = TestClient(app)


def test_count_metrics_route():
    response = client.post(
        "/api/v1/tools/count_metrics", json={"text": "Testing word count and metrics."}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "words" in data["data"]
    assert "characters" in data["data"]


def test_question_generator_route():
    response = client.post(
        "/api/v1/tools/question-generator", json={"text": "AI technology is rapidly advancing."}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert isinstance(data["data"]["questions"], list)


def test_content_idea_generator_route():
    response = client.post(
        "/api/v1/tools/content-idea-generator",
        json={"topic": "Python", "content_type": "Blog", "ideas_count": 2},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert isinstance(data["data"]["ideas"], list)


def test_grammar_checker_route():
    response = client.post("/api/v1/tools/grammar-checker", json={"text": "This are test."})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "corrected_text" in data["data"]


def test_hook_generator_route():
    response = client.post(
        "/api/v1/tools/hook-generator",
        json={
            "topic_description": "SEO strategy",
            "goal_of_content": "Rank #1",
            "number_of_variations": 2,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert isinstance(data["data"]["hooks"], list)


def test_seo_blog_titles_route():
    response = client.post(
        "/api/v1/tools/seo-blog-titles",
        json={"keyword": "fastapi", "number_of_topics": 2, "min_words": 3, "max_words": 10},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert isinstance(data["data"]["blog_titles"], list)


def test_broken_link_checker_route():
    response = client.post(
        "/api/v1/tools/link-checker", json={"url": "https://httpbin.org/status/200"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["working"] is True
