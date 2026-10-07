"""The emails' logo is never a broken image (B9c, rext-control#605).

The header loads the logo from storage. The server publishes the build's copy there at start
(publish_logo); until that has worked in this process, the header writes the name as text.
"""

import importlib
from types import SimpleNamespace

import pytest

from emails.components import simple_header

header_module = importlib.import_module("emails.components.header")

STORAGE_URL = "https://media.example.com/rext-media/branding/rext-logo.png"


@pytest.fixture
def storage(monkeypatch):
    state = SimpleNamespace(works=True, uploads=[])

    def upload_file(file_data, object_name, content_type=None):
        state.uploads.append((object_name, content_type, len(file_data)))
        return STORAGE_URL if state.works else None

    monkeypatch.setattr(header_module.storage_service, "upload_file", upload_file)
    monkeypatch.setattr(header_module.storage_service, "get_file_url", lambda name: STORAGE_URL)
    monkeypatch.setattr(header_module, "_logo_published", False)
    return state


def test_the_name_is_text_until_the_logo_is_published(storage):
    html = simple_header()

    assert "<img" not in html
    assert "Rext AI" in html


def test_a_published_logo_is_shown_from_storage(storage):
    assert header_module.publish_logo() is True
    assert storage.uploads == [
        ("branding/rext-logo.png", "image/png", header_module.LOGO_FILE.stat().st_size)
    ]

    html = simple_header()

    assert f'<img src="{STORAGE_URL}"' in html
    assert 'alt="Rext AI"' in html


def test_a_failed_publish_keeps_the_text(storage):
    storage.works = False

    assert header_module.publish_logo() is False
    assert "<img" not in simple_header()
