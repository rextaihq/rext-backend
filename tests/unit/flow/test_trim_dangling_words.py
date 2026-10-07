"""A title trimmed to fit never ends on a dangling word (G69a, #588).

The deterministic repair drops trailing words until a title fits, and could stop right after
"in", "for" or "the": the title step offered "Innovations in ai content writing tools for
agencies in". After a trim, trailing function words go too, never cutting into the keyphrase;
if that leaves the title unusable, the plain trim is kept, so no title is lost for its last word.
"""

from src.flow.engines.content.generation.seo_title_rules import repair_title, title_is_valid


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
