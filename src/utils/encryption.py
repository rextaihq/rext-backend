import os
from typing import Optional

from cryptography.fernet import Fernet
from sqlalchemy import String, Text, TypeDecorator


def _get_fernet() -> Fernet:
    """Get Fernet instance using the encryption key from environment."""
    key = os.environ.get("FIELD_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "FIELD_ENCRYPTION_KEY environment variable is not set. "
            "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


class EncryptedText(TypeDecorator):
    """
    SQLAlchemy TypeDecorator that transparently encrypts/decrypts text values
    using Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).

    Values are encrypted before being written to the database and decrypted
    when read. The encryption key is sourced from the FIELD_ENCRYPTION_KEY
    environment variable.

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
        except Exception:
            # Fallback for existing plaintext or decryption failure
            return value


class EncryptedLongText(EncryptedText):
    """EncryptedText stored in a TEXT column rather than VARCHAR."""

    impl = Text
    cache_ok = True
