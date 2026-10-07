"""The schema tool's validation errors show the visitor what they typed (G94, revnix/rext-control#766).

The date error was a plain string with a placeholder in it, so rext.ai showed
"date_published must be in MM/DD/YYYY format. Got: {v}" to anyone who typed a date another way.
"""

import pytest
from pydantic import ValidationError

from src.api.tool.schema.schema import SchemaRequest


def _error(**fields) -> str:
    with pytest.raises(ValidationError) as caught:
        SchemaRequest(schema_type="Article", name="A title", **fields)
    return caught.value.errors()[0]["msg"]


def test_a_wrong_date_is_shown_back_with_the_format_to_use():
    message = _error(date_published="2026-10-08")

    assert "Got: 2026-10-08" in message
    assert "MM/DD/YYYY" in message and "10/08/2026" in message
    assert "{" not in message and "}" not in message


def test_a_right_date_and_an_empty_one_pass():
    assert SchemaRequest(schema_type="Article", name="A", date_published="10/08/2026")
    assert (
        SchemaRequest(schema_type="Article", name="A", date_published="  ").date_published is None
    )


@pytest.mark.parametrize("field", ["date_published", "url", "image_url"])
def test_a_long_input_is_shown_back_cut_short(field):
    message = _error(**{field: "x" * 500})

    assert "x" * 40 + "..." in message
    assert "x" * 41 not in message


def test_a_wrong_address_is_still_shown_back():
    assert "Got: not a url" in _error(url="not  a url")
