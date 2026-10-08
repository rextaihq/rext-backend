"""The create form and the backend agree on a workspace's name and website (revnix/rext-control#881).

On launch day the backend refused names the form had accepted ("Tom’s Bakery" as a phone types it,
"Acme (UK)", "Acme: Blog"), and told a site that answers only at `www.` that it "does not exist".
"""

import httpx
import pytest

from src.api.middleware.exceptions import RextValidationException
from src.utils import fast_scraper
from src.utils.fast_scraper import WebsiteUnreachableError, check_website_reachable
from src.utils.name_utils import validate_workspace_name
from src.utils.url_validator import SSRFValidationError

# The name


@pytest.mark.parametrize(
    "name",
    [
        "Tom’s Bakery",  # the apostrophe a phone keyboard types
        "Tom's Bakery",
        "Acme (UK)",
        "Acme: Blog",
        "Acme | Blog",
        "Acme – Co",
        "Acme — Co",
        "Acme!",
        "Is it Acme?",
        "“Acme” Studio",
        "#1 Plumber",
        "Acme & Sons, Inc.",
        "Café Zoë",
        "Acme™",
        "X",
    ],
)
def test_the_names_people_type_are_accepted(name):
    assert validate_workspace_name(f"  {name} ") == name


@pytest.mark.parametrize(
    ("name", "says"),
    [
        ("<b>Acme</b>", None),
        ("Acme {x}", "ordinary punctuation"),
        ("Acme\x07", "control characters"),
        ("2024", "at least one letter"),
        ("   ", "required"),
    ],
)
def test_what_is_not_a_name_is_refused_beside_the_field(name, says):
    with pytest.raises(RextValidationException) as refused:
        validate_workspace_name(name)

    details = refused.value.details
    assert [detail["field"] for detail in details] == ["name"]
    if says:
        assert says in details[0]["message"]


# The website


@pytest.fixture
def site(monkeypatch):
    """A site whose only resolving hosts are `resolves`: what was looked up, what was fetched,
    and how the fetch answers."""
    seen = {"resolves": set(), "looked_up": [], "fetched": [], "answer": None}

    def look_up(url):
        host = httpx.URL(url).host
        seen["looked_up"].append(host)
        if host not in seen["resolves"]:
            raise SSRFValidationError(f"Could not resolve hostname: {host}")

    def respond(request):
        seen["fetched"].append(str(request.url))
        if seen["answer"] is not None:
            raise seen["answer"]
        return httpx.Response(200, content=b"<html><body><h1>We sell tea.</h1></body></html>")

    monkeypatch.setattr(fast_scraper, "validate_url_for_ssrf", look_up)
    monkeypatch.setattr(
        fast_scraper,
        "public_client",
        lambda **kwargs: httpx.AsyncClient(
            transport=httpx.MockTransport(respond), follow_redirects=True
        ),
    )
    return seen


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("typed", "resolves", "kept"),
    [
        ("https://tea.example.com/", "www.tea.example.com", "https://www.tea.example.com/"),
        ("https://www.tea.example.com/shop", "tea.example.com", "https://tea.example.com/shop"),
        ("https://tea.example.com/", "tea.example.com", "https://tea.example.com/"),
    ],
)
async def test_a_site_is_tried_at_its_www_twin_and_kept_where_it_answers(
    site, typed, resolves, kept
):
    site["resolves"].add(resolves)

    assert await check_website_reachable(typed) == kept
    assert site["fetched"] == [kept]


@pytest.mark.asyncio
async def test_a_site_at_neither_address_does_not_exist(site):
    with pytest.raises(WebsiteUnreachableError, match="does not exist"):
        await check_website_reachable("https://tea.example.com/")

    assert site["looked_up"] == ["tea.example.com", "www.tea.example.com"]
    assert site["fetched"] == []


