"""Re-encrypt every encrypted column with the newest field-encryption key.

FIELD_ENCRYPTION_KEY holds the keys, comma-separated and newest first. Values
are written with the first key and read with any of them, so a key is rotated
without losing what it protects:

1. Generate the new key:
   python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
2. Set FIELD_ENCRYPTION_KEY to "<new>,<old>" and deploy. New writes use the new key.
3. Run this script with --apply where the server runs. Run it again: every value
   counts as current and none as unreadable.
4. Set FIELD_ENCRYPTION_KEY to "<new>" alone and deploy. The old key is gone.

Every column whose type is EncryptedText (or EncryptedLongText) is visited, in
batches by primary key. A value already under the newest key is left alone; one
under an older key is re-encrypted with the newest; plaintext stored before the
column was encrypted is encrypted; a token no configured key opens is left as it
is and counted as unreadable (the script then exits 1: keep the old key until it
is 0). A row changed by the app between the read and the write is skipped and
picked up by the next run. It prints counts only, never a value or a key.

    python scripts/rotate_field_encryption.py            # count what would change
    python scripts/rotate_field_encryption.py --apply    # re-encrypt
"""

import asyncio
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Awaitable, Callable, Iterator, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptography.fernet import Fernet, InvalidToken, MultiFernet  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
from sqlalchemy import Column, MetaData, String, Table, literal, select, type_coerce, update  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncConnection  # noqa: E402

from src.utils.encryption import EncryptedText, configured_keys, looks_like_token  # noqa: E402

BATCH_SIZE = 500

CURRENT = "current"  # already under the newest key
ROTATED = "rotated"  # under an older key, re-encrypted with the newest
ENCRYPTED = "encrypted"  # plaintext from before the column was encrypted
UNREADABLE = "unreadable"  # a token no configured key opens; left as it is
SKIPPED = "skipped"  # changed by the app between the read and the write
OUTCOMES = (CURRENT, ROTATED, ENCRYPTED, UNREADABLE, SKIPPED)


def encrypted_columns(metadata: MetaData) -> Iterator[tuple[Table, list[Column]]]:
    """Every table with an encrypted column, and those columns."""
    for table in metadata.sorted_tables:
        columns = [column for column in table.columns if isinstance(column.type, EncryptedText)]
        if columns:
            yield table, columns


@lru_cache(maxsize=4)
def _ciphers(keys: tuple[str, ...]) -> tuple[Fernet, MultiFernet]:
    fernets = [Fernet(key.encode()) for key in keys]
    return fernets[0], MultiFernet(fernets)


def reencrypt(value: str, keys: list[str]) -> tuple[str, Optional[str]]:
    """What happens to one stored value: its outcome and, when it changes, the new text."""
    newest, every = _ciphers(tuple(keys))
    token = value.encode("utf-8")
    try:
        newest.decrypt(token)
        return CURRENT, None
    except InvalidToken:
        pass
    try:
        rotated = every.rotate(token)
        return ROTATED, rotated.decode("utf-8")
    except InvalidToken:
        pass
    if looks_like_token(value):
        return UNREADABLE, None
    return ENCRYPTED, newest.encrypt(token).decode("utf-8")


async def rotate_table(
    conn: AsyncConnection,
    table: Table,
    columns: list[Column],
    keys: list[str],
    apply: bool,
    commit: Optional[Callable[[], Awaitable[None]]] = None,
    batch_size: int = BATCH_SIZE,
) -> dict[str, Counter]:
    """Re-encrypt one table's encrypted columns; the counts per column."""
    (pk,) = table.primary_key.columns
    # Read and compare the stored text itself, not the column type's decrypted value.
    stored = {column.name: type_coerce(column, String) for column in columns}
    counts = {column.name: Counter() for column in columns}
    last = None
    while True:
        query = select(pk, *(expr.label(name) for name, expr in stored.items())).order_by(pk)
        if last is not None:
            query = query.where(pk > last)
        rows = (await conn.execute(query.limit(batch_size))).mappings().all()
        if not rows:
            return counts
        for row in rows:
            for name, expr in stored.items():
                value = row[name]
                if value is None:
                    continue
                outcome, new_value = reencrypt(value, keys)
                if apply and new_value is not None:
                    result = await conn.execute(
                        update(table)
                        .where(pk == row[pk.name], expr == literal(value, String()))
                        .values({name: literal(new_value, String())})
                    )
                    if result.rowcount == 0:
                        outcome = SKIPPED
                counts[name][outcome] += 1
        last = rows[-1][pk.name]
        if apply and commit is not None:
            await commit()


def report(table: Table, counts: dict[str, Counter], apply: bool) -> None:
    for name, column_counts in counts.items():
        parts = ", ".join(f"{column_counts[outcome]} {outcome}" for outcome in OUTCOMES)
        print(f"{table.name}.{name}: {parts}{'' if apply else ' (dry run)'}")


async def main(apply: bool) -> int:
    import src.api.models  # noqa: F401  (every model registers its table on Base.metadata)
    from src.api.database.async_database import async_engine
    from src.api.database.base import Base

    keys = configured_keys()
    print(f"{len(keys)} key(s) configured; values end under the first.")
    unreadable = 0
    async with async_engine.connect() as conn:
        for table, columns in encrypted_columns(Base.metadata):
            counts = await rotate_table(conn, table, columns, keys, apply, commit=conn.commit)
            report(table, counts, apply)
            unreadable += sum(column_counts[UNREADABLE] for column_counts in counts.values())
        if not apply:
            await conn.rollback()
    await async_engine.dispose()
    if unreadable:
        print(
            f"{unreadable} value(s) no configured key can read: keep every old key until this is 0."
        )
        return 1
    return 0


if __name__ == "__main__":
    load_dotenv()
    sys.exit(asyncio.run(main("--apply" in sys.argv[1:])))
