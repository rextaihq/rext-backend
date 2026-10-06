"""The field-encryption key can be rotated (G28, revnix/rext-control#343).

FIELD_ENCRYPTION_KEY lists the keys newest first: values are written with the
first and read with any of them, and scripts/rotate_field_encryption.py
re-encrypts what an older key wrote, so the old key can then be dropped.

The command is checked on the test PostgreSQL with a table of its own, created
inside a transaction that is rolled back.
"""

from uuid import uuid4

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    insert,
    literal,
    select,
    type_coerce,
)
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from scripts.rotate_field_encryption import (
    CURRENT,
    ENCRYPTED,
    ROTATED,
    UNREADABLE,
    encrypted_columns,
    reencrypt,
    rotate_table,
)
from src.utils.encryption import (
    EncryptedLongText,
    EncryptedText,
    configured_keys,
    looks_like_token,
)
from tests.conftest import TEST_DATABASE_URL

OLD, NEW, LOST = (Fernet.generate_key().decode() for _ in range(3))


def _write(value: str) -> str:
    return EncryptedText().process_bind_param(value, None)


def _read(stored: str):
    return EncryptedText().process_result_value(stored, None)


def test_keys_are_listed_newest_first(monkeypatch):
    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", f" {NEW} , {OLD} ")
    assert configured_keys() == [NEW, OLD]


def test_no_key_is_an_error(monkeypatch):
    monkeypatch.delenv("FIELD_ENCRYPTION_KEY", raising=False)
    with pytest.raises(RuntimeError, match="FIELD_ENCRYPTION_KEY"):
        configured_keys()


def test_a_value_written_with_the_old_key_reads_while_both_are_listed(monkeypatch):
    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", OLD)
    stored = _write("wp-application-password")

    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", f"{NEW},{OLD}")
    assert _read(stored) == "wp-application-password"
    # New writes use the newest key: they read with it alone.
    rewritten = _write("wp-application-password")
    assert Fernet(NEW.encode()).decrypt(rewritten.encode()) == b"wp-application-password"


def test_a_token_no_configured_key_opens_reads_as_nothing(monkeypatch):
    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", OLD)
    stored = _write("shpat_secret")

    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", NEW)
    assert _read(stored) is None  # never the ciphertext, handed on as if it were the secret


def test_plaintext_from_before_encryption_still_reads(monkeypatch):
    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", NEW)
    assert _read("plain-legacy-value") == "plain-legacy-value"


def test_token_shape():
    assert looks_like_token(Fernet(NEW.encode()).encrypt(b"x").decode())
    assert not looks_like_token("plain-legacy-value")
    assert not looks_like_token("gAAAAA-not-base64!")
    assert not looks_like_token("gAAAAAB")


def test_each_kind_of_stored_value():
    keys = [NEW, OLD]
    under_new = Fernet(NEW.encode()).encrypt(b"a").decode()
    under_old = Fernet(OLD.encode()).encrypt(b"b").decode()
    under_lost = Fernet(LOST.encode()).encrypt(b"c").decode()

    assert reencrypt(under_new, keys) == (CURRENT, None)

    outcome, rotated = reencrypt(under_old, keys)
    assert outcome == ROTATED
    assert Fernet(NEW.encode()).decrypt(rotated.encode()) == b"b"

    outcome, encrypted = reencrypt("plain", keys)
    assert outcome == ENCRYPTED
    assert Fernet(NEW.encode()).decrypt(encrypted.encode()) == b"plain"

    assert reencrypt(under_lost, keys) == (UNREADABLE, None)


def test_every_encrypted_model_column_is_visited():
    import src.api.models  # noqa: F401
    from src.api.database.base import Base

    found = {
        f"{table.name}.{column.name}"
        for table, columns in encrypted_columns(Base.metadata)
        for column in columns
    }
    assert "shopify_app_installs.access_token" in found
    assert any(name.startswith("integrations.") for name in found)


@pytest_asyncio.fixture
async def connection():
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as conn:
        transaction = await conn.begin()
        yield conn
        await transaction.rollback()
    await engine.dispose()


async def test_the_command_rotates_so_the_old_key_can_go(connection, monkeypatch):
    metadata = MetaData()
    table = Table(
        f"rotation_probe_{uuid4().hex[:8]}",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("secret", EncryptedText),
        Column("long_secret", EncryptedLongText),
    )
    await connection.run_sync(metadata.create_all)

    def old(value: str) -> str:
        return Fernet(OLD.encode()).encrypt(value.encode()).decode()

    under_lost = Fernet(LOST.encode()).encrypt(b"gone").decode()
    stored = {
        1: (old("one"), old("long one")),
        2: ("plain two", None),
        3: (under_lost, old("long three")),
        4: (None, None),
        5: (old("five"), "plain long five"),
    }
    for row_id, (secret, long_secret) in stored.items():
        # The stored text itself, past the column type's encryption.
        await connection.execute(
            insert(table).values(
                id=row_id,
                secret=literal(secret, String()),
                long_secret=literal(long_secret, String()),
            )
        )

    columns = [table.c.secret, table.c.long_secret]
    keys = [NEW, OLD]

    dry = await rotate_table(connection, table, columns, keys, apply=False, batch_size=2)
    assert dry["secret"] == {ROTATED: 2, ENCRYPTED: 1, UNREADABLE: 1}
    assert dry["long_secret"] == {ROTATED: 2, ENCRYPTED: 1}
    raw = await connection.execute(
        select(type_coerce(table.c.secret, String)).where(table.c.id == 1)
    )
    assert raw.scalar_one() == stored[1][0]  # a dry run writes nothing

    applied = await rotate_table(connection, table, columns, keys, apply=True, batch_size=2)
    assert applied == dry

    again = await rotate_table(connection, table, columns, keys, apply=True, batch_size=2)
    assert again["secret"] == {CURRENT: 3, UNREADABLE: 1}
    assert again["long_secret"] == {CURRENT: 3}

    # With the old key dropped, everything it wrote still reads.
    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", NEW)
    rows = (await connection.execute(select(table).order_by(table.c.id))).all()
    assert [(row.secret, row.long_secret) for row in rows] == [
        ("one", "long one"),
        ("plain two", None),
        (None, "long three"),  # the unreadable token reads as nothing, and is left as it was
        (None, None),
        ("five", "plain long five"),
    ]
    raw = await connection.execute(
        select(type_coerce(table.c.secret, String)).where(table.c.id == 3)
    )
    assert raw.scalar_one() == under_lost
