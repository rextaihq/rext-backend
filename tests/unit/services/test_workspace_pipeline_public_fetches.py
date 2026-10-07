"""A workspace's site is read through the public-only client (G84, rext-control #654).

Besides the scrape, the pipeline fetches pages the site leads to: its homepage for feeds, author
archives under its address, and articles its pages link to. Each goes through public_client(),
which connects only to an address it checked, so a page on this machine is refused, never read.
"""

import http.server
import socketserver
import threading
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.services.workspace_pipeline import WorkspacePipeline


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    hits = 0


class _Page(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (http.server's name)
        self.server.hits += 1
        body = b"<html><body>a page on this machine</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_HEAD = do_GET

    def log_message(self, *args):
        pass


@pytest.fixture
def local_site():
    server = _Server(("127.0.0.1", 0), _Page)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server, f"http://127.0.0.1:{server.server_address[1]}/"
    server.shutdown()
    server.server_close()


def _pipeline(url: str) -> WorkspacePipeline:
    return WorkspacePipeline(
        db=AsyncMock(),
        operation_id="op-g84",
        workspace_id=uuid4(),
        user_id=uuid4(),
        url=url,
        scraper=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_an_article_link_to_this_machine_is_refused_not_read(local_site):
    server, address = local_site

    assert await _pipeline("https://example.com")._fetch_credited_articles([address]) == {}
    assert server.hits == 0


@pytest.mark.asyncio
async def test_the_homepage_for_feeds_is_not_read_from_this_machine(local_site, monkeypatch):
    server, address = local_site
    discover = AsyncMock(return_value={})
    monkeypatch.setattr("src.utils.fast_scraper.discover_feed_authors", discover)

    assert await _pipeline(address)._feed_attempt() == {}
    assert server.hits == 0
    # Feed discovery still runs, on an empty homepage.
    assert discover.await_args.args[2] == ""


@pytest.mark.asyncio
async def test_author_archives_under_this_machine_are_not_read(local_site):
    server, address = local_site
    pipeline = _pipeline(address)

    await pipeline._fetch_missing_author_archives([{"name": "Jane Doe"}])

    assert server.hits == 0
    assert not getattr(pipeline, "_page_text_by_url", {})
