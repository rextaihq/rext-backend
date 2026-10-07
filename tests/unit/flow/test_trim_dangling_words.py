"""A title trimmed to fit never ends on a dangling word (G69a, #588).

The deterministic repair drops trailing words until a title fits, and could stop right after
"in", "for" or "the": the title step offered "Innovations in ai content writing tools for
agencies in". After a trim, trailing function words go too, never cutting into the keyphrase;
if that leaves the title unusable, the plain trim is kept, so no title is lost for its last word.
A preposition stays when the verb before it needs it ("Depend On", "Look For") or when it had
no object for the trim to cut ("Fall Back On in 2026").
"""

from src.flow.engines.content.generation.seo_title_rules import (
    _trim_to_max,
    repair_title,
    title_is_valid,
)


def test_the_reported_title_ends_on_a_whole_phrase():
    keyphrase = "ai content writing tools"
    title = "Innovations in ai content writing tools for agencies in 2026"  # 60, one over
    assert len(title) == 60

    repaired = repair_title(title, keyphrase)

    assert repaired == "Innovations in ai content writing tools for agencies"
    assert title_is_valid(repaired, keyphrase)


def test_every_trailing_function_word_goes():
    """Trimmed to fit, it would stop after "of the"; both go."""
    title = "SEO Agencies for Small Businesses: How to Choose One of the Best"  # 64
    repaired = repair_title(title, "seo agencies")

    assert repaired == "SEO Agencies for Small Businesses: How to Choose One"
    assert title_is_valid(repaired, "seo agencies")


def test_the_keyphrase_is_never_cut_for_its_last_word():
    keyphrase = "tools to rely on"
    title = "The Complete List of Marketing Software: Tools to Rely On Right Now"  # 67

    repaired = repair_title(title, keyphrase)

    assert repaired == "The Complete List of Marketing Software: Tools to Rely On"
    assert title_is_valid(repaired, keyphrase)


def test_a_preposition_the_verb_needs_stays():
    """Cut after "On", the title still reads; "Businesses Depend" would not."""
    title = "SEO Agencies: The Proven Experts Businesses Depend On Advice"  # 60
    repaired = repair_title(title, "seo agencies")

    assert repaired == "SEO Agencies: The Proven Experts Businesses Depend On"
    assert title_is_valid(repaired, "seo agencies")


def test_a_preposition_whose_object_was_cut_goes_but_the_verbs_stays():
    title = "SEO Agencies: What Small Business Owners Should Look For in One"  # 63
    repaired = repair_title(title, "seo agencies")

    assert repaired == "SEO Agencies: What Small Business Owners Should Look For"


def test_a_preposition_with_no_object_of_its_own_stays():
    """The trim cut nothing of "On", which stood before "in 2026", whatever the verb."""
    title = "SEO Tools: The Platforms Small Agencies Fall Back On in 2026 Today"  # 66
    repaired = repair_title(title, "seo tools")

    assert repaired == "SEO Tools: The Platforms Small Agencies Fall Back On"


def test_a_preposition_before_an_adverb_of_time_had_no_object_to_lose():
    """The trim cut "Today", not the preposition's object, whatever the verb ("lean" is unlisted)."""
    assert repair_title(
        "SEO Agencies: The Experts Every Small Business Turns To Today", "seo agencies"
    ) == ("SEO Agencies: The Experts Every Small Business Turns To")
    assert repair_title(
        "SEO Agencies: The Experts Every Small Business Leans On Today", "seo agencies"
    ) == ("SEO Agencies: The Experts Every Small Business Leans On")


def test_a_time_phrase_or_a_particle_before_the_preposition_keeps_it():
    """The trim cut "This Year", not an object of "On"; and "Up On" completes "Catch"."""
    title = "SEO Agencies: What Small Businesses Need to Catch Up On This Year"  # 65
    repaired = repair_title(title, "seo agencies")

    assert repaired == "SEO Agencies: What Small Businesses Need to Catch Up On"


def test_that_closing_a_clause_stays_and_a_relative_that_goes():
    assert repair_title(
        "SEO Agencies: Learn Why Your Business Really Needs That Today", "seo agencies"
    ) == ("SEO Agencies: Learn Why Your Business Really Needs That")
    # Its clause was cut: "that" goes with it.
    assert _trim_to_max(
        "SEO Agencies: The Proven Tools Small Businesses Need That Save Hours", "seo agencies"
    ) == ("SEO Agencies: The Proven Tools Small Businesses Need")


