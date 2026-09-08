"""
IP allowlist matching helpers
=============================

Pure, dependency-free helpers for the account-creation IP allowlist. They answer
"does this verified client IP match one of these allowlist entries?" and are
used by ``AccountCreationAllowlistService`` (which owns the DB-backed list) and
by ``check_device_account_limit`` in ``src/api/routes/users/auth.py``.

Security notes:
- Only pass an IP that was established by the ASGI stack, i.e.
  ``request.client.host``. Uvicorn's ``ProxyHeadersMiddleware`` rewrites that
  value from ``X-Forwarded-For`` *only* for the proxies listed in
  ``TRUSTED_PROXY_IPS`` (see ``src/api/server.py``); every other client keeps
  its real socket address. Never pass a raw header value here.
- Fails closed: an empty list, an unparseable client IP, or a malformed entry
  never produces a match, so the account-creation cap stays in force.
"""

from ipaddress import (
    IPv4Network,
    IPv6Network,
    ip_address,
    ip_network,
)
from typing import Iterable, Optional

from src.utils.logger import logger

# Ranges that must never appear in the account-creation allowlist: this list is
# meant to hold an organization's *public egress* IP(s) (the address Traefik/
# Coolify records as the source once traffic has left the org NAT gateway), not
# per-device or per-subnet private addresses. A client can never legitimately
# present one of these as its source IP to the app, so allowing one is at best
# useless and at worst a foot-gun.
_NON_EGRESS_NETWORKS = [
    ip_network("0.0.0.0/8"),      # "this host on this network"
    ip_network("10.0.0.0/8"),     # RFC 1918 private
    ip_network("127.0.0.0/8"),    # loopback
    ip_network("169.254.0.0/16"), # link-local
    ip_network("172.16.0.0/12"),  # RFC 1918 private
    ip_network("192.168.0.0/16"), # RFC 1918 private
    ip_network("::1/128"),        # IPv6 loopback
    ip_network("::/128"),         # IPv6 unspecified
    ip_network("fc00::/7"),       # IPv6 unique local (ULA)
    ip_network("fe80::/10"),      # IPv6 link-local
]


def normalize_allowlist_value(value: str) -> str:
    """
    Validate and canonicalize a single allowlist entry.

    Accepts a bare IPv4/IPv6 address ("203.0.113.10", "2001:db8::1") or a CIDR
    network ("203.0.113.0/24", "2001:db8::/32") and returns its canonical string
    form (compressed IPv6, network address for CIDRs).

    Raises:
        ValueError: if the value is not a valid IP address or network.
    """
    candidate = (value or "").strip()
    if not candidate:
        raise ValueError("IP address must not be empty")

    if "/" in candidate:
        # strict=False so "203.0.113.5/24" is accepted and stored as "203.0.113.0/24"
        return str(ip_network(candidate, strict=False))
    return str(ip_address(candidate))


def reject_reason_for_egress_ip(normalized_value: str) -> Optional[str]:
    """
    Return a human-readable reason string if ``normalized_value`` (already run
    through ``normalize_allowlist_value``) is not usable as a public egress
    entry, or None if it is acceptable.

    Rejects private (RFC 1918 / ULA), loopback, link-local, multicast and
    unspecified ranges — an org's traffic reaches the app from its NAT gateway's
    *public* IP, never from these.
    """
    try:
        as_network = ip_network(
            normalized_value
            if "/" in normalized_value
            else f"{normalized_value}/{'128' if ':' in normalized_value else '32'}"
        )
    except ValueError:
        return "not a valid IP address or CIDR range"

    if as_network.is_multicast:
        return "multicast addresses cannot be an egress source"
    if as_network.is_unspecified:
        return "the unspecified address cannot be an egress source"

    same_version = (
        (n for n in _NON_EGRESS_NETWORKS if isinstance(n, IPv4Network))
        if as_network.version == 4
        else (n for n in _NON_EGRESS_NETWORKS if isinstance(n, IPv6Network))
    )
    for blocked in same_version:
        if as_network.overlaps(blocked):
            return (
                f"{normalized_value} falls in the non-routable range {blocked} - "
                "the allowlist must hold the organization's public egress IP(s), "
                "not private / loopback / link-local addresses"
            )
    return None


def ip_matches_allowlist(client_ip: Optional[str], entries: Iterable[str]) -> bool:
    """
    Return True only when ``client_ip`` explicitly matches one of ``entries``
    (a single address or a CIDR network).

    Any problem — no client IP, unparseable client IP, malformed entry —
    resolves to False so the caller keeps its existing restriction.
    """
    if not client_ip:
        return False

    try:
        client = ip_address(client_ip)
    except ValueError:
        logger.warning(f"IP allowlist: unparseable client IP {client_ip!r}")
        return False

    for entry in entries:
        try:
            if "/" in entry:
                if client in ip_network(entry, strict=False):
                    return True
            elif client == ip_address(entry):
                return True
        except ValueError:
            logger.warning(f"IP allowlist: ignoring invalid entry {entry!r}")
            continue

    return False


def is_account_creation_ip_allowlisted(client_ip: Optional[str]) -> bool:
    """Return True if client_ip is in settings.ACCOUNT_CREATION_IP_ALLOWLIST."""
    from src.api.config import get_settings
    raw = getattr(get_settings(), "ACCOUNT_CREATION_IP_ALLOWLIST", "") or ""
    entries = [item.strip() for item in raw.split(",") if item.strip()]
    return ip_matches_allowlist(client_ip, entries)
