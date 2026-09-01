"""
Account-creation IP allowlist
=============================

Small, single-purpose helper around the ``ACCOUNT_CREATION_IP_ALLOWLIST``
setting. It answers exactly one question - "is this verified client IP allowed
to create multiple accounts?" - so the per-device account-creation cap in
``src/api/routes/users/auth.py`` can be bypassed for a handful of approved
internal networks (office egress IPs, CI runners, ...) without changing the
restriction itself.

Usage:
    from src.utils.ip_allowlist import is_account_creation_ip_allowlisted

    if is_account_creation_ip_allowlisted(client_ip):
        return  # skip the per-device free-account cap

Security notes:
- Only pass an IP that was established by the ASGI stack, i.e.
  ``request.client.host``. Uvicorn's ``ProxyHeadersMiddleware`` rewrites that
  value from ``X-Forwarded-For`` *only* for the proxies listed in
  ``TRUSTED_PROXY_IPS`` (see ``src/api/server.py``); every other client keeps
  its real socket address. Never pass a raw header value here.
- Fails closed: an empty, missing, or malformed allowlist entry means *no* IP
  matches, so the existing restriction stays fully in force.
"""

from ipaddress import ip_address, ip_network
from typing import List, Optional

from src.api.config import get_settings
from src.utils.logger import logger


def _allowlist_entries() -> List[str]:
    """Return the configured allowlist entries (trimmed, empties removed)."""
    return get_settings().account_creation_ip_allowlist


def is_account_creation_ip_allowlisted(client_ip: Optional[str]) -> bool:
    """
    Return True only when ``client_ip`` explicitly matches a configured allowlist
    entry - a single IPv4/IPv6 address or a CIDR network.

    Any problem (no configuration, unparseable client IP, malformed entry)
    resolves to False so the account-creation cap is never accidentally
    disabled.

    Args:
        client_ip: The verified client IP (``request.client.host``), or None.

    Returns:
        True if the IP is explicitly allowlisted, False otherwise.
    """
    if not client_ip:
        return False

    entries = _allowlist_entries()
    if not entries:
        return False

    try:
        client = ip_address(client_ip)
    except ValueError:
        logger.warning(f"Account-creation allowlist: unparseable client IP {client_ip!r}")
        return False

    for entry in entries:
        try:
            if "/" in entry:
                if client in ip_network(entry, strict=False):
                    return True
            elif client == ip_address(entry):
                return True
        except ValueError:
            logger.warning(f"Account-creation allowlist: ignoring invalid entry {entry!r}")
            continue

    return False
