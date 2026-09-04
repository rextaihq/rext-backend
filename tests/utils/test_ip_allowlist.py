"""Tests for the IP allowlist matching helpers and their integration with the
per-device account-creation cap (check_device_account_limit)."""

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException, Request

from src.utils.ip_allowlist import (
    ip_matches_allowlist,
    normalize_allowlist_value,
    reject_reason_for_egress_ip,
)

# ---------------------------------------------------------------------------
# normalize_allowlist_value
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("203.0.113.10", "203.0.113.10"),
        ("  203.0.113.10  ", "203.0.113.10"),
        ("203.0.113.0/24", "203.0.113.0/24"),
        ("203.0.113.5/24", "203.0.113.0/24"),  # host bits dropped
        ("2001:DB8::1", "2001:db8::1"),  # compressed / lowercased
        ("2001:db8::/32", "2001:db8::/32"),
    ],
)
def test_normalize_allowlist_value_canonicalizes(raw, expected):
    assert normalize_allowlist_value(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "not-an-ip", "999.999.999.999", "203.0.113.10/33"])
def test_normalize_allowlist_value_rejects_invalid(raw):
    with pytest.raises(ValueError):
        normalize_allowlist_value(raw)


# ---------------------------------------------------------------------------
# ip_matches_allowlist
# ---------------------------------------------------------------------------

def test_empty_entries_match_nothing():
    assert ip_matches_allowlist("203.0.113.10", []) is False


def test_missing_client_ip_is_not_matched():
    assert ip_matches_allowlist(None, ["203.0.113.10"]) is False
    assert ip_matches_allowlist("", ["203.0.113.10"]) is False


def test_single_ip_match():
    assert ip_matches_allowlist("203.0.113.10", ["203.0.113.10"]) is True
    assert ip_matches_allowlist("203.0.113.99", ["203.0.113.10"]) is False


def test_multiple_entries():
    entries = ["203.0.113.10", "203.0.113.11"]
    assert ip_matches_allowlist("203.0.113.11", entries) is True
    assert ip_matches_allowlist("203.0.113.12", entries) is False


def test_cidr_range_match():
    assert ip_matches_allowlist("203.0.113.55", ["203.0.113.0/24"]) is True
    assert ip_matches_allowlist("203.0.114.55", ["203.0.113.0/24"]) is False


def test_ipv6_match():
    assert ip_matches_allowlist("2001:db8::1", ["2001:db8::/32"]) is True
    assert ip_matches_allowlist("2001:dead::1", ["2001:db8::/32"]) is False


def test_invalid_entries_are_skipped_but_valid_ones_work():
    entries = ["not-an-ip", "999.999.999.999", "203.0.113.10"]
    assert ip_matches_allowlist("203.0.113.10", entries) is True
    assert ip_matches_allowlist("10.0.0.1", entries) is False


def test_unparseable_client_ip_fails_closed():
    assert ip_matches_allowlist("garbage", ["203.0.113.10"]) is False


# ---------------------------------------------------------------------------
# reject_reason_for_egress_ip  (allowlist must hold public egress IPs)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value",
    ["8.8.8.8", "1.1.1.1", "203.0.113.10", "203.0.113.0/24", "2001:4860:4860::8888"],
)
def test_public_egress_ip_is_accepted(value):
    assert reject_reason_for_egress_ip(value) is None


@pytest.mark.parametrize(
    "value",
    [
        "192.168.1.10",
        "10.0.0.5",
        "172.16.4.4",
        "127.0.0.1",
        "169.254.10.10",
        "10.0.0.0/8",
        "0.0.0.0/0",
        "fe80::1",
        "fc00::1",
        "::1",
        "224.0.0.1",
    ],
)
def test_private_or_non_routable_ip_is_rejected(value):
    reason = reject_reason_for_egress_ip(value)
    assert reason is not None and isinstance(reason, str)


# ---------------------------------------------------------------------------
# check_device_account_limit integration
# ---------------------------------------------------------------------------

