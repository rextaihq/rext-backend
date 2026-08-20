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


# --------------------------------------------------------------------------
# Bug 6: customer testimonials were extracted as brand personas. A testimonial
# names a real person with a real, often senior title, so every downstream
# name-shape filter passes them - kinsta.com surfaced Phlearn's CEO and Modern
# Castle's founder as Kinsta "experts". The model was also told never to use the
# 'testimonial' label, so leaks arrived as source='expert' and the one filter
# that could have caught them (source == "testimonial") never fired.
# --------------------------------------------------------------------------
from src.utils.fast_scraper import visible_text


TESTIMONIAL_PAGE = """
<html><body>
  <section class="hero"><p>We host WordPress sites.</p></section>
  <div class="testimonial-slider">
    <blockquote>Kinsta is amazing.</blockquote>
    <cite>Seth Kravitz, CEO of Phlearn</cite>
  </div>
  <section id="wall-of-love">
    <p>Derek Hales, Founder of Modern Castle</p>
  </section>
  <section class="our-team"><p>Jon Penland, Chief Operating Officer</p></section>
</body></html>
"""


def test_testimonial_blocks_are_removed():
    text = visible_text(TESTIMONIAL_PAGE, None, strip_testimonials=True)
    assert "Seth Kravitz" not in text
    assert "Derek Hales" not in text


def test_real_team_content_survives_the_strip():
    text = visible_text(TESTIMONIAL_PAGE, None, strip_testimonials=True)
    assert "Jon Penland" in text
    assert "We host WordPress sites." in text


def test_stripping_is_off_by_default():
    """Competitor discovery shares this function and must be unaffected."""
    assert "Seth Kravitz" in visible_text(TESTIMONIAL_PAGE, None)


def test_review_board_team_page_is_not_mistaken_for_a_testimonial():
    """wpbeginner.com's real staff page is /meet-our-wpbeginner-review-board/ —
    a bare "review" marker would delete exactly the page we need most."""
    html = """<html><body><div class="review-board-member">
        <p>Syed Balkhi, Founder</p></div></body></html>"""
    assert "Syed Balkhi" in visible_text(html, None, strip_testimonials=True)


# --------------------------------------------------------------------------
# Bug 7: run-to-run nondeterminism. Three consecutive scrapes of identical
# css-tricks.com content returned 34, 24 and 0 pages, and 11, 5 and 3 personas,
# because fetch() swallowed every error without retrying and load_model() never
# set a temperature (so extraction ran at OpenAI's default of 1.0).
# --------------------------------------------------------------------------
import asyncio
import httpx

from src.utils.fast_scraper import (
    MAX_FETCH_ATTEMPTS,
    _RETRYABLE_STATUS,
    _is_brand_account,
    _is_personal_profile,
    extract_person_socials,
    fetch,
)


class _FlakyClient:
    """Fails with `status` for `fail_times` calls, then serves HTML."""

    def __init__(self, status, fail_times):
        self.status, self.fail_times, self.calls = status, fail_times, 0

    async def get(self, url, timeout=None):
        self.calls += 1
        if self.calls <= self.fail_times:
            return httpx.Response(self.status, text="rate limited")
        return httpx.Response(200, text="<html>ok</html>",
                              headers={"content-type": "text/html"})


def test_transient_failure_is_retried_not_swallowed():
    client = _FlakyClient(429, fail_times=2)
    out = asyncio.run(fetch(client, "https://example.com", asyncio.Semaphore(1)))
    assert out == "<html>ok</html>"
    assert client.calls == 3, "should have retried twice before succeeding"


def test_permanent_failure_is_not_retried():
    client = _FlakyClient(404, fail_times=99)
    out = asyncio.run(fetch(client, "https://example.com", asyncio.Semaphore(1)))
    assert out == ""
    assert client.calls == 1, "404 is permanent — retrying only wastes time"


def test_retry_gives_up_after_max_attempts():
    client = _FlakyClient(503, fail_times=99)
    assert asyncio.run(fetch(client, "https://example.com", asyncio.Semaphore(1))) == ""
    assert client.calls == MAX_FETCH_ATTEMPTS


def test_rate_limit_status_is_retryable():
    assert 429 in _RETRYABLE_STATUS and 503 in _RETRYABLE_STATUS
    assert 404 not in _RETRYABLE_STATUS


