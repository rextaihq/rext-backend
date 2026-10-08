import re
import unicodedata

from src.api.middleware.exceptions import RextValidationException
from src.utils.input_safety import find_markup, has_hidden_characters, without_joiners_in_words

# Full-name policy for sign-up (email/password and invitation registration).
# rext-admin's signupFullNameSchema (schemas/auth-schemas.ts) should hold the
# same rules so the form reports them while the user types.
#
# A person is never refused for how their name is written (rext-control#933): the rule was
# English letters starting with a capital, which refused "john smith" typed on a phone,
# "José", "O'Brien", "Anne-Marie", "Li" and every name in a script without capitals. Only
# what protects us is checked: a name is there, has a letter in it, fits its limit, and holds
# no markup, no hidden or control character and no web address written as one.
FULL_NAME_MAX_LENGTH = 100  # the column holds 200

# A web address written as one. The name is printed in emails to other people (an invitation
# says who sent it), and no name holds either of these.
_WEB_ADDRESS_RE = re.compile(r"://|\bwww\.", re.IGNORECASE)


WORKSPACE_NAME_MIN_LETTERS = 1  # the same as the dashboard's form asks
WORKSPACE_NAME_MAX_LENGTH = 255
# Unicode letters and digits, and the punctuation people type in a business's name: both kinds of
# apostrophe and quote (a phone keyboard types the curly ones), brackets, dashes of every length,
# and the marks of a title ("Acme: Blog", "Tom’s Bakery", "Acme (UK)"). Markup is refused before
# this is asked (find_markup), so no angle bracket is on the list.
_WORKSPACE_NAME_RE = re.compile(r"^[\w .,&'’‘\"“”()\[\]/+\-–—:;!?|@#%*·•™®©]+$")


def validate_workspace_name(name: str) -> str:
    normalized = unicodedata.normalize("NFC", " ".join((name or "").split()))
    if not normalized:
        raise RextValidationException(
            message="Workspace name is required",
            field_errors={"name": ["Workspace name is required"]},
        )
    if len(normalized) > WORKSPACE_NAME_MAX_LENGTH:
        raise RextValidationException(
            message=f"Workspace name must be at most {WORKSPACE_NAME_MAX_LENGTH} characters",
            field_errors={
                "name": [f"Workspace name must be at most {WORKSPACE_NAME_MAX_LENGTH} characters"]
            },
        )
    markup_error = find_markup(normalized, "Workspace name")
    if markup_error:
        raise RextValidationException(message=markup_error, field_errors={"name": [markup_error]})
    if not _WORKSPACE_NAME_RE.fullmatch(normalized):
        raise RextValidationException(
            message="Workspace name contains unsupported characters",
            field_errors={
                "name": ["Use letters, numbers, spaces and ordinary punctuation in the name"]
            },
        )
    if sum(char.isalpha() for char in normalized) < WORKSPACE_NAME_MIN_LETTERS:
        message = "Workspace name must contain at least one letter"
        raise RextValidationException(message=message, field_errors={"name": [message]})
    return normalized


def validate_brand_name(name: str) -> str:
    """A business's name as its owner typed it: the workspace name's own rule (what it may hold,
    how long), refused beside its own field."""
    try:
        return validate_workspace_name(name)
    except RextValidationException as exc:
        said = [detail["message"] for detail in exc.details] or [str(exc.message)]
        said = [
            text.replace("Workspace name", "The business's name").replace(
                "in the name", "in the business's name"
            )
            for text in said
        ]
        raise RextValidationException(message=said[0], field_errors={"brand_name": said}) from exc


def validate_signup_full_name(full_name: str) -> str:
    """
    Validate a full name entered at sign-up and return it normalised.

    Leading/trailing whitespace is removed and runs of whitespace inside the
    name are collapsed to one space before the rules are checked, so
    "  John   Smith " is stored as "John Smith". The name is stored as the
    person wrote it: any script, any case, with its accents, apostrophes,
    hyphens and full stops.

    Requirements:
    - not empty, and at least one letter of any script
    - at most FULL_NAME_MAX_LENGTH characters
    - no HTML or script, no hidden or control character, no web address
      written as one ("http://", "www.")

    Raises:
        RextValidationException: If the name does not meet the requirements
    """
    name = unicodedata.normalize("NFC", " ".join((full_name or "").split()))
    errors = []

    if not name:
        errors.append("Full name is required")
    else:
        # The joiners Persian and Indic scripts write inside a word are part of the name
        # there, and hidden characters anywhere else.
        markup_error = find_markup(without_joiners_in_words(name), "Full name")
        if markup_error:
            errors.append(markup_error)
        elif has_hidden_characters(name):
            errors.append("Full name cannot contain hidden or control characters")
        elif _WEB_ADDRESS_RE.search(name):
            errors.append("Full name cannot contain a web address")
        elif not any(char.isalpha() for char in name):
            errors.append("Full name must contain at least one letter")

        if len(name) > FULL_NAME_MAX_LENGTH:
            errors.append(f"Full name must be at most {FULL_NAME_MAX_LENGTH} characters")

    if errors:
        # Same shape as validate_password_strength: first error as the message.
        raise RextValidationException(message=errors[0], field_errors={"full_name": errors})

    return name


def validate_signup_fields(full_name: str, password: str) -> str:
    """
    Check the sign-up name and password together and report every problem.

    Checking them one after the other stopped at the first failure, so a
    name's problem was never reported while the password was also wrong.

    Returns:
        The normalised full name.

    Raises:
        RextValidationException: Message lists each failing field's first
            problem; field_errors carries all of them per field.
    """
    from src.utils.password_utils import validate_password_strength

    problems = []
    name = full_name
    try:
        name = validate_signup_full_name(full_name)
    except RextValidationException as exc:
        problems.append(exc)
    try:
        validate_password_strength(password)
    except RextValidationException as exc:
        problems.append(exc)

    if problems:
        field_errors: dict[str, list[str]] = {}
        for exc in problems:
            for detail in exc.details:
                field_errors.setdefault(detail["field"], []).append(detail["message"])
        raise RextValidationException(
            message=". ".join(exc.message for exc in problems), field_errors=field_errors
        )
    return name
