"""Field rules for personas a person types in.

These cover PER-003, PER-006, PER-011 and PER-012 from the persona test plan.
The admin app checks the same things while someone types; this is the copy that
decides, so each case is named after the one it keeps closed.

`PersonaExtract` is deliberately not held to these rules — it carries what a
crawl found on someone else's site, and refusing a real person's bio because
their site writes it with a character we disallow in our own form would lose
the extraction rather than improve it. The last test pins that down.
"""

import pytest
from pydantic import ValidationError

from src.api.schema.persona_schema import (
    PERSONA_FIELD_LIMITS,
    PersonaCreate,
    PersonaExtract,
    PersonaUpdate,
    is_valid_http_url,
)


def _message(exc: ValidationError) -> str:
    return exc.errors()[0]["msg"].replace("Value error, ", "")


# --------------------------------------------------------------------------
# PER-006 — avatar URL validation
# --------------------------------------------------------------------------

BAD_URLS = [
    "https:///example.com",
    "https://-example.com",
    "https://example,com",
    "https://example-.com",
    "https://example",
    "https://exa mple.com",
    "ftp://example.com/photo.jpg",
    "javascript:alert(1)",
    "not a url at all",
]

GOOD_URLS = [
    "https://example.com/photo.jpg",
    "http://cdn.example.co.uk/a/b/c.png",
    "https://1.2.3.4/photo.png",
    "http://localhost:3000/photo.png",
]


@pytest.mark.parametrize("url", BAD_URLS)
def test_malformed_avatar_url_is_rejected(url):
    assert is_valid_http_url(url) is False
    with pytest.raises(ValidationError):
        PersonaCreate(name="Marketing Mary", avatar_url=url)


@pytest.mark.parametrize("url", GOOD_URLS)
def test_usable_avatar_url_is_accepted(url):
    assert is_valid_http_url(url) is True
    assert PersonaCreate(name="Marketing Mary", avatar_url=url).avatar_url == url


def test_stored_object_key_and_data_uri_pass_through():
    """An uploaded file and generated initials are ours, not typed input."""
    key = "avatars/personas/abc/avatar_1.png"
    assert PersonaUpdate(avatar_url=key).avatar_url == key
    assert PersonaUpdate(avatar_url="data:image/svg+xml;base64,AA==").avatar_url.startswith(
        "data:"
    )


def test_linkedin_url_must_be_a_profile():
    with pytest.raises(ValidationError):
        PersonaCreate(name="Marketing Mary", linkedin_url="https://linked.in/in/mary")
    assert PersonaCreate(
        name="Marketing Mary", linkedin_url="https://www.linkedin.com/in/mary-jane"
    ).linkedin_url


# --------------------------------------------------------------------------
# PER-003 — display name required, professional title optional
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["", " ", "M"])
def test_display_name_is_required(name):
    with pytest.raises(ValidationError):
        PersonaCreate(name=name)


def test_professional_title_is_optional():
    assert PersonaCreate(name="Marketing Mary").professional_title is None
    assert PersonaCreate(name="Marketing Mary", professional_title=None).professional_title is None


def test_professional_title_is_bounded_when_given():
    low, high = PERSONA_FIELD_LIMITS["professional_title"]
    with pytest.raises(ValidationError):
        PersonaCreate(name="Marketing Mary", professional_title="x" * (low - 1))
    with pytest.raises(ValidationError):
        PersonaCreate(name="Marketing Mary", professional_title="x" * (high + 1))
    assert PersonaCreate(name="Marketing Mary", professional_title="SEO Lead")


# --------------------------------------------------------------------------
# PER-011 — special characters
# --------------------------------------------------------------------------


def test_markup_in_a_name_is_rejected():
    with pytest.raises(ValidationError) as exc:
        PersonaCreate(name="<script>alert(1)</script>")
    assert "may only contain" in _message(exc.value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("description", "Hello <b>there</b>"),
        ("bio", "A marketer who writes ${payload} posts about search"),
        ("demographics", "25-40, urban, `whoami`"),
        ("tone_of_voice", "Friendly |& direct"),
    ],
)
def test_markup_and_template_syntax_in_prose_is_rejected(field, value):
    with pytest.raises(ValidationError) as exc:
        PersonaCreate(name="Marketing Mary", **{field: value})
    assert "cannot contain" in _message(exc.value)


def test_ordinary_punctuation_still_works():
    persona = PersonaCreate(
        name="Mary-Jane O'Brien",
        bio="She writes about SEO, analytics & content: clearly, and often!",
        description="A marketer (ten years) focused on organic growth.",
    )
    assert persona.name == "Mary-Jane O'Brien"


def test_list_entries_are_checked_individually():
    with pytest.raises(ValidationError) as exc:
        PersonaCreate(name="Marketing Mary", areas_of_expertise=["SEO", "`rm -rf /`"])
    assert "cannot contain" in _message(exc.value)


# --------------------------------------------------------------------------
# PER-012 — maximum length
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field", ["name", "description", "bio", "demographics", "tone_of_voice"]
)
def test_long_text_is_rejected(field):
    maximum = PERSONA_FIELD_LIMITS[field][1]
    with pytest.raises(ValidationError):
        PersonaCreate(**{"name": "Marketing Mary", field: "a" * (maximum + 1)})


def test_short_bio_is_rejected():
    with pytest.raises(ValidationError):
        PersonaCreate(name="Marketing Mary", bio="Hi.")


def test_comma_separated_fields_are_bounded():
    with pytest.raises(ValidationError):
        PersonaCreate(name="Marketing Mary", goals=["a" * 501])
    with pytest.raises(ValidationError):
        PersonaCreate(
            name="Marketing Mary", areas_of_expertise=[f"Topic {i}" for i in range(21)]
        )
    assert PersonaCreate(name="Marketing Mary", areas_of_expertise=["SEO", "Analytics"])


# --------------------------------------------------------------------------
# The update schema is held to the same rules, and leaves unsent fields alone
# --------------------------------------------------------------------------


def test_update_applies_the_same_rules():
    with pytest.raises(ValidationError):
        PersonaUpdate(bio="a" * (PERSONA_FIELD_LIMITS["bio"][1] + 1))
    with pytest.raises(ValidationError):
        PersonaUpdate(avatar_url="https://example,com")


def test_update_only_carries_what_was_sent():
    assert PersonaUpdate(name="Marketing Mary").model_dump(exclude_unset=True) == {
        "name": "Marketing Mary"
    }


# --------------------------------------------------------------------------
# Extraction is not held to the manual-entry rules
# --------------------------------------------------------------------------


def test_extracted_personas_are_not_held_to_the_form_rules():
    """A crawl reports what a site says; rejecting it would lose the person."""
    extracted = PersonaExtract(
        name="Dr. <b>Sarah</b> Mitchell",
        bio="x" * 5000,
        professional_title="Board-Certified Dermatologist and Clinical Researcher",
    )
    assert extracted.name