def _request_from_ip(ip):
    request = Mock(spec=Request)
    if ip is None:
        request.client = None
    else:
        request.client = Mock()
        request.client.host = ip
    return request


@pytest.fixture
def patched_services(monkeypatch):
    """Stub AccountCreationAllowlistService + SubscriptionService in the auth
    module. `state` controls the allowlist decision and the non-paid count and
    records whether the subscription cap query was reached."""
    from src.api.routes.users import auth as auth_module

    state = {"allowlisted": False, "count": 0, "cap_checked": False}

    class _StubAllowlistService:
        def __init__(self, db):
            pass

        async def is_ip_allowlisted(self, client_ip):
            return state["allowlisted"]

    class _StubSubscriptionService:
        def __init__(self, db):
            pass

        async def count_non_paid_accounts_for_device(self, fingerprint):
            state["cap_checked"] = True
            return state["count"]

    monkeypatch.setattr(auth_module, "AccountCreationAllowlistService", _StubAllowlistService)
    monkeypatch.setattr(auth_module, "SubscriptionService", _StubSubscriptionService)
    return state


async def _run_limit_check(request):
    from src.api.routes.users import auth as auth_module

    await auth_module.check_device_account_limit(
        request, device_fingerprint="fp-123", db=None
    )


@pytest.mark.asyncio
async def test_allowlisted_public_ip_bypasses_multiple_account_restriction(patched_services):
    """An approved org egress IP creates accounts past the per-device cap."""
    patched_services["allowlisted"] = True
    patched_services["count"] = 999  # far over MAX_NON_PAID_ACCOUNTS_PER_DEVICE

    await _run_limit_check(_request_from_ip("203.0.113.10"))  # no HTTPException

    assert patched_services["cap_checked"] is False  # short-circuited before the DB


@pytest.mark.asyncio
async def test_non_allowlisted_ip_stays_restricted(patched_services):
    """Every other IP still hits the unchanged 403 cap."""
    patched_services["allowlisted"] = False
    patched_services["count"] = 5  # at the cap

    with pytest.raises(HTTPException) as exc_info:
        await _run_limit_check(_request_from_ip("198.51.100.7"))

    assert exc_info.value.status_code == 403
    assert patched_services["cap_checked"] is True


@pytest.mark.asyncio
async def test_non_allowlisted_ip_under_cap_is_allowed(patched_services):
    patched_services["allowlisted"] = False
    patched_services["count"] = 2

    await _run_limit_check(_request_from_ip("198.51.100.7"))

    assert patched_services["cap_checked"] is True


# ---------------------------------------------------------------------------
# AccountCreationAllowlistService (no-DB unit slices)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_service_is_ip_allowlisted_uses_active_values(monkeypatch):
    from src.services.account_creation_allowlist_service import (
        AccountCreationAllowlistService,
    )

    service = AccountCreationAllowlistService(db=Mock())
    monkeypatch.setattr(
        service, "_active_ip_values", AsyncMock(return_value=["203.0.113.0/24"])
    )

    assert await service.is_ip_allowlisted("203.0.113.7") is True
    assert await service.is_ip_allowlisted("198.51.100.7") is False
    assert await service.is_ip_allowlisted(None) is False


@pytest.mark.asyncio
async def test_service_is_ip_allowlisted_fails_closed_on_error(monkeypatch):
    from src.services.account_creation_allowlist_service import (
        AccountCreationAllowlistService,
    )

    service = AccountCreationAllowlistService(db=Mock())
    monkeypatch.setattr(
        service, "_active_ip_values", AsyncMock(side_effect=RuntimeError("redis down"))
    )

    assert await service.is_ip_allowlisted("203.0.113.7") is False


def test_service_normalize_rejects_invalid():
    from src.api.middleware.exceptions import RextValidationException
    from src.services.account_creation_allowlist_service import (
        AccountCreationAllowlistService,
    )

    with pytest.raises(RextValidationException):
        AccountCreationAllowlistService._normalize("not-an-ip")

    assert AccountCreationAllowlistService._normalize(" 203.0.113.5/24 ") == "203.0.113.0/24"
