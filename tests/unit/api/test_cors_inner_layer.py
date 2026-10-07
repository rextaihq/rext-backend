"""Plain responses name an allowed origin only (G83, rext-control#648).

The LangGraph server wraps this app as `app.user_middleware = custom_middleware + global_middleware`
(langgraph_api/server.py): the app's CORSMiddleware, built from ALLOWED_ORIGINS, is outermost and answers
every preflight, and LangGraph's own CORSMiddleware sits inside it. Without `http.cors` in langgraph.json
that inner one allows every origin with credentials, so a plain response to any Origin came back naming
it in Access-Control-Allow-Origin. langgraph.json now gives it no origins: it adds nothing, and the app's
layer decides alone. The stack below is built the same way, outer first.
"""

import json
import re
from pathlib import Path

from fastapi.middleware.cors import CORSMiddleware
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from src.api.server import app

ROOT = Path(__file__).resolve().parents[3]
FOREIGN = "https://evil.example"
APP_CORS = app.user_middleware[0]
ALLOWED = APP_CORS.kwargs["allow_origins"][0]
# What LangGraph adds when langgraph.json has no `http.cors` (langgraph_api/server.py).
LANGGRAPH_DEFAULT = {
    "allow_origins": ["*"],
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}


def _langgraph_cors() -> dict:
    return json.loads((ROOT / "langgraph.json").read_text(encoding="utf-8"))["http"]["cors"]


def _client(inner: dict) -> TestClient:
    def ok(_request):
        return PlainTextResponse("ok")

    stack = Starlette(
        routes=[Route("/ok", ok, methods=["GET", "POST"])],
        middleware=[
            Middleware(CORSMiddleware, **APP_CORS.kwargs),
            Middleware(CORSMiddleware, **inner),
        ],
    )
    return TestClient(stack)


def test_langgraph_json_and_the_dockerfile_give_langgraphs_cors_no_origins() -> None:
    assert _langgraph_cors() == {"allow_origins": []}
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    http = json.loads(re.search(r"ENV LANGGRAPH_HTTP='(.*)'", dockerfile).group(1))
    assert http["cors"] == _langgraph_cors()


def test_a_plain_response_names_no_foreign_origin() -> None:
    response = _client(_langgraph_cors()).get("/ok", headers={"Origin": FOREIGN})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_an_allowed_origin_keeps_its_header_and_its_preflight() -> None:
    client = _client(_langgraph_cors())
    plain = client.get("/ok", headers={"Origin": ALLOWED})
    assert plain.headers["access-control-allow-origin"] == ALLOWED
    preflight = client.options(
        "/ok",
        headers={
            "Origin": ALLOWED,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == ALLOWED


def test_a_foreign_preflight_is_still_refused() -> None:
    preflight = _client(_langgraph_cors()).options(
        "/ok", headers={"Origin": FOREIGN, "Access-Control-Request-Method": "POST"}
    )
    assert preflight.status_code == 400


def test_langgraphs_default_echoed_any_origin_with_credentials() -> None:
    # The bug, kept as the reason for the setting: the inner default names a foreign origin.
    response = _client(LANGGRAPH_DEFAULT).get("/ok", headers={"Origin": FOREIGN})
    assert response.headers["access-control-allow-origin"] == FOREIGN
    assert response.headers["access-control-allow-credentials"] == "true"
