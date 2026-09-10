"""
IP allowlist matching helpers
=============================

Pure, dependency-free helpers for the account-creation IP allowlist. They answer
"does this verified client IP match one of these allowlist entries?" and are
used by ``AccountCreationAllowlistService`` (which owns the DB-backed list) and
by ``check_device_account_limit`` in ``src/api/routes/users/auth.py``.

Security notes:
- Take the client IP from ``get_verified_client_ip(request)`` — never from
  ``X-Forwarded-For`` / ``X-Real-IP`` directly. Traefik *appends* to
  ``X-Forwarded-For``, so every entry left of the last one is supplied by the
  client and is trivially forged.
- Fails closed: an empty list, an unparseable client IP, an over-broad or
  malformed entry, or a reverse-proxy configuration that cannot be trusted all
  resolve to "not allowlisted", so the account-creation cap stays in force.
"""

from ipaddress import (
    IPv4Network,
    IPv6Network,
    ip_address,
    ip_network,
)
from typing import Any, Iterable, Optional

from src.utils.logger import logger

# Smallest prefix an allowlist entry may use. The list holds an organization's
# egress address(es); a /24 (256 addresses) is already generous for a NAT pool.
# Anything wider would hand the bypass to a large slice of the internet, which
# is never an "explicitly configured" allowlisting decision.
MIN_ALLOWLIST_PREFIXLEN = {4: 24, 6: 64}

# TRUSTED_PROXY_IPS values that tell uvicorn's ProxyHeadersMiddleware to trust
# any peer. Under these it returns the *leftmost* X-Forwarded-For entry, which
# the client controls end-to-end — see proxy_trust_is_spoofable().
_CATCH_ALL_PROXY_TOKENS = frozenset({"*", "0.0.0.0/0", "::/0"})

# Ranges that must never appear in the account-creation allowlist: this list is
# meant to hold an organization's *public egress* IP(s) (the address Traefik/
# Coolify records as the source once traffic has left the org NAT gateway), not
# per-device or per-subnet private addresses. A client can never legitimately
# present one of these as its source IP to the app, so allowing one is at best
# useless and at worst a foot-gun.
_NON_EGRESS_NETWORKS = [
    ip_network("0.0.0.0/8"),  # "this host on this network"
    ip_network("10.0.0.0/8"),  # RFC 1918 private
    ip_network("127.0.0.0/8"),  # loopback
    ip_network("169.254.0.0/16"),  # link-local
    ip_network("172.16.0.0/12"),  # RFC 1918 private
    ip_network("192.168.0.0/16"),  # RFC 1918 private
    ip_network("::1/128"),  # IPv6 loopback
    ip_network("::/128"),  # IPv6 unspecified
    ip_network("fc00::/7"),  # IPv6 unique local (ULA)
    ip_network("fe80::/10"),  # IPv6 link-local
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

    if _entry_is_too_broad(as_network):
        minimum = MIN_ALLOWLIST_PREFIXLEN[as_network.version]
        return (
            f"{normalized_value} covers too much of the internet - an allowlist "
            f"entry must be a single address or a /{minimum} or narrower range"
        )

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


def _entry_is_too_broad(network) -> bool:
    """True when a CIDR entry covers more addresses than an egress range should."""
    return network.prefixlen < MIN_ALLOWLIST_PREFIXLEN[network.version]


def resolve_trusted_proxy_hosts(trusted_proxy_ips: Optional[str]) -> list:
    """
    The ``trusted_hosts`` list ProxyHeadersMiddleware is configured with.

    Single source of truth: ``src/api/server.py`` builds the middleware from
    this, and ``proxy_trust_is_spoofable`` judges the very same list, so the
    middleware's behaviour and the allowlist's trust decision can never drift
    apart. An unset/blank setting falls back to loopback only, which means
    ``X-Forwarded-For`` is never honoured.
    """
    entries = [e.strip() for e in (trusted_proxy_ips or "").split(",") if e.strip()]
    return entries or ["127.0.0.1", "::1"]


def proxy_trust_is_spoofable(trusted_proxy_ips: Optional[str]) -> bool:
    """
    Return True when the trusted-proxy configuration names no concrete proxy.

    ``*``, ``0.0.0.0/0`` and ``::/0`` all make uvicorn's ProxyHeadersMiddleware
    trust every peer, and it then hands back the **leftmost** ``X-Forwarded-For``
    entry. Traefik appends to that header rather than replacing it, so the
    leftmost entry is whatever the client sent — any caller could present an
    allowlisted address. Under such a configuration ``request.client.host`` is
    attacker-controlled and must not drive a security decision.
    """
    for entry in resolve_trusted_proxy_hosts(trusted_proxy_ips):
        if entry in _CATCH_ALL_PROXY_TOKENS:
            return True
        try:
            if ip_network(entry, strict=False).prefixlen == 0:
                return True
        except ValueError:
            continue
    return False


def get_verified_client_ip(request: Any) -> Optional[str]:
    """
    The client IP this app is willing to base a security decision on, else None.

    Reads only ``request.client.host`` — the value uvicorn's
    ProxyHeadersMiddleware derives from ``X-Forwarded-For``, and only for peers
    listed in ``TRUSTED_PROXY_IPS``. ``X-Forwarded-For`` and ``X-Real-IP`` are
    never read here.

    Returns None — so the caller falls through to its normal restriction — when:
    - the connection carries no client address,
    - that address does not parse as an IP, or
    - ``TRUSTED_PROXY_IPS`` is a catch-all, which leaves ``request.client.host``
      holding a client-supplied ``X-Forwarded-For`` value.
    """
    from src.api.config import get_settings

    client = getattr(request, "client", None)
    host = getattr(client, "host", None) if client is not None else None
    if not host:
        return None

    try:
        ip_address(host)
    except ValueError:
        logger.warning(f"IP allowlist: unparseable client IP {host!r}")
        return None

    if proxy_trust_is_spoofable(get_settings().TRUSTED_PROXY_IPS):
        logger.error(
            f"IP allowlist: refusing to trust client IP {host!r} because "
            "TRUSTED_PROXY_IPS is a catch-all - X-Forwarded-For is "
            "client-controlled under that setting. Set TRUSTED_PROXY_IPS to the "
            "reverse proxy's exact address/subnet to re-enable the allowlist."
        )
        return None

    return host


def ip_matches_allowlist(client_ip: Optional[str], entries: Iterable[str]) -> bool:
    """
    Return True only when ``client_ip`` explicitly matches one of ``entries``
    (a single address, or a CIDR network no wider than
    ``MIN_ALLOWLIST_PREFIXLEN``).

    Any problem — no client IP, unparseable client IP, malformed or over-broad
    entry — resolves to False so the caller keeps its existing restriction.
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
                network = ip_network(entry, strict=False)
                if _entry_is_too_broad(network):
                    logger.warning(f"IP allowlist: ignoring over-broad entry {entry!r}")
                    continue
                if client in network:
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