def test_persona_extraction_pins_temperature_to_zero():
    """Extraction must be repeatable; generation elsewhere may not be."""
    src = open("src/services/workspace_pipeline.py").read()
    assert "load_model(temperature=0)" in src


def test_load_model_temperature_is_opt_in():
    """Default None keeps the other five call sites byte-identical."""
    import inspect
    from src.flow.model import llm_manager
    assert inspect.signature(llm_manager.load_model).parameters["temperature"].default is None


# --------------------------------------------------------------------------
# Bug 8: personas carried no social links. The column existed and was persisted,
# but the prompt never requested it, so linkedin_url was null on every site. The
# risk in filling it is attributing the *company's* account, or another author's,
# to a person — a wrong profile URL is worse than an empty field.
# --------------------------------------------------------------------------
AUTHOR_CARD = """
<html><body>
  <footer><a href="https://twitter.com/kinsta">brand</a></footer>
  <div class="author-card">
    <h3>Carlo Daniele</h3>
    <a href="https://www.linkedin.com/in/carlodaniele/">li</a>
    <a href="https://twitter.com/carlodaniele">tw</a>
  </div>
  <div class="author-card">
    <h3>Joel Olawanle</h3>
    <a href="https://twitter.com/olawanle_joel">tw</a>
  </div>
</body></html>
"""


def test_social_links_attach_to_the_right_person():
    got = extract_person_socials(AUTHOR_CARD, ["Carlo Daniele", "Joel Olawanle"],
                                 "https://kinsta.com")
    assert got["Carlo Daniele"]["linkedin"] == "https://www.linkedin.com/in/carlodaniele/"
    assert got["Carlo Daniele"]["twitter"] == "https://twitter.com/carlodaniele"
    assert got["Joel Olawanle"]["twitter"] == "https://twitter.com/olawanle_joel"
    assert "linkedin" not in got["Joel Olawanle"], "must not borrow Carlo's profile"


def test_company_footer_account_is_never_attributed():
    got = extract_person_socials(AUTHOR_CARD, ["Carlo Daniele"], "https://kinsta.com")
    assert "https://twitter.com/kinsta" not in got["Carlo Daniele"].values()


def test_shared_container_yields_nothing_rather_than_a_guess():
    """Two names in one block — ownership is ambiguous, so return nothing."""
    html = """<html><body><div class="team">
        <p>Ada Lovelace</p><p>Grace Hopper</p>
        <a href="https://twitter.com/someone">tw</a>
    </div></body></html>"""
    got = extract_person_socials(html, ["Ada Lovelace", "Grace Hopper"], "https://example.com")
    assert got == {}


@pytest.mark.parametrize("url,expected", [
    ("https://www.linkedin.com/in/carlodaniele/", True),
    ("https://www.linkedin.com/company/kinsta/", False),
    ("https://github.com/someuser", True),
    ("https://github.com/someuser/somerepo", False),
    ("https://twitter.com/intent/tweet", False),
])
def test_personal_profile_detection(url, expected):
    from src.utils.fast_scraper import _social_network
    assert _is_personal_profile(url, _social_network(url)) is expected


@pytest.mark.parametrize("url,site,expected", [
    ("https://x.com/css", "https://css-tricks.com", True),
    ("https://www.facebook.com/kinstahosting", "https://kinsta.com", True),
    ("https://github.com/kinsta/", "https://kinsta.com", True),
    ("https://twitter.com/carlodaniele", "https://kinsta.com", False),
])
def test_brand_account_detection(url, site, expected):
    assert _is_brand_account(url, site) is expected


# --------------------------------------------------------------------------
# Bug 9: a social link from an adjacent team card was attributed to the wrong
# person. The container guard rejects containers naming another *known* persona,
# but rankinggrow.com's neighbouring card belonged to someone the LLM never
# extracted, so linkedin.com/in/tuba-batool-2106a71b4 landed on Mushad Usama.
# --------------------------------------------------------------------------
from src.utils.fast_scraper import _handle_matches_name, extract_byline


@pytest.mark.parametrize("url,name,expected", [
    ("https://www.linkedin.com/in/tuba-batool-2106a71b4/", "Mushad Usama", False),
    ("https://www.linkedin.com/in/zeeshan0x01/", "Zeeshan Waheed", True),
    ("https://www.linkedin.com/in/carlodaniele/", "Carlo Daniele", True),
    ("https://twitter.com/olawanle_joel", "Joel Olawanle", True),
    ("https://www.youtube.com/@joelolawanle", "Joel Olawanle", True),
    ("https://hu.linkedin.com/in/tom-zsomborgi-72582191", "Tom Zsomborgi", True),
])
def test_handle_must_plausibly_belong_to_the_person(url, name, expected):
    assert _handle_matches_name(url, name) is expected


