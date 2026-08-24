"""
Email Domain Validation Utility
================================

Provides a fast, zero-dependency check for whether a given email address
belongs to a known disposable or temporary email provider.

Usage:
    from src.utils.email_domain_validator import is_disposable_email

    if is_disposable_email("user@mailinator.com"):
        raise HTTPException(status_code=422, detail="Disposable email not allowed.")
"""

from src.constants.disposable_email_domains import DISPOSABLE_EMAIL_DOMAINS


def is_disposable_email(email: str) -> bool:
    """
    Return True if the email's domain is a known disposable / temporary provider.

    Behaviour:
    - Case-insensitive: "User@Mailinator.COM" → domain "mailinator.com" → blocked.
    - Handles subdomains: "user@sub.mailinator.com" checks both "sub.mailinator.com"
      AND the root "mailinator.com" so subdomain tricks don't bypass the check.
    - Pure in-memory lookup (frozenset) — O(1), no network call, no DB hit.

    Args:
        email: A raw email string (may be already validated by Pydantic EmailStr).

    Returns:
        True if the domain or its root domain is in the blocklist, False otherwise.
    """
    try:
        domain = email.rsplit("@", 1)[-1].lower().strip()
    except Exception:
        # Malformed email — let the normal validation handle it
        return False

    # Direct match (most common case)
    if domain in DISPOSABLE_EMAIL_DOMAINS:
        return True

    # Subdomain match: strip one level at a time and check root
    # e.g. "mail.mailinator.com" → "mailinator.com"
    parts = domain.split(".")
    if len(parts) > 2:
        root_domain = ".".join(parts[-2:])
        if root_domain in DISPOSABLE_EMAIL_DOMAINS:
            return True

    return False
