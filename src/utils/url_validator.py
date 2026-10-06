"""
SSRF Prevention Utility

Validates URLs before server-side requests to prevent Server-Side Request Forgery.
Implements OWASP SSRF Prevention Cheat Sheet recommendations.

Reference: https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
"""

import asyncio
import ipaddress
import socket
import ssl
import time
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import httpcore
import httpx

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


class InvalidURLError(SSRFValidationError):
    """The URL itself is unusable: too long, an unsupported scheme, or no hostname."""


class UnresolvableHostError(SSRFValidationError):
    """The URL's hostname resolves to no address."""


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
        raise InvalidURLError(f"URL exceeds maximum length of {MAX_URL_LENGTH} characters")

    parsed = urlparse(url)

    # Check scheme
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise InvalidURLError(
            f"URL scheme '{parsed.scheme}' is not allowed. Only {ALLOWED_SCHEMES} are permitted."
        )

    # Check hostname exists
    hostname = parsed.hostname
    if not hostname:
        raise InvalidURLError("URL must contain a valid hostname")

    resolved_ips = _checked_addresses(hostname)

    logger.info(
        "URL passed SSRF validation",
        extra={"url_host": hostname, "resolved_ips": resolved_ips},
    )
    return url


def _checked_addresses(hostname: str) -> list[str]:
    """The addresses ``hostname`` stands for, each checked against the blocked ranges.

    A raw IP address is checked as it is; a name is resolved and every address it
    resolves to must be public, in the resolver's order. Raises SSRFValidationError
    otherwise, and UnresolvableHostError when the name resolves to nothing.
    """
    # Only the parse is guarded: SSRFValidationError is itself a ValueError and must
    # not be swallowed here.
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        ip = None  # not a raw IP address: a hostname, resolved below
    if ip is not None:
        _check_ip_blocked(ip)
        return [str(ip)]

    resolved_ips = _resolve_hostname(hostname)
    if not resolved_ips:
        raise UnresolvableHostError(f"Could not resolve hostname: {hostname}")

    for ip_str in resolved_ips:
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            raise SSRFValidationError(f"Invalid IP address from DNS resolution: {ip_str}") from None
        _check_ip_blocked(ip)
    return resolved_ips


def _check_ip_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    """
    Check if an IP address falls within any blocked network range.

    Args:
        ip: The IP address to check.

    Raises:
        SSRFValidationError: If the IP is in a blocked range.
    """
    # Only globally reachable addresses pass: is_global is also false for the
    # special-use ranges the flags below miss, such as shared address space
    # (100.64.0.0/10) and benchmarking (198.18.0.0/15).
    if (
        not ip.is_global
        or ip.is_private
        or ip.is_reserved
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
    ):
        raise SSRFValidationError(
            f"URL resolves to blocked IP address: {ip} "
            f"(global={ip.is_global}, private={ip.is_private}, reserved={ip.is_reserved}, "
            f"loopback={ip.is_loopback}, link_local={ip.is_link_local})"
        )

    for network in BLOCKED_IP_NETWORKS:
        if ip in network:
            raise SSRFValidationError(f"URL resolves to blocked IP range {network}: {ip}")


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
        ips = list(
            dict.fromkeys(info[4][0] for info in addr_info)
        )  # unique, in the resolver's order
        return ips
    except socket.gaierror as e:
        logger.warning(f"DNS resolution failed for {hostname}: {e}")
        return []


# Name lookups of customer-given hosts run on threads of their own. A lookup that
# outlasts its timeout keeps its thread until the system resolver gives up (a
# cancelled await cannot stop it); on the event loop's shared executor, enough of
# them would hold up every other to_thread call. Here they can only hold up lookups.
_LOOKUP_THREADS = ThreadPoolExecutor(max_workers=16, thread_name_prefix="public-dns")


async def _in_lookup_thread(fn: Callable, *args):
    return await asyncio.get_running_loop().run_in_executor(_LOOKUP_THREADS, fn, *args)


async def ensure_public_urls(*urls: str | None) -> None:
    """Raise SSRFValidationError unless every given URL leads to a public address.

    The DNS lookup runs in a thread, so the event loop is not blocked. Empty and
    blank values are skipped.
    """
    for url in urls:
        if url and url.strip():
            await _in_lookup_thread(validate_url_for_ssrf, url.strip())


