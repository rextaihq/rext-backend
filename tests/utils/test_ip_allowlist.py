"""Tests for the account-creation IP allowlist helper and its integration
with the per-device account-creation cap (check_device_account_limit)."""

from unittest.mock import Mock

import pytest
from fastapi import HTTPException, Request

from src.api.config import get_settings
from src.utils.ip_allowlist import is_account_creation_ip_allowlisted


@pytest.fixture
def allowlist(monkeypatch):
    """Set ACCOUNT_CREATION_IP_ALLOWLIST for the duration of a test."""

    def _set(value: str) -> None:
        monkeypatch.setattr(get_settings(), "ACCOUNT_CREATION_IP_ALLOWLIST", value)

    return _set


# ---------------------------------------------------------------------------
# is_account_creation_ip_allowlisted
# ---------------------------------------------------------------------------


def test_empty_allowlist_matches_nothing(allowlist):
    allowlist("")
    assert is_account_creation_ip_allowlisted("203.0.113.10") is False


def test_missing_client_ip_is_not_allowlisted(allowlist):
    allowlist("203.0.113.10")
    assert is_account_creation_ip_allowlisted(None) is False
    assert is_account_creation_ip_allowlisted("") is False


def test_single_allowlisted_ip_matches(allowlist):
    allowlist("203.0.113.10")
    assert is_account_creation_ip_allowlisted("203.0.113.10") is True


def test_non_allowlisted_ip_does_not_match(allowlist):
    allowlist("203.0.113.10")
    assert is_account_creation_ip_allowlisted("203.0.113.99") is False


def test_multiple_allowlisted_ips(allowlist):
    allowlist(" 203.0.113.10 , 203.0.113.11 ")
    assert is_account_creation_ip_allowlisted("203.0.113.10") is True
    assert is_account_creation_ip_allowlisted("203.0.113.11") is True
    assert is_account_creation_ip_allowlisted("203.0.113.12") is False


def test_cidr_range_is_supported(allowlist):
    allowlist("203.0.113.0/24")
    assert is_account_creation_ip_allowlisted("203.0.113.55") is True
    assert is_account_creation_ip_allowlisted("203.0.114.55") is False


def test_ipv6_is_supported(allowlist):
    allowlist("2001:db8::/32")
    assert is_account_creation_ip_allowlisted("2001:db8::1") is True
    assert is_account_creation_ip_allowlisted("2001:dead::1") is False


def test_invalid_entries_are_ignored_but_valid_ones_still_work(allowlist):
    allowlist("not-an-ip, 999.999.999.999, 203.0.113.10")
    assert is_account_creation_ip_allowlisted("203.0.113.10") is True
    assert is_account_creation_ip_allowlisted("10.0.0.1") is False


def test_unparseable_client_ip_fails_closed(allowlist):
    allowlist("203.0.113.10")
    assert is_account_creation_ip_allowlisted("garbage") is False


def test_fully_invalid_allowlist_matches_nothing(allowlist):
    allowlist("nonsense,,also-bad")
    assert is_account_creation_ip_allowlisted("203.0.113.10") is False


# ---------------------------------------------------------------------------
# check_device_account_limit integration
# ---------------------------------------------------------------------------


def _request_from_ip(ip: str | None) -> Request:
    request = Mock(spec=Request)
    if ip is None:
        request.client = None
    else:
        request.client = Mock()
        request.client.host = ip
    return request


@pytest.fixture
def patch_subscription_service(monkeypatch):
    """Replace SubscriptionService in the auth module with a stub returning a
    configurable non-paid account count, and record whether it was consulted."""
    from src.api.routes.users import auth as auth_module

    state = {"count": 0, "consulted": False}

    class _StubSubscriptionService:
        def __init__(self, db):
            pass

        async def count_non_paid_accounts_for_device(self, fingerprint: str) -> int:
            state["consulted"] = True
            return state["count"]

    monkeypatch.setattr(auth_module, "SubscriptionService", _StubSubscriptionService)
    return state


async def _run_limit_check(request: Request):
    from src.api.routes.users import auth as auth_module

    await auth_module.check_device_account_limit(request, device_fingerprint="fp-123", db=None)


@pytest.mark.asyncio
async def test_limit_check_bypassed_for_allowlisted_ip(allowlist, patch_subscription_service):
    allowlist("203.0.113.10")
    patch_subscription_service["count"] = 999  # far over the cap

    await _run_limit_check(_request_from_ip("203.0.113.10"))

    # Allowlisted IPs short-circuit before the DB is ever queried.
    assert patch_subscription_service["consulted"] is False


@pytest.mark.asyncio
async def test_limit_check_still_enforced_for_non_allowlisted_ip(
    allowlist, patch_subscription_service
):
    allowlist("203.0.113.10")
    patch_subscription_service["count"] = 5  # at the cap

    with pytest.raises(HTTPException) as exc_info:
        await _run_limit_check(_request_from_ip("198.51.100.7"))

    assert exc_info.value.status_code == 403
    assert patch_subscription_service["consulted"] is True


@pytest.mark.asyncio
async def test_limit_check_still_enforced_when_allowlist_empty(
    allowlist, patch_subscription_service
):
    allowlist("")
    patch_subscription_service["count"] = 5

    with pytest.raises(HTTPException) as exc_info:
        await _run_limit_check(_request_from_ip("203.0.113.10"))

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_non_allowlisted_ip_under_cap_is_allowed(allowlist, patch_subscription_service):
    allowlist("203.0.113.10")
    patch_subscription_service["count"] = 2  # below the cap

    await _run_limit_check(_request_from_ip("198.51.100.7"))

    assert patch_subscription_service["consulted"] is True
