"""The staging API accepts our dashboard previews' origins, and production never can (G68, rext-control#578).

A preview on Vercel has a new host for every deployment, so ALLOWED_ORIGINS can't list it. With
ALLOW_PREVIEW_ORIGINS on, CORS also accepts our team's deployment hosts, matched whole; the settings
refuse the switch unless ENVIRONMENT is staging, development or local.
"""

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.api.config import PREVIEW_ORIGIN_REGEX, Settings

REQUIRED = {
    "SECRET_KEY": "x" * 32,
    "REFRESH_SECRET_KEY": "y" * 32,
    "POSTGRES_URI_CUSTOM": "postgresql://localhost/test",
}
OURS = "https://rext-o4wss9vqi-it-rx.vercel.app"


def _settings(**values):
    return Settings(**REQUIRED, **values)


@pytest.mark.parametrize("environment", ["production", "Production", "prod", "live"])
def test_the_switch_is_refused_outside_staging_and_development(environment):
    with pytest.raises(ValidationError) as exc_info:
        _settings(ENVIRONMENT=environment, ALLOW_PREVIEW_ORIGINS=True)

    assert "ALLOW_PREVIEW_ORIGINS is only allowed" in str(exc_info.value)


@pytest.mark.parametrize("environment", ["staging", "development", "local"])
def test_the_switch_turns_the_pattern_on(environment):
    assert _settings(ENVIRONMENT=environment, ALLOW_PREVIEW_ORIGINS=True).allowed_origin_regex == (
        PREVIEW_ORIGIN_REGEX
    )


def test_off_by_default_everywhere():
    assert _settings(ENVIRONMENT="production").allowed_origin_regex is None
    assert _settings(ENVIRONMENT="staging").allowed_origin_regex is None


def _preflight(settings: Settings, origin: str):
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://staging.rext.ai"],
        allow_origin_regex=settings.allowed_origin_regex,
        allow_credentials=True,
        allow_methods=["GET"],
    )
    return TestClient(app).options(
        "/api/v1/plans", headers={"Origin": origin, "Access-Control-Request-Method": "GET"}
    )


def test_a_preview_of_ours_passes_the_preflight():
    response = _preflight(_settings(ENVIRONMENT="staging", ALLOW_PREVIEW_ORIGINS=True), OURS)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == OURS


@pytest.mark.parametrize(
    "origin",
    [
        "https://rext-o4wss9vqi-x-it-rx.vercel.app",  # another team whose name ends in "-it-rx"
        "http://rext-o4wss9vqi-it-rx.vercel.app",  # not https
        "https://a.rext-o4wss9vqi-it-rx.vercel.app",  # an extra subdomain
        "https://rext-o4wss9vqi-it-rx.vercel.app:8443",  # a port
        "https://rext-o4wss9vqi-it-rx.vercel.app/x",  # a path
        "https://rext-o4wss9vqi-it-rx.vercel.app.example.com",  # a suffix
        "https://rext-o4wss9vq-it-rx.vercel.app",  # eight characters
        "https://rext-O4WSS9VQI-it-rx.vercel.app",  # upper case
        "https://rext-app-git-main-it-rx.vercel.app",  # a branch alias
        "https://rext-app-git-foo-x-it-rx.vercel.app",  # another team's branch alias
    ],
)
def test_look_alikes_are_refused(origin):
    assert (
        _preflight(_settings(ENVIRONMENT="staging", ALLOW_PREVIEW_ORIGINS=True), origin).status_code
        == 400
    )


def test_a_preview_is_refused_with_the_switch_off():
    assert _preflight(_settings(ENVIRONMENT="staging"), OURS).status_code == 400


def test_the_server_passes_the_pattern_to_cors():
    from src.api.server import app, settings

    cors = next(m for m in app.user_middleware if m.cls is CORSMiddleware)

    assert cors.kwargs["allow_origin_regex"] == settings.allowed_origin_regex
