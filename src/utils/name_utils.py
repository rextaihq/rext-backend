import re

from src.api.middleware.exceptions import RextValidationException

# Full-name policy for sign-up (email/password and invitation registration).
# rext-admin's signupFullNameSchema (schemas/auth-schemas.ts) should hold the
# same rules so the form reports them while the user types.
FULL_NAME_MIN_LENGTH = 3
FULL_NAME_MAX_LENGTH = 50  # matches the sign-up form's limit

# English letters, with single spaces between words. This excludes digits,
# emoji, punctuation, symbols and invisible characters (zero-width spaces,
# right-to-left overrides) in one rule, rather than trying to list them.
_FULL_NAME_RE = re.compile(r"^[A-Za-z]+(?: [A-Za-z]+)*$")


def validate_signup_full_name(full_name: str) -> str:
    """
    Validate a full name entered at sign-up and return it normalised.

    Leading/trailing whitespace is removed and runs of whitespace inside the
    name are collapsed to one space before the rules are checked, so
    "  John   Smith " is stored as "John Smith".

    Requirements:
    - 3 to 50 characters
    - Letters (A-Z, a-z) and single spaces only: no numbers, emoji or
      special characters
    - Starts with a capital letter

    Raises:
        RextValidationException: If the name does not meet the requirements
    """
    name = " ".join((full_name or "").split())
    errors = []

    if not name:
        errors.append("Full name is required")
    else:
        if any(ch.isdigit() for ch in name):
            errors.append("Full name should not contain numbers")
        elif not _FULL_NAME_RE.match(name):
            errors.append(
                "Full name can only contain letters and spaces (no emoji or special characters)"
            )
        elif not name[0].isupper():
            errors.append("Full name must start with a capital letter")

        if len(name) < FULL_NAME_MIN_LENGTH:
            errors.append(f"Full name must be at least {FULL_NAME_MIN_LENGTH} characters")
        if len(name) > FULL_NAME_MAX_LENGTH:
            errors.append(f"Full name must be at most {FULL_NAME_MAX_LENGTH} characters")

    if errors:
        # Same shape as validate_password_strength: first error as the message.
        raise RextValidationException(message=errors[0], field_errors={"full_name": errors})

    return name
