"""The personas a user picks in the review step become the workspace's set.

Extraction saves every author it can prove the site publishes; the review step
is where the user narrows that down. These cover what the narrowing may and may
not delete.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.services.brand_voice_service import BrandVoiceService


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _StubDB:
    def __init__(self, personas):
        self._personas = personas
        self.deleted = []
        self.flushed = 0

    async def execute(self, _statement):
        return _Result(self._personas)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def flush(self):
        self.flushed += 1


def _persona(name, *, full_name=None, extracted=True):
    return SimpleNamespace(
        id=uuid4(),
        name=name,
        full_name=full_name or name,
        custom_metadata={"source": "author"} if extracted else None,
    )


def _selection(*names):
    return [{"name": name, "full_name": name} for name in names]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_only_the_selected_personas_are_kept():
    personas = [_persona(f"Author {index}") for index in range(5)]
    db = _StubDB(personas)

    await BrandVoiceService(db)._apply_persona_selection(
        uuid4(), _selection("Author 0", "Author 3")
    )

    assert [p.name for p in db.deleted] == ["Author 1", "Author 2", "Author 4"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_selecting_nothing_keeps_every_persona():
    """No selection is "no preference" — the default stays "save them all"."""
    personas = [_persona("Author 0"), _persona("Author 1")]
    db = _StubDB(personas)

    await BrandVoiceService(db)._apply_persona_selection(uuid4(), [])
    await BrandVoiceService(db)._apply_persona_selection(uuid4(), None)

    assert db.deleted == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_persona_someone_typed_in_is_never_dropped_by_a_selection():
    extracted = _persona("Extracted Author")
    handmade = _persona("Hand Written Author", extracted=False)
    db = _StubDB([extracted, handmade])

    await BrandVoiceService(db)._apply_persona_selection(uuid4(), _selection("Somebody Else"))

    # "Somebody Else" matches nothing, so nothing is deleted at all.
    assert db.deleted == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_selection_matching_nothing_deletes_nothing():
    """A payload that describes no persona here is no basis for deleting any."""
    personas = [_persona("Author 0"), _persona("Author 1")]
    db = _StubDB(personas)

    await BrandVoiceService(db)._apply_persona_selection(uuid4(), _selection("Unknown Person"))

    assert db.deleted == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handmade_personas_survive_alongside_a_real_selection():
    kept = _persona("Kept Author")
    dropped = _persona("Dropped Author")
    handmade = _persona("Hand Written Author", extracted=False)
    db = _StubDB([kept, dropped, handmade])

    await BrandVoiceService(db)._apply_persona_selection(uuid4(), _selection("Kept Author"))

    assert [p.name for p in db.deleted] == ["Dropped Author"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_names_match_regardless_of_case_and_padding():
    personas = [_persona("Sara Ortiz"), _persona("Amir Khan")]
    db = _StubDB(personas)

    await BrandVoiceService(db)._apply_persona_selection(
        uuid4(), [{"name": "  sara ortiz  ", "full_name": None}]
    )

    assert [p.name for p in db.deleted] == ["Amir Khan"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_persona_selected_by_full_name_is_kept():
    persona = SimpleNamespace(
        id=uuid4(),
        name="sara",
        full_name="Sara Ortiz",
        custom_metadata={"source": "author"},
    )
    other = _persona("Amir Khan")
    db = _StubDB([persona, other])

    await BrandVoiceService(db)._apply_persona_selection(
        uuid4(), [{"name": "Sara Ortiz", "full_name": "Sara Ortiz"}]
    )

    assert [p.name for p in db.deleted] == ["Amir Khan"]
