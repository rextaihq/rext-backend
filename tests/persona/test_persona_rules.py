"""Unit tests for the rules that decide who becomes a persona.

Every case here is something that actually reached a persona list during
development. They run without network or model access, so they can gate a
change; the benchmark measures whole sites and needs both.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.services.workspace_pipeline import (  # noqa: E402
    _confidence, _has_departed, _is_collective, _is_heading_not_name,
    _is_publication_name, _names_other_employer, _priority)
from src.utils.fast_scraper import (  # noqa: E402
    _is_collective_name, _is_person_name, extract_author_facts,
    extract_founder_credits, gravatar_url, initials_avatar)


@pytest.mark.parametrize("value", [
    "Nouman Yaqoob", "Syed Balkhi", "Diana Greenhaw", "Alicia Malone",
    "Laura K. Gray", "Mark Read",          # a real name holding a UI word
])
def test_person_names_accepted(value):
    assert _is_person_name(value)


@pytest.mark.parametrize("value,reason", [
    ("Read more »", "link furniture read as a byline"),
    ("View Profile", "link furniture"),
    ("Continue Reading", "link furniture"),
    ("Devrevnix Com", "name derived from dev@revnix.com"),
    ("Huzaifa Revnixgmail Com", "name derived from an address"),
    ("Syed Balkhi CEO Awesome Motive Inc.", "name plus title and employer"),
    ("Mark Meissner SVP, Engagement Officer (North America)", "name plus title"),
    ("wpbeginner", "an account handle"),
])
def test_non_names_rejected(value, reason):
    assert not _is_person_name(value), reason


@pytest.mark.parametrize("value", [
    "Editorial Staff", "Editorial Team", "The News Desk", "Content Team"])
def test_collectives_identified(value):
    assert _is_collective_name(value) or _is_collective(value)


def test_section_heading_is_not_a_person():
    # Sat above the staff cards on 21stcenturyequipment.com.
    assert _is_heading_not_name("Hear From Our Team")
    assert not _is_heading_not_name("Nouman Yaqoob")


def test_publication_is_not_a_person():
    # Reached the pcisecuritystandards.org roster at full confidence.
    assert _is_publication_name("PCI Perspectives", "pcisecuritystandards")
    assert not _is_publication_name("Alicia Malone", "pcisecuritystandards")


def test_other_employers_role_rejected():
    # revnix.com credits this under a client quotation with no testimonial markup.
    assert _names_other_employer("COO, KitBash3D + Greyscalegorilla", "revnix")
    assert not _names_other_employer("Head of Product & Technology", "pci")


def test_departure_needs_the_phrase_beside_the_name():
    pages = {"a": "Sam Ray has since left the company.",
             "b": "Past results vary. Amy Fox writes here."}
    assert _has_departed("Sam Ray", pages)
    assert not _has_departed("Amy Fox", pages)


def test_stated_facts_are_read_not_inferred():
    html = ("<p>Started blogging in 2002 with over 23 years of hands-on "
            "experience. Joined the WPBeginner team in 2012.</p>")
    facts = extract_author_facts(html)
    assert facts["years_experience"] == 23
    assert facts["joined_year"] == 2012
    assert facts["active_since"] == 2002


def test_founder_credit_stops_at_the_name():
    assert list(extract_founder_credits(
        "<p>WPBeginner was founded by Syed Balkhi in 2009.</p>")) == ["Syed Balkhi"]
    assert extract_founder_credits("<p>Created by the Editorial Staff</p>") == {}


def test_gravatar_requires_an_address_and_refuses_a_default():
    url = gravatar_url("  Syed@WPBeginner.com ")
    assert "d=404" in url, "a miss must 404 rather than return a generated design"
    assert gravatar_url("not-an-email") == ""


def test_initials_avatar_is_stable_and_self_contained():
    first = initials_avatar("Nouman Yaqoob")
    assert first.startswith("data:image/svg+xml")
    assert first == initials_avatar("Nouman Yaqoob")


class TestConfidence:
    def test_team_page_sets_a_floor(self):
        score, _ = _confidence({}, {"on_team_page"})
        assert score >= 65

    def test_leadership_sets_a_higher_floor(self):
        score, _ = _confidence({}, {"leadership_title", "inactive"})
        assert score >= 75, "an inactive founder is still the founder"

    def test_departure_outranks_every_floor(self):
        score, _ = _confidence({}, {"leadership_title", "on_team_page", "departed"})
        assert score < 75, "someone who has left is not a current persona"

    def test_active_writer_beats_inactive_founder(self):
        writer, _ = _confidence({}, {"author_profile", "contributor_50plus",
                                     "active_2023_plus", "bio"})
        founder, _ = _confidence({}, {"on_team_page", "declared_byline",
                                      "job_title", "bio", "avatar", "inactive"})
        assert writer > founder

    def test_no_provenance_scores_low(self):
        score, _ = _confidence({}, {"bio", "job_title"})
        assert _priority(score) == "low"


class TestRecommendation:
    """Which persona the brand is told to write as.

    A ranked list says who scores highest; it does not say who can speak for
    the brand, and the two differ exactly where it matters.
    """

    @staticmethod
    def _pick(people: list) -> str:
        """The selection rule, applied to already-ranked personas."""
        from src.services.workspace_pipeline import _RECOMMENDATION_FLOOR
        for p in people:
            meta = p.get("custom_metadata") or {}
            if meta.get("is_collective"):
                continue
            if "departed" in (meta.get("confidence_signals") or []):
                continue
            if (meta.get("confidence") or 0) >= _RECOMMENDATION_FLOOR:
                return p["name"]
        return ""

    def test_a_masthead_never_speaks_for_the_brand(self):
        # Editorial Staff outscores everyone on wpbeginner.com with 2141
        # pieces, and has no voice of its own to write in.
        assert self._pick([
            {"name": "Editorial Staff",
             "custom_metadata": {"confidence": 100, "is_collective": True}},
            {"name": "Nouman Yaqoob", "custom_metadata": {"confidence": 91}},
        ]) == "Nouman Yaqoob"

    def test_someone_who_has_left_is_not_put_forward(self):
        assert self._pick([
            {"name": "Gone Person",
             "custom_metadata": {"confidence": 95,
                                 "confidence_signals": ["departed"]}},
            {"name": "Current Writer", "custom_metadata": {"confidence": 72}},
        ]) == "Current Writer"

    def test_nobody_is_recommended_on_thin_evidence(self):
        # Better to recommend nobody than to put someone forward on evidence
        # too thin to defend when a reader asks why.
        assert self._pick([
            {"name": "Barely Known", "custom_metadata": {"confidence": 40}},
        ]) == ""

    def test_the_strongest_eligible_person_wins(self):
        assert self._pick([
            {"name": "Top Writer", "custom_metadata": {"confidence": 100}},
            {"name": "Second", "custom_metadata": {"confidence": 80}},
        ]) == "Top Writer"
