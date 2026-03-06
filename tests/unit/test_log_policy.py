from src.api.lib.log_policy import get_event_level, get_severity_level


def test_severity_level_mapping() -> None:
    assert get_severity_level("critical") == "error"
    assert get_severity_level("high") == "error"
    assert get_severity_level("medium") == "warning"
    assert get_severity_level("low") == "info"


def test_event_level_mapping() -> None:
    assert get_event_level("permission_denied") == "warning"
    assert get_event_level("transaction_committed") == "debug"
    assert get_event_level("rate_limit_exceeded") == "warning"
