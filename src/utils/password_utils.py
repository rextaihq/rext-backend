# File: src/utils/password_utils.py (new file)
import re
from src.api.middleware.exceptions import RextValidationException


# Password policy constants
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 72  # bcrypt truncates at 72 bytes


def validate_password_strength(password: str) -> None:
    """
    Validate password meets minimum strength requirements.

    Requirements (matching frontend validation):
    - Minimum 8 characters
    - Maximum 72 characters (bcrypt limit)
    - At least one uppercase letter (A-Z)
    - At least one lowercase letter (a-z)
    - At least one digit (0-9)

    Args:
        password: Plain text password to validate

    Raises:
        RextValidationException: If password does not meet requirements
    """
    errors = []

    if len(password) < MIN_PASSWORD_LENGTH:
        errors.append(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")

    if len(password) > MAX_PASSWORD_LENGTH:
        errors.append(f"Password must be at most {MAX_PASSWORD_LENGTH} characters")

    if not re.search(r'[A-Z]', password):
        errors.append("Password must contain at least one uppercase letter")

    if not re.search(r'[a-z]', password):
        errors.append("Password must contain at least one lowercase letter")

    if not re.search(r'\d', password):
        errors.append("Password must contain at least one number")

    if errors:
        # Use only the first (highest priority) error as the main message
        detailed_message = f"{errors[0]}"
        
        raise RextValidationException(
            message=detailed_message,
            field_errors={"password": errors}
        )

