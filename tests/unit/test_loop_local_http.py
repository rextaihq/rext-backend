"""Runs on their own event loops never share a pooled connection (G80, rext-control #644).

LangGraph runs each background job on its own event loop, and every chat model shared one
cached httpx client: under load, a run waited on an asyncio Event bound to another run's loop,
reused a connection whose loop had closed, or stalled. The shared client now keeps one
connection pool per event loop.
"""

import asyncio
import http.server
import socketserver
import threading
import time
from collections import Counter

import pytest

from src.utils.loop_local_http import SHARED_ASYNC_CLIENT, loop_local_async_client


class _SlowHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):  # noqa: N802 (http.server's name)
        time.sleep(0.02)
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


@pytest.fixture
def local_url():
    server = _Server(("127.0.0.1", 0), _SlowHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/"
    server.shutdown()


def test_concurrent_runs_on_their_own_loops_share_the_client_safely(local_url):
    """Three "runs", each on its own event loop in its own thread as LangGraph runs them, send
    overlapping requests through one client: none fails or stalls, and none finds another loop's
    connection (a plain shared client failed this with the load test's error)."""
    client = loop_local_async_client()
    errors: Counter = Counter()
    batches: Counter = Counter()

    def run(name: str) -> None:
        async def main() -> None:
            for _ in range(8):
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*(client.get(local_url, timeout=3) for _ in range(5))),
                        timeout=4,
                    )
                    batches[name] += 1
                except Exception as error:  # noqa: BLE001 (counted and asserted below)
                    errors[f"{type(error).__name__}: {error}"] += 1

        asyncio.run(main())

    threads = [threading.Thread(target=run, args=(f"run{i}",)) for i in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors, dict(errors)
    assert dict(batches) == {"run0": 8, "run1": 8, "run2": 8}


def test_each_loop_gets_its_own_pool_and_a_closed_loop_lets_it_go(local_url):
    client = loop_local_async_client()
    transport = client._transport

    async def one_request() -> int:
        assert (await client.get(local_url, timeout=3)).status_code == 200
        return len(transport._pools)

    assert asyncio.run(one_request()) == 1
    # A new run on a new loop: the first loop has closed, so its pool is gone.
    assert asyncio.run(one_request()) == 1
    assert asyncio.run(one_request()) == 1


def test_every_chat_model_and_the_competitors_client_use_the_shared_client(monkeypatch):
    from src.flow.model import llm_manager

    monkeypatch.setattr(llm_manager.settings, "OPENAI_API_KEY", "sk-test", raising=False)
    for build in (
        llm_manager.load_model,
        llm_manager.load_content_model,
        llm_manager.load_luna_content_model,
        llm_manager.load_humanize_model,
        llm_manager.topic_generation_model,
    ):
        assert build().http_async_client is SHARED_ASYNC_CLIENT, build.__name__

    from src.flow.engines.competitors import llm_client

    assert llm_client._client._client is SHARED_ASYNC_CLIENT