def refuse_private_addresses() -> Callable[[httpx.Request], Awaitable[None]]:
    """An httpx request hook that refuses every request to a private or reserved address.

    Give it to a client that talks to a customer-given address
    (``event_hooks={"request": [refuse_private_addresses()]}``): each request it
    sends, redirects included, is checked before it leaves, and a host that passed
    once is not looked up again for that client. Re-resolution between the check and
    the connection (DNS rebinding) is covered by PublicOnlyTransport, which
    public_client() adds.
    """
    passed: set[str] = set()

    async def refuse(request: httpx.Request) -> None:
        host = request.url.host
        if host in passed:
            return
        # httpx runs this hook before the transport, so the lookup here is bounded by
        # the request's connect timeout too, and the connection gets what is left of
        # it: one deadline for both lookups, not one each.
        timeouts = request.extensions.get("timeout") or {}
        timeout = timeouts.get("connect")
        started = time.monotonic()
        try:
            await asyncio.wait_for(
                _in_lookup_thread(validate_url_for_ssrf, str(request.url)), timeout
            )
        except TimeoutError:
            raise httpx.ConnectTimeout(
                f"Looking up {host} took over {timeout} s", request=request
            ) from None
        except UnresolvableHostError:
            # A name that does not resolve is a network failure, not a refusal: the
            # connection reports it as one, and a retry may find it.
            return
        passed.add(host)
        if timeout is not None:
            left = timeout - (time.monotonic() - started)
            if left <= 0:
                raise httpx.ConnectTimeout(
                    f"Looking up {host} took over {timeout} s", request=request
                )
            request.extensions = {**request.extensions, "timeout": {**timeouts, "connect": left}}

    return refuse


class _PublicOnlyNetworkBackend(httpcore.AsyncNetworkBackend):
    """Connects to the address it checked, not to a second lookup of the name.

    The request hook checks a host before the request leaves, and the connection
    would look the name up again: a name that answers a public address first and a
    private one next (DNS rebinding) would pass. Here the name is resolved once, every
    address is checked, and the connection goes to the checked address. TLS still
    names the original host, so the certificate is verified against it.
    """

    def __init__(self) -> None:
        self._backend = httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ) -> httpcore.AsyncNetworkStream:
        # The lookup counts against the connect timeout, and a name that does not
        # resolve is a connection error (retryable), not a refusal.
        started = time.monotonic()
        lookup = _in_lookup_thread(_checked_addresses, host)
        try:
            addresses = await asyncio.wait_for(lookup, timeout)
        except TimeoutError:
            raise httpcore.ConnectTimeout(f"Looking up {host} took over {timeout} s") from None
        except UnresolvableHostError:
            raise httpcore.ConnectError(f"Could not resolve host: {host}") from None

        # Every address was checked; try them in the resolver's order, as a
        # connection by name would (an unreachable IPv6 answer falls through).
        failure: Exception | None = None
        for index, address in enumerate(addresses):
            left = None if timeout is None else timeout - (time.monotonic() - started)
            if left is not None and left <= 0:
                raise httpcore.ConnectTimeout(f"Connecting to {host} took over {timeout} s")
            # What is left is shared among the addresses still to try, so a first
            # address that never answers cannot use up the time of a reachable one.
            attempt = None if left is None else left / (len(addresses) - index)
            try:
                return await self._backend.connect_tcp(
                    address,
                    port,
                    timeout=attempt,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                failure = exc
        raise failure

    async def connect_unix_socket(self, path: str, timeout=None, socket_options=None):
        raise SSRFValidationError("A public client does not connect to a local socket")

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


class PublicOnlyTransport(httpx.AsyncHTTPTransport):
    """httpx's transport, with connections only to checked public addresses."""

    def __init__(self, verify: ssl.SSLContext | str | bool = True) -> None:
        super().__init__(verify=verify)
        # httpx 0.28 does not take a network backend; its httpcore pool does. The pool
        # httpx just built is rebuilt with the same TLS context and the client's
        # default limits (100 connections, 20 kept alive), plus the checking backend.
        built = self._pool
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=built._ssl_context,
            max_connections=built._max_connections,
            max_keepalive_connections=built._max_keepalive_connections,
            keepalive_expiry=built._keepalive_expiry,
            network_backend=_PublicOnlyNetworkBackend(),
        )


def public_client(*, verify: ssl.SSLContext | str | bool = True, **kwargs) -> httpx.AsyncClient:
    """An httpx client for an address a customer controls (their site, an image URL).

    Every request, redirects included, is refused before it leaves if its host leads
    to a private or reserved network, and every connection goes only to the public
    address that was checked. A refusal raises SSRFValidationError.
    """
    hooks = kwargs.pop("event_hooks", {})
    hooks = {**hooks, "request": [refuse_private_addresses(), *hooks.get("request", [])]}
    return httpx.AsyncClient(
        transport=PublicOnlyTransport(verify=verify), event_hooks=hooks, **kwargs
    )
