"""
SSRF Prevention Utility

Validates URLs before server-side requests to prevent Server-Side Request Forgery.
Implements OWASP SSRF Prevention Cheat Sheet recommendations.

Reference: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
"""

import ipaddress
import socket
from urllib.parse import urlparse
from src.utils.logger import logger


# Private and reserved IP ranges that must be blocked
BLOCKED_IP_NETWORKS = [
    # Loopback
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    # Private networks (RFC 1918)
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    # Link-local / Cloud metadata (AWS, GCP, Azure)
    ipaddress.ip_network("169.254.0.0/16"),
    # IPv6 link-local
    ipaddress.ip_network("fe80::/10"),
    # IPv6 unique local
    ipaddress.ip_network("fc00::/7"),
    # Multicast
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("ff00::/8"),
    # Reserved for documentation
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    # Broadcast
    ipaddress.ip_network("255.255.255.255/32"),
]

# Allowed URL schemes
ALLOWED_SCHEMES = {"http", "https"}

# Maximum URL length to prevent abuse
MAX_URL_LENGTH = 2048


class SSRFValidationError(ValueError):
    """Raised when a URL fails SSRF validation."""
    pass


def validate_url_for_ssrf(url: str) -> str:
    """
    Validate a URL to prevent SSRF attacks.

    Performs the following checks:
    1. URL length limit
    2. Scheme allowlist (http/https only)
    3. Hostname presence and format
    4. DNS resolution to get actual IP addresses
    5. IP address validation against blocked ranges

    Args:
        url: The URL to validate.

    Returns:
        The validated URL string (unchanged).

    Raises:
        SSRFValidationError: If the URL fails any validation check.
    """
    if len(url) > MAX_URL_LENGTH:
        raise SSRFValidationError(f"URL exceeds maximum length of {MAX_URL_LENGTH} characters")

    parsed = urlparse(url)

    # Check scheme
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise SSRFValidationError(f"URL scheme '{parsed.scheme}' is not allowed. Only {ALLOWED_SCHEMES} are permitted.")

    # Check hostname exists
    hostname = parsed.hostname
    if not hostname:
        raise SSRFValidationError("URL must contain a valid hostname")

    # Check for IP address directly in URL
    try:
        ip = ipaddress.ip_address(hostname)
        _check_ip_blocked(ip)
        return url
    except ValueError:
        # Not a raw IP address — it's a hostname, resolve it
        pass

    # Resolve hostname to IP addresses and validate each one
    resolved_ips = _resolve_hostname(hostname)
    if not resolved_ips:
        raise SSRFValidationError(f"Could not resolve hostname: {hostname}")

    for ip_str in resolved_ips:
        try:
            ip = ipaddress.ip_address(ip_str)
            _check_ip_blocked(ip)
        except ValueError:
            raise SSRFValidationError(f"Invalid IP address from DNS resolution: {ip_str}")

    logger.info(
        "URL passed SSRF validation",
        extra={"url_host": hostname, "resolved_ips": resolved_ips},
    )
    return url


def _check_ip_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    """
    Check if an IP address falls within any blocked network range.

    Args:
        ip: The IP address to check.

    Raises:
        SSRFValidationError: If the IP is in a blocked range.
    """
    if ip.is_private or ip.is_reserved or ip.is_loopback or ip.is_link_local or ip.is_multicast:
        raise SSRFValidationError(
            f"URL resolves to blocked IP address: {ip} "
            f"(private={ip.is_private}, reserved={ip.is_reserved}, "
            f"loopback={ip.is_loopback}, link_local={ip.is_link_local})"
        )

    for network in BLOCKED_IP_NETWORKS:
        if ip in network:
            raise SSRFValidationError(
                f"URL resolves to blocked IP range {network}: {ip}"
            )


def _resolve_hostname(hostname: str) -> list[str]:
    """
    Resolve a hostname to its IP addresses using DNS.

    Uses socket.getaddrinfo for both IPv4 and IPv6 resolution.

    Args:
        hostname: The hostname to resolve.

    Returns:
        List of resolved IP address strings.
    """
    try:
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        ips = list({info[4][0] for info in addr_info})
        return ips
    except socket.gaierror as e:
        logger.warning(f"DNS resolution failed for {hostname}: {e}")
        return []