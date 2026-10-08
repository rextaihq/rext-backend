# File: src/utils/password_utils.py (new file)
import asyncio
import hashlib
import os

import httpx

from src.api.middleware.exceptions import RextValidationException
from src.utils.input_safety import find_script_content
from src.utils.logger import logger

# Password policy constants
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 72  # bytes: bcrypt's limit


# The rule is the one the app tells people (rext-control#939): at least 8 characters, at most
# 72 bytes, and not a password known from a breach. It also asked for an upper-case letter, a
# lower-case letter, a number and a symbol, which the sign-up form never said: a passphrase
# such as "blueberry pancakes" passed the form and was refused here, one rule at a time.
BREACHED_PASSWORD_MESSAGE = (
    "This password has appeared in a data breach. Please choose a different password"
)

# The floor under the breach list, for when it can't be reached: the commonest passwords of
# eight characters or more, compared without regard to case.
_COMMONEST_PASSWORDS = frozenset(
    {
        "password", "password1", "password12", "password123", "password1234", "passw0rd",
        "p@ssw0rd", "p@ssword", "pa55word", "12345678", "123456789", "1234567890", "0123456789",
        "0987654321", "987654321", "87654321", "11111111", "00000000", "12341234", "123123123",
        "1q2w3e4r", "1q2w3e4r5t", "q1w2e3r4", "q1w2e3r4t5", "1qaz2wsx", "1qazxsw2", "zaq12wsx",
        "qwertyui", "qwertyuiop", "qwerty123", "qwerty12", "qwerty1234", "qwer1234", "1234qwer",
        "asdfghjk", "asdfghjkl", "asdf1234", "zxcvbnm1", "abcd1234", "abc12345", "abcdefgh",
        "a1b2c3d4", "iloveyou", "iloveyou1", "sunshine", "princess", "football", "baseball",
        "superman", "trustno1", "starwars", "whatever", "computer", "internet", "welcome1",
        "welcome123", "letmein1", "letmein123", "admin123", "admin1234", "administrator",
        "changeme", "changeme1", "test1234", "testtest", "monkey123", "dragon123", "master123",
        "michelle", "jennifer", "football1", "baseball1", "liverpool", "chocolate", "passpass",
    }
)  # fmt: skip


def validate_password_strength(password: str) -> None:
    """
    Validate a password against the rule the app states, without leaving the process.

    Requirements:
    - at least 8 characters
    - at most 72 bytes (bcrypt's limit: 72 plain letters, fewer with accented
      letters or emoji, which take two to four bytes each)
    - not one of the commonest passwords (the floor under the breach list,
      which `ensure_password_not_breached` asks)
    - no "<" or ">", no "javascript:", no control or invisible characters

    Every unmet part is reported in one answer: the message joins them and
    field_errors lists each for the password field.

    Args:
        password: Plain text password to validate

    Raises:
        RextValidationException: If password does not meet requirements
    """
    errors = []

    # Checked first so this is the message shown for an HTML/script attempt.
    script_error = find_script_content(password, "Password")
    if script_error:
        errors.append(script_error)

    if len(password) < MIN_PASSWORD_LENGTH:
        errors.append(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")

    # bcrypt's limit is 72 *bytes*: accented letters and emoji take 2-4 bytes
    # each, and bcrypt 5 raises on anything longer instead of truncating, so
    # counting characters let such passwords through to a 500.
    if len(password.encode("utf-8")) > MAX_PASSWORD_LENGTH:
        errors.append(
            f"Password must be at most {MAX_PASSWORD_LENGTH} bytes: {MAX_PASSWORD_LENGTH} plain "
            "letters, fewer with accented letters or emoji, which count as two to four each"
        )

    if password.lower() in _COMMONEST_PASSWORDS:
        errors.append(BREACHED_PASSWORD_MESSAGE)

    if errors:
        raise RextValidationException(message=". ".join(errors), field_errors={"password": errors})


# Have I Been Pwned's range API (k-anonymity): the first five characters of the password's
# SHA-1 are sent, never the password or its whole hash, and the answer lists the endings known
# from breaches for that beginning. The same call the dashboard makes from the browser.
_BREACH_RANGE_URL = "https://api.pwnedpasswords.com/range/"
# The whole call, however it is slow: a sign-up is never held longer for it.
_BREACH_RANGE_SECONDS = 2.0


async def _breach_range(prefix: str) -> str:
    """The list's answer for one beginning of a hash, as text."""
    async with httpx.AsyncClient(timeout=_BREACH_RANGE_SECONDS) as http:
        response = await http.get(f"{_BREACH_RANGE_URL}{prefix}", headers={"Add-Padding": "true"})
    response.raise_for_status()
    return response.text


async def password_is_breached(password: str) -> bool:
    """Whether the password is known from a data breach, by the range list.

    False when the list can't be asked or doesn't answer in time: the password is then allowed,
    as the dashboard allows it, and the commonest ones are refused without the list
    (validate_password_strength). REXT_PASSWORD_BREACH_CHECK=off leaves the call out (tests).
    """
    if os.getenv("REXT_PASSWORD_BREACH_CHECK", "on").strip().lower() == "off":
        return False
    digest = hashlib.sha1(password.encode("utf-8"), usedforsecurity=False).hexdigest().upper()
    prefix, ending = digest[:5], digest[5:]
    try:
        listed = await asyncio.wait_for(_breach_range(prefix), timeout=_BREACH_RANGE_SECONDS)
    except Exception as error:
        # The kind of failure only: nothing of the password or its hash is logged.
        logger.warning("The breached-password list did not answer: %s", type(error).__name__)
        return False
    for line in listed.splitlines():
        found, _, count = line.partition(":")
        # A padding line carries a count of 0: it is no password.
        if found.strip().upper() == ending and count.strip() not in ("", "0"):
            return True
    return False


async def ensure_password_not_breached(password: str) -> None:
    """Refuse a password known from a data breach, in the dashboard's own sentence, as a field
    error on the password. Call it after validate_password_strength."""
    if await password_is_breached(password):
        raise RextValidationException(
            message=BREACHED_PASSWORD_MESSAGE,
            field_errors={"password": [BREACHED_PASSWORD_MESSAGE]},
        )