@pytest.mark.asyncio
async def test_a_site_that_keeps_us_waiting_is_let_through(site):
    site["resolves"].add("tea.example.com")
    site["answer"] = httpx.ReadTimeout("still waiting")

    # It is somebody's site: the workspace is created, and the read that follows has its own
    # patience and its own words.
    assert await check_website_reachable("https://tea.example.com/") == "https://tea.example.com/"


@pytest.mark.asyncio
async def test_a_parking_page_that_stalls_is_still_a_parking_page(site, monkeypatch):
    site["resolves"].add("tea.example.com")

    class _Stalls(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"<html><body>This domain is for sale. Buy this domain today.</body></html>"
            raise httpx.ReadTimeout("still waiting")

    monkeypatch.setattr(
        fast_scraper,
        "public_client",
        lambda **kwargs: httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=_Stalls())),
            follow_redirects=True,
        ),
    )

    # What it sent before it stalled already says what it is.
    with pytest.raises(WebsiteUnreachableError, match="parked or for sale"):
        await check_website_reachable("https://tea.example.com/")


@pytest.mark.asyncio
async def test_a_slow_sites_address_is_logged_without_what_it_carries(site, caplog):
    site["resolves"].add("tea.example.com")
    site["answer"] = httpx.ReadTimeout("still waiting")

    with caplog.at_level("INFO"):
        await check_website_reachable("https://tea.example.com/in?token=s3cret#part")

    assert "s3cret" not in caplog.text


@pytest.mark.asyncio
async def test_a_parking_marketplace_that_stalls_before_answering_is_still_refused(
    site, monkeypatch
):
    site["resolves"].add("tea.example.com")

    def respond(request):
        if request.url.host == "tea.example.com":
            return httpx.Response(302, headers={"location": "https://sedoparking.com/tea"})
        raise httpx.ReadTimeout("still waiting", request=request)

    monkeypatch.setattr(
        fast_scraper,
        "public_client",
        lambda **kwargs: httpx.AsyncClient(
            transport=httpx.MockTransport(respond), follow_redirects=True
        ),
    )

    with pytest.raises(WebsiteUnreachableError, match="parked or for sale"):
        await check_website_reachable("https://tea.example.com/")


@pytest.mark.asyncio
async def test_a_failed_check_is_logged_without_what_the_address_carries(site, caplog):
    site["resolves"].add("tea.example.com")
    site["answer"] = httpx.ConnectError("refused")

    with caplog.at_level("INFO"), pytest.raises(WebsiteUnreachableError):
        await check_website_reachable("https://user:s3cret@tea.example.com/in?token=t0ken")

    assert "s3cret" not in caplog.text and "t0ken" not in caplog.text


@pytest.mark.asyncio
async def test_a_site_where_no_server_answers_is_still_refused(site):
    site["resolves"].add("tea.example.com")
    site["answer"] = httpx.ConnectTimeout("nobody there")

    with pytest.raises(WebsiteUnreachableError, match="not responding"):
        await check_website_reachable("https://tea.example.com/")


def test_the_twin_keeps_what_came_before_the_host():
    twin = fast_scraper._www_twin("https://user:pass@tea.example.com:8443/shop?x=1")

    assert twin == "https://user:pass@www.tea.example.com:8443/shop?x=1"
    assert fast_scraper._www_twin("https://www.tea.example.com/") == "https://tea.example.com/"


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Acme (UK)", "acme-uk"),
        ("Tom’s Bakery", "toms-bakery"),
        ("Café Zoë", "cafe-zoe"),
        ("É", "e"),
        ("茶", "workspace"),
        ("茶屋 2", "2"),
    ],
)
def test_every_accepted_name_has_an_address(name, slug):
    from src.services.workspace_service import WorkspaceService

    assert WorkspaceService(None)._slugify(validate_workspace_name(name)) == slug


@pytest.mark.asyncio
async def test_a_site_that_refuses_the_connection_is_still_refused(site):
    site["resolves"].add("tea.example.com")
    site["answer"] = httpx.ConnectError("refused")

    with pytest.raises(WebsiteUnreachableError, match="couldn't reach"):
        await check_website_reachable("https://tea.example.com/")
