import base64
import binascii
import logging
import os
from functools import lru_cache
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy import String, Text, TypeDecorator

logger = logging.getLogger(__name__)


def configured_keys() -> list[str]:
    """The field-encryption keys from FIELD_ENCRYPTION_KEY, newest first.

    One key is the usual setting. While a key is being rotated the variable lists
    several, comma-separated and newest first: values are written with the first
    and read with any of them (scripts/rotate_field_encryption.py has the steps).
    """
    raw = os.environ.get("FIELD_ENCRYPTION_KEY") or ""
    keys = [key.strip() for key in raw.split(",") if key.strip()]
    if not keys:
        raise RuntimeError(
            "FIELD_ENCRYPTION_KEY environment variable is not set. "
            "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
    return keys


@lru_cache(maxsize=4)
def _fernet_for(keys: tuple[str, ...]) -> MultiFernet:
    return MultiFernet([Fernet(key.encode()) for key in keys])


def _get_fernet() -> MultiFernet:
    """Encrypts with the newest configured key, decrypts with any of them."""
    return _fernet_for(tuple(configured_keys()))


def looks_like_token(value: str) -> bool:
    """Whether a stored value has the shape of a Fernet token rather than plaintext.

    A token is the version byte 0x80, an 8-byte timestamp, a 16-byte IV, the
    ciphertext in 16-byte blocks and a 32-byte HMAC, base64url-encoded.
    """
    if not value.startswith("gAAAAA"):
        return False
    try:
        raw = base64.urlsafe_b64decode(value.encode("ascii"))
    except (binascii.Error, ValueError):
        return False
    return raw[0] == 0x80 and len(raw) >= 73 and (len(raw) - 57) % 16 == 0


class EncryptedText(TypeDecorator):
    """
    SQLAlchemy TypeDecorator that transparently encrypts/decrypts text values
    using Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).

    Values are encrypted before being written to the database and decrypted
    when read. The keys come from the FIELD_ENCRYPTION_KEY environment variable
    (see configured_keys).

    Usage:
        api_key = Column(EncryptedText, nullable=True)
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Optional[str], dialect) -> Optional[str]:
        """Encrypt value before storing in database."""
        if value is None:
            return None
        fernet = _get_fernet()
        return fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def process_result_value(self, value: Optional[str], dialect) -> Optional[str]:
        """Decrypt value after reading from database."""
        if value is None:
            return None
        fernet = _get_fernet()
        try:
            return fernet.decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            if looks_like_token(value):
                # Written under a key that is no longer configured. Returning the
                # token would hand ciphertext to the caller as if it were the secret.
                logger.warning("An encrypted field could not be decrypted with any configured key")
                return None
            # Plaintext stored before the column was encrypted
            return value


class EncryptedLongText(EncryptedText):
    """EncryptedText stored in a TEXT column rather than VARCHAR."""

    impl = Text
    cache_ok = True
