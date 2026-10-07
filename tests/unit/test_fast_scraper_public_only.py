"""The site scraper never reaches a private or reserved network (G86, rext-control #659).

The reachability check at workspace creation and the scrape itself go through public_client():
each request, redirects included, is checked before it is sent, and a connection goes only to the
address that was checked. A site that redirects inward is refused, and nothing is sent there.
"""

import httpx
import pytest

from src.utils import url_validator
from src.utils.fast_scraper import WebsiteUnreachableError, check_website_reachable, scrape_site

PUBLIC = "http://93.184.216.34/"
PRIVATE_REDIRECTS = [
    "http://127.0.0.1:8000/admin",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.5/",
]
HOME = b"<html><head><title>A shop</title></head><body><h1>Welcome</h1><p>We sell tea.</p></body></html>"


class _Sent(list):
    """The URLs the mock transport was asked to send, and where it redirects the public host."""

    def __init__(self) -> None:
        super().__init__()
        self.target: dict[str, str] = {}
        self.verify: list[object] = []


@pytest.fixture
def sent(monkeypatch) -> _Sent:
    """Every public client gets a mock transport: the public host redirects to the test's
    `redirect_to` if it has one, else answers with a small homepage."""
    requests = _Sent()

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if "redirect_to" in requests.target and request.url.host == "93.184.216.34":
            return httpx.Response(302, headers={"location": requests.target["redirect_to"]})
        return httpx.Response(200, content=HOME, headers={"content-type": "text/html"})

    def transport(verify=True):
        requests.verify.append(verify)
        return httpx.MockTransport(respond)

    monkeypatch.setattr(url_validator, "PublicOnlyTransport", transport)
    return requests


@pytest.mark.asyncio
@pytest.mark.parametrize("private", PRIVATE_REDIRECTS)
async def test_the_reachability_check_refuses_a_redirect_to_a_private_address(sent, private):
    sent.target["redirect_to"] = private

    with pytest.raises(WebsiteUnreachableError, match="not allowed"):
        await check_website_reachable(PUBLIC)

    assert private not in sent
    assert sent == [PUBLIC]


@pytest.mark.asyncio
async def test_a_reachable_site_still_passes_the_check(sent):
    await check_website_reachable(PUBLIC)

    assert sent == [PUBLIC]


@pytest.mark.asyncio
@pytest.mark.parametrize("private", PRIVATE_REDIRECTS)
async def test_the_scrape_never_follows_the_homepage_to_a_private_address(sent, private):
    sent.target["redirect_to"] = private

    result = await scrape_site(PUBLIC, budget_seconds=5)

    assert private not in sent
    assert not result.get("pages")


@pytest.mark.asyncio
async def test_the_scrape_checks_certificates_and_reads_a_public_site(sent):
    result = await scrape_site(PUBLIC, budget_seconds=5)

    assert sent and sent[0] == PUBLIC
    assert result.get("raw_home_html", "").startswith("<html>")
    # The scrape's client verifies certificates; only the reachability check doesn't.
    assert sent.verify == [True]
