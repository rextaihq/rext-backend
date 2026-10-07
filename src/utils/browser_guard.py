"""The public-only rule for the headless browser (G88, revnix/rext-control#661).

The browser fallback renders a customer's page in Chromium, which fetches whatever the page
names: the page itself, its redirects, frames, scripts, workers and sockets. The browser is
launched with PublicOnlyProxy as its proxy, so every connection it opens goes through one place:
the proxy resolves the host once, checks every address it resolves to, and connects only to a
checked public address, as public_client() does for httpx. A request to anything else is
answered 403 and never leaves.

Chromium keeps its own network stack: redirects, cookies and TLS work as they do without the
proxy, and every hop of a redirect is a new request through the proxy. An https or wss
connection is a CONNECT tunnel, so TLS stays between the browser and the site.
"""

import asyncio
import time
from urllib.parse import urlsplit

from src.api.lib.logger import auto_logger
from src.utils import url_validator
from src.utils.url_validator import SSRFValidationError

logger = auto_logger()

_HEAD_TIMEOUT_SECONDS = 30.0
_CONNECT_TIMEOUT_SECONDS = 15.0
_HEAD_LIMIT_BYTES = 64 * 1024
_CHUNK_BYTES = 64 * 1024
# A plain http request is forwarded on a connection of its own; the browser opens the next.
_HOP_BY_HOP = (b"proxy-connection:", b"proxy-authorization:", b"connection:", b"keep-alive:")
PROXY_BROWSER_ARGS = [
    # Chromium sends loopback addresses past a proxy unless told otherwise.
    "--proxy-bypass-list=<-loopback>",
    # WebRTC may otherwise send UDP on its own, outside any proxy.
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
]


def _host_port(authority: str, default_port: int) -> tuple[str, int]:
    """'host:port' or '[v6]:port' from a CONNECT line."""
    parts = urlsplit(f"//{authority}")
    if not parts.hostname:
        raise ValueError(f"no host in {authority!r}")
    return parts.hostname, parts.port or default_port


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while chunk := await reader.read(_CHUNK_BYTES):
            writer.write(chunk)
            await writer.drain()
    except (ConnectionError, OSError):
        pass
    finally:
        if not writer.is_closing():
            writer.close()


async def _connect_checked(host: str, port: int):
    """Open a connection to a checked public address of ``host``. Raises SSRFValidationError
    when any address it resolves to isn't public; nothing is sent then. The lookup and every
    address tried share one deadline, as public_client()'s connections do."""
    deadline = time.monotonic() + _CONNECT_TIMEOUT_SECONDS
    # On url_validator's own lookup threads: a stalled lookup can't hold up other work.
    addresses = await asyncio.wait_for(
        url_validator._in_lookup_thread(url_validator._checked_addresses, host),
        _CONNECT_TIMEOUT_SECONDS,
    )
    failure: Exception = OSError(f"no address to connect to for {host}")
    for index, address in enumerate(addresses):
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError(f"connecting to {host} took over {_CONNECT_TIMEOUT_SECONDS} s")
        # What is left is shared among the addresses still to try, so an address that never
        # answers can't use up the time of one that would.
        try:
            return await asyncio.wait_for(
                asyncio.open_connection(address, port), left / (len(addresses) - index)
            )
        except (OSError, TimeoutError) as exc:
            failure = exc
    raise failure


class PublicOnlyProxy:
    """An HTTP proxy on 127.0.0.1 for one browser session, closed with ``async with``."""

    def __init__(self) -> None:
        self._server: asyncio.base_events.Server | None = None
        # Each connection's handler, so closing the proxy ends them all, including one still
        # looking up or connecting.
        self._handlers: set[asyncio.Task] = set()
        self.url = ""

    async def __aenter__(self) -> "PublicOnlyProxy":
        self._server = await asyncio.start_server(
            self._handle, "127.0.0.1", 0, limit=_HEAD_LIMIT_BYTES
        )
        port = self._server.sockets[0].getsockname()[1]
        self.url = f"http://127.0.0.1:{port}"
        return self

    async def __aexit__(self, *exc) -> None:
        self._server.close()
        handlers = list(self._handlers)
        for handler in handlers:
            handler.cancel()
        await asyncio.gather(*handlers, return_exceptions=True)
        await self._server.wait_closed()

    async def _answer(self, writer: asyncio.StreamWriter, status: str) -> None:
        writer.write(
            f"HTTP/1.1 {status}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".encode()
        )
        await writer.drain()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        handler = asyncio.current_task()
        self._handlers.add(handler)
        upstream: asyncio.StreamWriter | None = None
        try:
            try:
                head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), _HEAD_TIMEOUT_SECONDS)
            except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, TimeoutError):
                return
            request_line, _, header_block = head.partition(b"\r\n")
            try:
                method, target, version = request_line.decode("latin-1").split(" ", 2)
                if method.upper() == "CONNECT":
                    host, port = _host_port(target, 443)
                    forward = b""
                else:
                    parts = urlsplit(target)
                    if parts.scheme.lower() != "http" or not parts.hostname:
                        raise ValueError(f"not an absolute http address: {target!r}")
                    host, port = parts.hostname, parts.port or 80
                    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
                    headers = [
                        line
                        for line in header_block.split(b"\r\n")
                        if line and not line.lower().startswith(_HOP_BY_HOP)
                    ]
                    forward = b"\r\n".join(
                        [f"{method} {path} {version}".encode("latin-1"), *headers]
                    )
                    forward += b"\r\nConnection: close\r\n\r\n"
            except ValueError:
                await self._answer(writer, "400 Bad Request")
                return
            try:
                upstream_reader, upstream = await _connect_checked(host, port)
            except SSRFValidationError as exc:
                logger.warning(
                    "Browser request refused", extra={"host": host, "reason": type(exc).__name__}
                )
                await self._answer(writer, "403 Forbidden")
                return
            except (OSError, TimeoutError):
                await self._answer(writer, "502 Bad Gateway")
                return
            if forward:
                upstream.write(forward)
            else:
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
            await asyncio.gather(_pipe(reader, upstream), _pipe(upstream_reader, writer))
        except (ConnectionError, OSError):
            pass
        finally:
            for stream in (upstream, writer):
                if stream is not None and not stream.is_closing():
                    stream.close()
            self._handlers.discard(handler)