def test_a_time_word_counts_only_when_it_is_all_the_trim_cut():
    """The trim cut "Today and Tomorrow", the object of "for", not a time after it."""
    title = "SEO Agencies: The Complete Strategic Marketing Plan for Today and Tomorrow"
    assert _trim_to_max(title, "seo agencies") == (
        "SEO Agencies: The Complete Strategic Marketing Plan"
    )


def test_agreeing_keeps_its_preposition():
    title = "SEO Agencies: These Choices Businesses Are Agreeing With Their Advisors"
    assert _trim_to_max(title, "seo agencies") == (
        "SEO Agencies: These Choices Businesses Are Agreeing With"
    )


def test_a_particle_keeps_the_preposition_only_after_a_phrasal_verb():
    """Here "Round Up" is a noun, and "For" lost its object."""
    title = "SEO Agencies: The Complete Detailed Expert Round Up For Teams Everywhere"
    assert _trim_to_max(title, "seo agencies") == (
        "SEO Agencies: The Complete Detailed Expert Round Up"
    )


def test_every_common_preposition_whose_object_was_cut_goes():
    title = "SEO Agencies: A Complete Guide for Small Businesses Without Hidden Costs"
    assert _trim_to_max(title, "seo agencies") == (
        "SEO Agencies: A Complete Guide for Small Businesses"
    )


def test_that_ending_a_clause_before_punctuation_stays():
    title = "SEO Agencies: Why Every Small Business Really Needs That: Guide"
    assert _trim_to_max(title, "seo agencies") == (
        "SEO Agencies: Why Every Small Business Really Needs That"
    )


def test_a_preposition_before_an_adverb_keeps_its_place():
    """The trim cut "Online", not the object of "For"."""
    title = "SEO Agencies: Complete Guide to What Businesses Search For Online"
    assert _trim_to_max(title, "seo agencies") == (
        "SEO Agencies: Complete Guide to What Businesses Search For"
    )


def test_a_verb_ending_in_o_keeps_its_preposition():
    title = "SEO Agencies: Learn Exactly Who This Helpful Guide Goes To Ultimately"
    assert _trim_to_max(title, "seo agencies") == (
        "SEO Agencies: Learn Exactly Who This Helpful Guide Goes To"
    )


def test_a_verb_that_doubles_its_last_consonant_keeps_its_preposition():
    title = "SEO Agencies: A Strategy Your Whole Team Is Committed To Today"  # 62
    repaired = repair_title(title, "seo agencies")

    assert repaired == "SEO Agencies: A Strategy Your Whole Team Is Committed To"


def test_a_clause_ending_on_is_or_are_stays():
    title = "SEO Agencies: A Clear Guide to Understanding Who We Are Today"  # 61
    repaired = repair_title(title, "seo agencies")

    assert repaired == "SEO Agencies: A Clear Guide to Understanding Who We Are"


def test_prepositions_sharing_a_cut_object_all_go():
    """The conjunction after "for" shares the object that was cut ("for and by Industry Experts"),
    so "for" lost it too. (repair_title then keeps the plain trim: 48 characters, and no
    qualifier fits within 59.)"""
    title = "SEO Agencies: A Complete Practical Guide Written for and by Industry Experts"

    assert _trim_to_max(title, "seo agencies") == "SEO Agencies: A Complete Practical Guide Written"


def test_a_preposition_after_a_noun_still_goes():
    """Here "Plan" is a noun, as it mostly is in titles, and "for" lost its object."""
    title = "SEO Tools for Agencies: How to Build a Marketing Plan for 2026 Now"  # 66
    repaired = repair_title(title, "seo tools")

    assert repaired == "SEO Tools for Agencies: How to Build a Marketing Plan"


def test_the_plain_trim_is_kept_when_the_tidy_one_cannot_be_used():
    """Dropping "for the" leaves 49 characters, and no qualifier fits within 59: the plain
    trim, valid as it was, is kept rather than losing the title."""
    title = "Best Tools for Teams: How to Choose the Right One for the Job and"  # 65

    repaired = repair_title(title, "best tools")

    assert repaired == "Best Tools for Teams: How to Choose the Right One for the"
    assert title_is_valid(repaired, "best tools")


def test_a_title_that_needs_no_trim_is_left_as_written():
    """Only a trim's ending is tidied: a phrasal ending the writer chose stays."""
    title = "SEO Agencies: What Small Businesses Should Look For"  # 51, valid

    assert title_is_valid(title, "seo agencies")
    assert repair_title(title, "seo agencies") == title
