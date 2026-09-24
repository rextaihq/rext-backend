from src.api.schema.response_schemas import ResponseMeta


def test_response_meta_timestamp_is_timezone_aware() -> None:
    meta = ResponseMeta(request_id="req_test_12345")
    assert meta.timestamp.tzinfo is not None
    assert meta.timestamp.utcoffset() is not None
