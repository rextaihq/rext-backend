from src.api.middleware.rate_limiter import (
    SECONDS_PER_MINUTE,
    SECONDS_PER_HOUR,
    SECONDS_PER_DAY,
    LOGIN_LIMIT,
    REGISTRATION_LIMIT,
    OAUTH_LIMIT,
    NOTIFICATION_READ_LIMIT,
    login_rate_limit,
    registration_rate_limit,
    oauth_rate_limit,
    notification_read_rate_limit,
)


def test_time_constants_are_consistent() -> None:
    assert SECONDS_PER_MINUTE == 60
    assert SECONDS_PER_HOUR == 3600
    assert SECONDS_PER_DAY == 86400


def test_login_rate_limit_profile_matches_factory() -> None:
    limiter = login_rate_limit()
    assert limiter.requests == LOGIN_LIMIT.requests
    assert limiter.window_seconds == LOGIN_LIMIT.window_minutes * SECONDS_PER_MINUTE


def test_registration_rate_limit_profile_matches_factory() -> None:
    limiter = registration_rate_limit()
    assert limiter.requests == REGISTRATION_LIMIT.requests
    assert limiter.window_seconds == REGISTRATION_LIMIT.window_minutes * SECONDS_PER_MINUTE


def test_oauth_rate_limit_profile_matches_factory() -> None:
    limiter = oauth_rate_limit()
    assert limiter.requests == OAUTH_LIMIT.requests
    assert limiter.window_seconds == OAUTH_LIMIT.window_minutes * SECONDS_PER_MINUTE


def test_notification_read_rate_limit_profile_matches_factory() -> None:
    limiter = notification_read_rate_limit()
    assert limiter.requests == NOTIFICATION_READ_LIMIT.requests
    assert limiter.window_seconds == NOTIFICATION_READ_LIMIT.window_minutes * SECONDS_PER_MINUTE