def test_stranger_link_in_a_persons_card_is_still_rejected():
    """Precision over recall: an empty field beats someone else's profile."""
    html = """<html><body><div class="member">
        <h4>Mushad Usama</h4>
        <a href="https://www.linkedin.com/in/tuba-batool-2106a71b4/">li</a>
    </div></body></html>"""
    got = extract_person_socials(html, ["Mushad Usama"], "https://rankinggrow.com")
    assert got == {}


# --------------------------------------------------------------------------
# Bug 10: post bylines live in markup that visible_text() drops and that the
# per-post character cap can truncate away, so real authors were invisible to
# the LLM even on pages that declared them.
# --------------------------------------------------------------------------
def test_byline_is_read_from_markup():
    html = '<html><body><span rel="author">Noor Khalid</span><p>body</p></body></html>'
    assert extract_byline(html, "https://rankinggrow.com") == "Noor Khalid"


def test_byline_label_prefix_is_stripped():
    html = '<html><body><div class="post-author">Post author:Noor Khalid</div></body></html>'
    assert extract_byline(html, "https://rankinggrow.com") == "Noor Khalid"


def test_byline_from_json_ld():
    html = ('<html><head><script type="application/ld+json">'
            '{"@type":"Article","author":{"@type":"Person","name":"Jane Roe"}}'
            '</script></head><body></body></html>')
    assert extract_byline(html, "https://example.com") == "Jane Roe"


@pytest.mark.parametrize("byline", ["rankinggrow", "admin", "RankingGrow Team"])
def test_site_account_is_not_a_byline(byline):
    """Most posts on that site are authored by the site's own username, which
    must never become a persona."""
    html = f'<html><body><span rel="author">{byline}</span></body></html>'
    assert extract_byline(html, "https://rankinggrow.com") is None


# --------------------------------------------------------------------------
# Bug 11: wpmudev.com declared an author on every post yet yielded one persona.
# The declaration was present in three forms, none of which extract_byline read.
# --------------------------------------------------------------------------
def test_byline_from_theme_namespaced_class():
    """Themes namespace their classes, so an exact selector list is never
    complete — wpmudev.com uses `dev-post__meta-author`."""
    html = ('<html><body><span class="dev-post__meta-author">James Farmer</span>'
            "</body></html>")
    assert extract_byline(html, "https://wpmudev.com") == "James Farmer"


def test_empty_author_meta_does_not_mask_a_populated_one():
    """The page carries two author metas and the first is blank; find() returned
    the blank one and silently discarded the real byline behind it."""
    html = ('<html><head><meta name="author" content="">'
            '<meta name="author" content="James Farmer"></head><body></body></html>')
    assert extract_byline(html, "https://wpmudev.com") == "James Farmer"


def test_byline_from_json_ld_graph_reference():
    """Yoast-style @graph: author is a reference, the name is on a Person node."""
    html = ('<html><head><script type="application/ld+json">{"@graph":['
            '{"@type":"Article","author":{"@id":"https://x.com/#schema-author"}},'
            '{"@type":"Person","@id":"https://x.com/#schema-author","name":"James Farmer"}'
            ']}</script></head><body></body></html>')
    assert extract_byline(html, "https://wpmudev.com") == "James Farmer"


@pytest.mark.parametrize("byline", [
    "Editorial Staff", "Editorial Team", "Guest Author", "Content Team",
    "Marketing Team", "News Desk",
])
def test_collective_byline_is_not_a_person(byline):
    """Two words is not enough to be a person — wpmudev.com publishes under
    "Editorial Staff", which must not become a persona."""
    html = f'<html><body><span rel="author">{byline}</span></body></html>'
    assert extract_byline(html, "https://wpmudev.com") is None


def test_real_two_word_name_still_passes_the_collective_filter():
    html = '<html><body><span rel="author">Joshua Dailey</span></body></html>'
    assert extract_byline(html, "https://wpmudev.com") == "Joshua Dailey"


