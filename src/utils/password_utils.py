# File: src/utils/password_utils.py (new file)
import re
import string

from src.api.middleware.exceptions import RextValidationException
from src.utils.input_safety import find_script_content

# Password policy constants
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 72  # bcrypt truncates at 72 bytes
# Keyboard symbols that count as the required special character; "<" and ">"
# are excluded because they are not allowed at all.
PASSWORD_SPECIAL_CHARACTERS = string.punctuation.replace("<", "").replace(">", "")


def validate_password_strength(password: str) -> None:
    """
    Validate password meets minimum strength requirements.

    Requirements (matching frontend validation):
    - Minimum 8 characters
    - Maximum 72 characters (bcrypt limit)
    - At least one uppercase letter (A-Z)
    - At least one lowercase letter (a-z)
    - At least one digit (0-9)
    - At least one special character (one of PASSWORD_SPECIAL_CHARACTERS)
    - No "<" or ">", no "javascript:", no control or invisible characters

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
            f"Password must be at most {MAX_PASSWORD_LENGTH} characters "
            "(accented letters and emoji count as more than one)"
        )

    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter")

    if not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter")

    if not re.search(r"\d", password):
        errors.append("Password must contain at least one number")

    if not any(ch in PASSWORD_SPECIAL_CHARACTERS for ch in password):
        errors.append("Password must contain at least one special character (e.g. ! @ # $ %)")

    if errors:
        # Use only the first (highest priority) error as the main message
        detailed_message = f"{errors[0]}"

        raise RextValidationException(message=detailed_message, field_errors={"password": errors})
