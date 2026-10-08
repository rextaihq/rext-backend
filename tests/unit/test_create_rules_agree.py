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
async def test_a_site_that_refuses_the_connection_is_still_refused(site):
    site["resolves"].add("tea.example.com")
    site["answer"] = httpx.ConnectError("refused")

    with pytest.raises(WebsiteUnreachableError, match="couldn't reach"):
        await check_website_reachable("https://tea.example.com/")
