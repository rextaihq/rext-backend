"""A person is never refused at sign-up for how their name is written (rext-control #933).

On live one person was refused three times in ten seconds with "Full name must start with a
capital letter". The rule was English letters A to Z and single spaces, 3 to 50 characters,
starting with a capital: it refused a name typed in lower case on a phone, every accent,
apostrophe and hyphen, a two-letter name, and every script without capitals or outside Latin
letters. Only what protects us is checked now.
"""

import pytest
from pydantic import ValidationError

from src.api.middleware.exceptions import RextValidationException
from src.api.schema.user_schema import RegisterUser, RegisterWithInvitation
from src.utils.name_utils import (
    FULL_NAME_MAX_LENGTH,
    validate_signup_fields,
    validate_signup_full_name,
)

A_STRONG_PASSWORD = "Tr0ub4dor&3-horse-staple"


@pytest.mark.parametrize(
    "name",
    [
        "john smith",  # the name that was refused on live, typed on a phone
        "JOHN SMITH",
        "José Álvarez",
        "O'Brien",
        "O’Brien",  # the apostrophe a phone keyboard types
        "Anne-Marie Dupont",
        "Li",
        "Ng",
        "李雷",
        "محمد",
        "علی\u200cرضا",  # Persian writes a joiner inside the word
        "\u0939\u093f\u0928\u094d\u200d\u0926\u0940",  # Hindi: a joiner after a combining mark
        "Nguyễn Thị Minh Khai",
        "J. R. R. Tolkien",
        "Dr.Ahmed Khan",
        "Martin Luther King, Jr.",
        "Björk",
        "X Æ A-12",
        "Zoë van der Berg",
    ],
)
def test_a_name_is_taken_as_the_person_wrote_it(name):
    assert validate_signup_full_name(name) == name


def test_spaces_are_trimmed_and_collapsed_and_the_letters_are_composed():
    assert validate_signup_full_name("  john   smith ") == "john smith"
    assert validate_signup_full_name("Jose\u0301 A\u0301lvarez") == "José Álvarez"


def test_a_long_name_fits_and_one_past_the_limit_does_not():
    assert validate_signup_full_name("a" * FULL_NAME_MAX_LENGTH) == "a" * FULL_NAME_MAX_LENGTH
    with pytest.raises(RextValidationException) as refused:
        validate_signup_full_name("a" * (FULL_NAME_MAX_LENGTH + 1))
    assert refused.value.message == f"Full name must be at most {FULL_NAME_MAX_LENGTH} characters"


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("", "Full name is required"),
        ("   ", "Full name is required"),
        ("<b>John</b>", "Full name cannot contain HTML or script code"),
        ("John <script>alert(1)</script>", "Full name cannot contain HTML or script code"),
        ("John\u200bSmith", "Full name cannot contain hidden or control characters"),
        ("\u202eJohn Smith", "Full name cannot contain hidden or control characters"),
        ("John\u200c Smith", "Full name cannot contain hidden or control characters"),
        ("John\x07Smith", "Full name cannot contain hidden or control characters"),
        # Every character nobody sees, by Unicode's categories and not a list of ranges: a C1
        # control, a soft hyphen, a private-use character, a joiner at a word's edge.
        ("Jo\x9bhn", "Full name cannot contain hidden or control characters"),
        ("Jo\u00adhn", "Full name cannot contain hidden or control characters"),
        ("Jo\ue000hn", "Full name cannot contain hidden or control characters"),
        ("John\u200d", "Full name cannot contain hidden or control characters"),
        ("\u200cJohn", "Full name cannot contain hidden or control characters"),
        ("Jo\u200c\u200chn", "Full name cannot contain hidden or control characters"),
        ("Prize at http://evil.example", "Full name cannot contain a web address"),
        ("www.evil.example", "Full name cannot contain a web address"),
        ("12345", "Full name must contain at least one letter"),
        ("- - -", "Full name must contain at least one letter"),
        ("😀😀", "Full name must contain at least one letter"),
    ],
)
def test_what_protects_us_is_still_refused(name, message):
    with pytest.raises(RextValidationException) as refused:
        validate_signup_full_name(name)

    assert refused.value.message == message
    assert [detail["field"] for detail in refused.value.details] == ["full_name"]


def test_the_message_about_a_capital_letter_is_gone():
    for name in ("john", "élodie", "ßen", "ǆemal"):
        assert validate_signup_full_name(name) == name


def test_a_lower_case_name_with_a_weak_password_reports_the_password_alone():
    with pytest.raises(RextValidationException) as refused:
        validate_signup_fields("john smith", "short")

    assert {detail["field"] for detail in refused.value.details} == {"password"}


def test_the_sign_up_fields_return_the_name_normalised():
    assert validate_signup_fields("  maría   josé ", A_STRONG_PASSWORD) == "maría josé"


PERSIAN = "\u0639\u0644\u06cc\u200c\u0631\u0636\u0627"
HINDI = "\u0939\u093f\u0928\u094d\u200d\u0926\u0940"


def _request(model, full_name):
    fields = {"full_name": full_name, "email": "person@example.com", "password": A_STRONG_PASSWORD}
    if model is RegisterWithInvitation:
        fields["invitation_token"] = "token"
    return model(**fields)


@pytest.mark.parametrize("model", [RegisterUser, RegisterWithInvitation])
@pytest.mark.parametrize("name", ["john smith", "José Álvarez", "O'Brien", "李雷", PERSIAN, HINDI])
def test_the_request_itself_lets_the_name_through_to_the_rule(model, name):
    """The request models check the name before the route does: a joiner inside a word was a
    hidden character to them, so a Persian name never reached the rule that allows it."""
    assert validate_signup_full_name(_request(model, name).full_name) == name


@pytest.mark.parametrize("model", [RegisterUser, RegisterWithInvitation])
@pytest.mark.parametrize("name", ["<b>John</b>", "John\u200bSmith", "John\u200d", "\u202eJohn"])
def test_the_request_still_refuses_markup_and_hidden_characters(model, name):
    with pytest.raises(ValidationError):
        _request(model, name)
