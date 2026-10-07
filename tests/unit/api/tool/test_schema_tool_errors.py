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


# -- What the visitor typed is shown to them, and never kept in the error log -----------


def _recorded(**fields) -> list[dict]:
    from src.api.middleware.error_handler import _validation_error_metadata

    with pytest.raises(ValidationError) as caught:
        SchemaRequest(schema_type="Article", name="A title", **fields)
    return _validation_error_metadata(caught.value)["invalid_fields"]


@pytest.mark.parametrize("field", ["date_published", "url", "image_url"])
def test_the_error_log_never_keeps_what_was_typed(field):
    typed = "sk-live-a-token-pasted-by-mistake"

    (row,) = _recorded(**{field: typed})

    assert row["field"] == field and row["rule"] == "value_error"
    assert "pasted" not in row["message"] and "sk-live" not in row["message"]
    assert row["message"].endswith("Got: [not recorded]")


def test_a_message_that_repeats_the_input_whole_is_recorded_without_it():
    from src.api.middleware.error_handler import _message_without_input

    err = {"msg": "Value error, 'hunter2!' is not allowed here", "input": "hunter2!"}

    assert _message_without_input(err) == "Value error, '[not recorded]' is not allowed here"
    # A built-in message quotes nothing and is recorded as it is.
    assert _message_without_input({"msg": "Field required", "input": {}}) == "Field required"
