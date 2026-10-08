"""The outline promotes no label as a brand (revnix/rext-control#853).

A workspace made from its owner's description has no website, and its brand name is empty until
the owner writes one. The workspace's own name is only a label there ("Client 2"), so with neither
a name nor a site the outline is given no brand to promote. With a site the label still stands in,
as before.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.flow.engines.content.generation import outline as outline_module


def _stored(monkeypatch, *, brand_name, label, url):
    """The brand voice and workspace the lookup reads, in place of the database."""
    voice = SimpleNamespace(brand_name=brand_name, about="We bake bread.", selling_position="")

    async def read(coroutine):
        coroutine.close()
        return voice, label, url

    monkeypatch.setattr("src.utils.loop_bridge.run_on_main_loop", read)


@pytest.mark.asyncio
async def test_no_name_and_no_site_is_no_brand_to_promote(monkeypatch):
    _stored(monkeypatch, brand_name=None, label="Client 2", url=None)

    assert await outline_module._fetch_brand_voice_promotion({"sections": []}, uuid4()) is None


@pytest.mark.asyncio
async def test_a_name_the_owner_gave_is_promoted_without_a_link(monkeypatch):
    _stored(monkeypatch, brand_name="Crumb and Crust", label="Client 2", url=None)

    promo = await outline_module._fetch_brand_voice_promotion({"sections": []}, uuid4())

    assert promo["brand_name"] == "Crumb and Crust"
    assert promo["brand_url"] == ""


@pytest.mark.asyncio
async def test_with_a_site_the_label_still_stands_in_for_a_missing_name(monkeypatch):
    _stored(monkeypatch, brand_name=None, label="Crumb and Crust", url="https://crumb.example.com")

    promo = await outline_module._fetch_brand_voice_promotion({"sections": []}, uuid4())

    assert promo["brand_name"] == "Crumb and Crust"
    assert promo["brand_url"] == "https://crumb.example.com"
