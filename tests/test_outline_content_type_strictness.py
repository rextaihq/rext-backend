import pytest

from src.flow.model.structure.content_types import normalize_content_type
from src.flow.model.structure.outlines import get_outline_model
from src.flow.model.structure.outlines.base import BaseOutline
from src.flow.model.structure.outlines.infomational.blog import BlogOutline


@pytest.mark.unit
def test_normalize_content_type_aliases_and_separators():
    assert normalize_content_type("coupon_page") == "coupon-page"
    assert normalize_content_type("Coupon Page") == "coupon-page"
    assert normalize_content_type("ARTICLE") == "blog"


@pytest.mark.unit
def test_normalize_content_type_rejects_unknown():
    with pytest.raises(ValueError):
        normalize_content_type("not-a-real-type")


@pytest.mark.unit
def test_get_outline_model_normalizes_and_is_strict():
    model = get_outline_model("coupon_page")
    assert model.__name__ == "CouponPageOutline"

    with pytest.raises(ValueError):
        get_outline_model("not-a-real-type")


@pytest.mark.unit
def test_outline_schemas_require_content_type():
    assert "content_type" in (BaseOutline.model_json_schema().get("required") or [])
    assert "content_type" in (BlogOutline.model_json_schema().get("required") or [])