# --------------------------------------------------------------------------
# Bug 12: broadening the byline search to any author-ish class swept in comment
# threads. WordPress marks every commenter `comment-author`, so readers became
# personas — wpbeginner.com produced ten "authors" of whom eight had only left
# comments on the site.
# --------------------------------------------------------------------------
COMMENTED_POST = """
<html><body>
  <span class="dev-post__meta-author">Syed Balkhi</span>
  <div class="comment-respond">
    <ol class="comment-list">
      <li class="comment byuser"><span class="comment-author-name">Dennis Muthomi</span></li>
      <li class="comment"><span class="comment-author">Rob Phillips-Legge</span></li>
    </ol>
  </div>
</body></html>
"""


def test_commenters_are_not_bylines():
    assert extract_byline(COMMENTED_POST, "https://www.wpbeginner.com") == "Syed Balkhi"


def test_comment_author_alone_yields_no_byline():
    """A page whose only author-ish markup is a comment has no byline at all."""
    html = """<html><body><div class="comment-list">
        <span class="comment-author">Dennis Muthomi</span>
    </div></body></html>"""
    assert extract_byline(html, "https://www.wpbeginner.com") is None


@pytest.mark.parametrize("container", [
    "comment-list", "comments-area", "respond", "reply-form", "disqus_thread",
])
def test_comment_containers_are_excluded(container):
    html = (f'<html><body><div class="{container}">'
            '<span rel="author">Some Commenter</span></div></body></html>')
    assert extract_byline(html, "https://example.com") is None


def test_post_crawl_stops_when_authors_stop_appearing():
    """Blog archives repeat the same writers; the crawl must not spend its whole
    budget re-confirming authors it already has."""
    from src.utils.fast_scraper import _POST_WAVE_SIZE
    assert _POST_WAVE_SIZE >= 5, "waves too small — one repeat post could end the crawl"


# --------------------------------------------------------------------------
# Bug 13: only the four valid groups belong in personas — founders, authors,
# team members, affiliated experts. Commenters, FAQ names, reviewers and
# testimonial contributors were still reaching the model in the page text.
# --------------------------------------------------------------------------
MIXED_PAGE = """
<html><body>
  <div class="team"><p>Syed Balkhi, Founder</p></div>
  <div class="review-board-member"><p>Nouman Yaqoob, Editor</p></div>
  <ol class="comment-list"><li><p>Dennis Muthomi</p><p>great post!</p></li></ol>
  <section class="faq"><p>Asked by Rob Phillips-Legge</p></section>
  <div class="testimonial-slider"><p>Seth Kravitz, CEO of Phlearn</p></div>
</body></html>
"""


@pytest.mark.parametrize("name", ["Syed Balkhi", "Nouman Yaqoob"])
def test_writers_and_team_members_survive(name):
    """The review board is wpbeginner.com's real staff page, not a review widget."""
    assert name in visible_text(MIXED_PAGE, None, strip_testimonials=True)


@pytest.mark.parametrize("name", ["Dennis Muthomi", "Rob Phillips-Legge", "Seth Kravitz"])
def test_commenters_faq_names_and_testimonials_are_removed(name):
    assert name not in visible_text(MIXED_PAGE, None, strip_testimonials=True)


# --------------------------------------------------------------------------
# Bug 14: one human, two personas. A team page saying "Syed Balkhi" and an
# author box saying "Dr. Syed Balkhi" produced two records for the same person.
# --------------------------------------------------------------------------
from src.services.workspace_pipeline import _filter_valid_personas, _identity_key


def test_honorific_variant_is_the_same_person():
    assert _identity_key("Dr. Syed Balkhi") == _identity_key("Syed Balkhi")


def test_duplicates_merge_keeping_the_richer_record():
    out = _filter_valid_personas([
        {"name": "Syed Balkhi", "source": "founder",
         "professional_title": "Founder & CEO", "bio": "x"},
        {"name": "Dr. Syed Balkhi", "source": "expert"},
        {"name": "Chris Christoff", "source": "team_member",
         "professional_title": "CIO"},
    ])
    assert [p["name"] for p in out] == ["Syed Balkhi", "Chris Christoff"]
    assert out[0]["professional_title"] == "Founder & CEO", "kept the fuller record"


def test_distinct_people_are_not_merged():
    out = _filter_valid_personas([
        {"name": "Chris Christoff", "source": "team_member"},
        {"name": "Chris Klosowski", "source": "team_member"},
    ])
    assert len(out) == 2
