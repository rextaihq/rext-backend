"""Regression tests for the persona-discovery scraping bugs.

Each test pins one confirmed failure that made workspace persona extraction
return empty or wrong results: the page that actually names the humans was
never fetched, so the LLM had nothing real to extract and — correctly, per its
own prompt rules — returned an empty list.
"""
import pytest

from src.utils.fast_scraper import (
    ABOUT_KEYWORDS,
    BLOG_KEYWORDS,
    TEAM_KEYWORDS,
    _find_post_links,
    _matches_keyword,
    _parse_locs,
    _persona_signal_score,
    find_internal_links,
)

BASE = "https://example.com"


def _html(*hrefs: str) -> str:
    links = "".join(f'<a href="{h}">x</a>' for h in hrefs)
    return f"<html><body>{links}</body></html>"


# --------------------------------------------------------------------------
# Bug 1: the about-page budget was spent in DOM order, so a nav bar full of
# product links crowded out the team page sitting further down the document.
# --------------------------------------------------------------------------
def test_team_page_outranks_product_pages_within_budget():
    html = _html(
        "/features/editor", "/features/assets", "/features/database",
        "/features/hooks", "/our-team",
    )
    chosen = find_internal_links(
        html, BASE, ABOUT_KEYWORDS + TEAM_KEYWORDS, 4,
        priority_keywords=TEAM_KEYWORDS,
    )
    assert f"{BASE}/our-team" in chosen


def test_priority_ranking_is_off_by_default():
    """Competitor discovery calls this without priority_keywords and must keep
    its original pure-DOM-order behaviour."""
    html = _html("/features/editor", "/features/assets", "/our-team")
    assert find_internal_links(html, BASE, ABOUT_KEYWORDS + TEAM_KEYWORDS, 2) == [
        f"{BASE}/features/editor", f"{BASE}/features/assets",
    ]


def test_deep_article_url_does_not_hijack_priority_tier():
    """`/showcase/best-email-marketing-services/` matches "service" only as a
    substring of "services" and is three segments deep — it is an article, not
    an about hub, and must not outrank a real team page."""
    html = _html("/showcase/best-email-marketing-services/", "/meet-the-team")
    chosen = find_internal_links(
        html, BASE, ABOUT_KEYWORDS + TEAM_KEYWORDS, 1,
        priority_keywords=TEAM_KEYWORDS,
    )
    assert chosen == [f"{BASE}/meet-the-team"]


# --------------------------------------------------------------------------
# Bug 2: posts were required to live under the blog index path. wpbeginner.com
# indexes at /blog/ but publishes at /beginners-guide/<slug>, so the strict pass
# matched only /blog/page/N pagination and returned zero posts.
# --------------------------------------------------------------------------
def test_posts_found_when_they_live_outside_the_index_path():
    html = _html(
        "/blog/page/2", "/blog/page/3",
        "/beginners-guide/how-to-choose-the-best-blogging-platform/",
        "/showcase/best-wordpress-themes/",
    )
    assert _find_post_links(html, f"{BASE}/blog/", 10) == []
    relaxed = _find_post_links(html, f"{BASE}/blog/", 10, allow_outside_index_path=True)
    assert f"{BASE}/beginners-guide/how-to-choose-the-best-blogging-platform/" in relaxed
    assert f"{BASE}/showcase/best-wordpress-themes/" in relaxed


def test_relaxed_pass_still_rejects_pagination_and_navigation():
    html = _html("/blog/page/2", "/pricing", "/docs", "/how-to-build-a-blog")
    relaxed = _find_post_links(html, f"{BASE}/blog/", 10, allow_outside_index_path=True)
    assert relaxed == [f"{BASE}/how-to-build-a-blog"]


# --------------------------------------------------------------------------
# Bug 3: WordPress/Yoast wraps <loc> in CDATA. The raw capture kept the wrapper,
# so no entry ended in ".xml" (sub-sitemaps never followed) and tldextract read
# every domain as "<![CDATA[https" (every URL discarded as off-domain).
# --------------------------------------------------------------------------
def test_cdata_wrapped_sitemap_locs_are_unwrapped():
    xml = (
        "<sitemapindex>"
        "<sitemap><loc><![CDATA[https://example.com/post-sitemap.xml]]></loc></sitemap>"
        "<sitemap><loc>https://example.com/page-sitemap.xml</loc></sitemap>"
        "</sitemapindex>"
    )
    locs = _parse_locs(xml)
    assert locs == [
        "https://example.com/post-sitemap.xml",
        "https://example.com/page-sitemap.xml",
    ]
    assert all(l.endswith(".xml") for l in locs), "sitemap-index detection depends on this"


# --------------------------------------------------------------------------
# Bug 4: sitemap posts were gated on _persona_signal_score > 0, so a site whose
# slugs are ordinary prose contributed zero posts regardless of budget.
# --------------------------------------------------------------------------
def test_ordinary_slugs_score_zero_and_must_not_be_gated_out():
    ordinary = [f"{BASE}/blog/introducing-nextly", f"{BASE}/blog/why-we-built-nextly"]
    assert all(_persona_signal_score(u) == 0 for u in ordinary)
    signal = f"{BASE}/blog/meet-our-new-ceo"
    assert _persona_signal_score(signal) > 0
    ranked = sorted(ordinary + [signal], key=_persona_signal_score, reverse=True)
    assert ranked[0] == signal, "persona-signal posts still rank first"
    assert len(ranked) == 3, "but ordinary posts still fill the budget"


# --------------------------------------------------------------------------
# Bug 5: "press" is a substring of "wordpress", so on WordPress-adjacent sites
# every /wordpress-hosting/* URL registered as a blog link, filled the blog
# index candidate list, and the real /blog/ was never fetched.
# --------------------------------------------------------------------------
@pytest.mark.parametrize("path", ["/wordpress-hosting/", "/wordpress-hosting/security/"])
def test_wordpress_is_not_a_press_page(path):
    assert not _matches_keyword(path, BLOG_KEYWORDS)


@pytest.mark.parametrize("path", ["/press/", "/press-releases/", "/blog/", "/news/"])
def test_real_blog_and_press_paths_still_match(path):
    assert _matches_keyword(path, BLOG_KEYWORDS)


def test_plural_and_singular_keyword_forms_both_match():
    assert _matches_keyword("/features/editor", ABOUT_KEYWORDS)
    assert _matches_keyword("/feature/editor", ABOUT_KEYWORDS)
    assert _matches_keyword("/our-team", TEAM_KEYWORDS)


def test_blog_index_candidates_exclude_wordpress_marketing_pages():
    html = _html(
        "/wordpress-hosting/", "/wordpress-hosting/security/",
        "/wordpress-hosting/performance/", "/wordpress-hosting/agencies/",
        "/wordpress-hosting/enterprise/", "/blog/",
    )
    candidates = find_internal_links(html, BASE, BLOG_KEYWORDS, 5)
    assert candidates == [f"{BASE}/blog/"]
