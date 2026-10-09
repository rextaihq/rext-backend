"""The outline is planned for the workspace's reader and offer, with the intent shaping it (FB2.17,
revnix/rext-control#698; the founder's option A). It used only the brand name and competitors."""

import pytest

import src.flow.engines.content.generation.outline as outline_module
from src.flow.engines.content.generation.outline import (
    _format_reader_and_offer,
    _profile_list,
    _profile_text,
)
from src.flow.model.provider_outage import ProviderUnavailable

PROFILE = {
    "customer_profile": "Marketing leads at 10–50 person B2B SaaS teams who publish weekly.",
    "target_audience": ["Content marketers", "SEO specialists"],
    "about": "Rext AI writes SEO articles that show their work.",
    "selling_position": "Researched, cited drafts in your brand voice, published to WordPress.",
    "content_pillars": ["SEO content", "Content operations"],
}


def test_the_reader_and_the_offer_are_shown_apart():
    block = _format_reader_and_offer(PROFILE)

    reader, offer = block.split("WHAT THE BRAND OFFERS:")
    assert reader.startswith("WHO THE SITE SERVES:")
    assert "Customer profile: Marketing leads at 10–50 person B2B SaaS teams" in reader
    assert "Audiences: Content marketers; SEO specialists" in reader
    assert "About: Rext AI writes SEO articles" in offer
    assert "What it offers: Researched, cited drafts" in offer
    assert "Content pillars: SEO content; Content operations" in offer


def test_an_empty_profile_says_so():
    assert _format_reader_and_offer({}) == "None available."
    assert _format_reader_and_offer({"about": ""}) == "None available."


def test_only_the_parts_known_are_shown():
    block = _format_reader_and_offer({"about": "A garden shop."})

    assert block == "WHAT THE BRAND OFFERS:\n- About: A garden shop."


def test_profile_lists_take_strings_and_objects_and_stay_short():
    items = _profile_list(
        ["Founders", {"name": "Marketers", "description": "run the blog"}, "", 42, *"abcdefgh"]
    )

    assert items[:3] == ["Founders", "Marketers — run the blog", "42"]
    assert len(items) == 6
    assert _profile_list("not a list") == []


def test_long_profile_text_is_clipped():
    text = _profile_text("word " * 400)

    assert len(text) <= 500 and text.endswith("…")


@pytest.fixture
def outline_prompt(monkeypatch):
    """The human message generate_outline sends, with the workspace profile given."""
    sent = []

    class _Stop(Exception):
        pass

    class _Model:
        def with_structured_output(self, _schema):
            return self

        async def ainvoke(self, messages):
            sent.extend(messages)
            raise _Stop

    async def entities(_workspace_id):
        return "Rext AI", ["surferseo.com"]

    async def nothing(_workspace_id):
        return None

    monkeypatch.setattr(outline_module, "load_model", lambda **_kw: _Model())
    monkeypatch.setattr(outline_module, "_fetch_known_entities", entities)
    monkeypatch.setattr(outline_module, "_bulk_sync_workspace", nothing)
    monkeypatch.setattr(outline_module, "resolve_focus_keyword", lambda _state: "seo content brief")
    monkeypatch.setattr(
        outline_module, "build_cluster_heading_map", lambda **_kw: {"enabled": False}
    )

    async def go(profile):
        async def fetch_profile(_workspace_id):
            return profile

        monkeypatch.setattr(outline_module, "_fetch_workspace_profile", fetch_profile)
        sent.clear()
        # Stopped at the model call: an outline that fails ends the run (rext-control#697).
        with pytest.raises(ProviderUnavailable):
            await outline_module.generate_outline.__wrapped__(
                {
                    "serp_payload": {"workspace_id": None},
                    "seo_result": {"serp_backlinks": {"main_intent": "Commercial"}},
                    "content": {
                        "selected_topic": "How to choose an SEO content brief tool",
                        "content_type": "blog",
                        "outline": {},
                    },
                }
            )
        return sent[1].content

    return go


@pytest.mark.unit
async def test_the_outline_is_planned_for_the_workspaces_reader_and_offer(outline_prompt):
    human = await outline_prompt(PROFILE)

    assert "The Workspace's Customers and Offer" in human
    assert "Customer profile: Marketing leads at 10–50 person B2B SaaS teams" in human
    assert "What it offers: Researched, cited drafts" in human
    # The reader is the searcher, narrowed toward the site's customers where the subject is
    # the site's own; never their list copied.
    assert "12. WRITE FOR THE PERSON SEARCHING THIS KEYWORD:" in human
    assert "WHO THE SITE SERVES:\n" in human
    assert "the reader is whoever types the Focus Keyword above" in human
    # The keyword itself is stated: a title the user wrote may not contain it.
    assert (
        "Focus Keyword (what the reader typed into the search engine):\nseo content brief" in human
    )
    assert "`target_audience` names the searcher in the keyword's own terms" in human
    assert "Never copy the site's customer list into `target_audience`" in human
    assert "LET THE INTENT SHAPE THE STRUCTURE" in human
    assert "Commercial → how to choose (criteria)" in human
    assert "Intent Distribution:\nCommercial" in human
    # The offer gets a place in the plan, but the brand isn't named there: that's decided later.
    assert "Do NOT name the brand there" in human


@pytest.mark.unit
async def test_without_a_profile_the_outline_says_none_available(outline_prompt):
    human = await outline_prompt({})

    assert (
        "The Workspace's Customers and Offer (who this site serves, and what it offers):\nNone available."
        in human
    )


@pytest.mark.unit
async def test_a_site_that_is_not_about_the_keyword_does_not_lend_it_its_customers(outline_prompt):
    """Launch-night articles (rext-control#816): a site for marketing teams, asked for an
    article on standing desks, planned it for "content marketers". The profile here shares no
    word with the keyword ("seo content brief") or the title, so its customers are left out of
    what the outline is told, and the reason is said."""
    bakery = {
        "customer_profile": "Families and cafes in Leeds who order bread for the week.",
        "target_audience": ["Cafe owners", "Families"],
        "about": "A bakery in Leeds that bakes sourdough and pastries every morning.",
        "selling_position": "Fresh bread, delivered before the cafes open.",
        "content_pillars": ["Sourdough", "Baking at home"],
    }

    human = await outline_prompt(bakery)

    assert "WHO THE SITE SERVES: left out." in human
    assert "Cafe owners" not in human and "Families and cafes" not in human
    # What the brand offers stays: the brand's own mention has its own rules.
    assert "WHAT THE BRAND OFFERS:" in human and "A bakery in Leeds" in human
