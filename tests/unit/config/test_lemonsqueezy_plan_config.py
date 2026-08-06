from src.config.lemonsqueezy_plan_config import (
    get_configured_plan_mapping,
    get_plan_config_from_env,
    get_plan_env_var_names,
)


def test_get_plan_env_var_names_normalizes_plan_name():
    env_names = get_plan_env_var_names("starter-plus")

    assert env_names["product_id"] == "LEMONSQUEEZY_STARTER_PLUS_PRODUCT_ID"
    assert env_names["variant_id_monthly"] == "LEMONSQUEEZY_STARTER_PLUS_VARIANT_ID_MONTHLY"
    assert env_names["variant_id_yearly"] == "LEMONSQUEEZY_STARTER_PLUS_VARIANT_ID_YEARLY"
    assert env_names["store_id"] == "LEMONSQUEEZY_STARTER_PLUS_STORE_ID"


def test_get_plan_config_from_env_uses_global_store_fallback():
    config = get_plan_config_from_env(
        "pro",
        {
            "LEMONSQUEEZY_PRO_PRODUCT_ID": "prod_1",
            "LEMONSQUEEZY_PRO_VARIANT_ID_MONTHLY": "month_1",
            "LEMONSQUEEZY_PRO_VARIANT_ID_YEARLY": "year_1",
            "LEMONSQUEEZY_STORE_ID": "store_global",
        },
    )

    assert config.product_id == "prod_1"
    assert config.variant_id_monthly == "month_1"
    assert config.variant_id_yearly == "year_1"
    assert config.store_id == "store_global"


def test_get_plan_config_from_env_rejects_partial_configuration():
    try:
        get_plan_config_from_env(
            "growth",
            {
                "LEMONSQUEEZY_GROWTH_PRODUCT_ID": "prod_growth",
                "LEMONSQUEEZY_GROWTH_VARIANT_ID_MONTHLY": "month_growth",
            },
        )
    except ValueError as exc:
        assert "LEMONSQUEEZY_GROWTH_VARIANT_ID_YEARLY" in str(exc)
    else:
        raise AssertionError("Expected partial LemonSqueezy plan configuration to fail")


def test_get_configured_plan_mapping_supports_multiple_plans_with_both_billing_periods():
    mapping = get_configured_plan_mapping(
        ["basic", "pro", "agency"],
        {
            "LEMONSQUEEZY_BASIC_PRODUCT_ID": "prod_basic",
            "LEMONSQUEEZY_BASIC_VARIANT_ID_MONTHLY": "basic_month",
            "LEMONSQUEEZY_BASIC_VARIANT_ID_YEARLY": "basic_year",
            "LEMONSQUEEZY_PRO_PRODUCT_ID": "prod_pro",
            "LEMONSQUEEZY_PRO_VARIANT_ID_MONTHLY": "pro_month",
            "LEMONSQUEEZY_PRO_VARIANT_ID_YEARLY": "pro_year",
            "LEMONSQUEEZY_AGENCY_PRODUCT_ID": "",
            "LEMONSQUEEZY_AGENCY_VARIANT_ID_MONTHLY": "",
            "LEMONSQUEEZY_AGENCY_VARIANT_ID_YEARLY": "",
        },
    )

    assert list(mapping.keys()) == ["basic", "pro"]
    assert mapping["basic"].product_id == "prod_basic"
    assert mapping["basic"].variant_id_monthly == "basic_month"
    assert mapping["basic"].variant_id_yearly == "basic_year"
    assert mapping["pro"].product_id == "prod_pro"
    assert mapping["pro"].variant_id_monthly == "pro_month"
    assert mapping["pro"].variant_id_yearly == "pro_year"


def test_get_configured_plan_mapping_returns_only_complete_plans():
    mapping = get_configured_plan_mapping(
        ["starter", "agency"],
        {
            "LEMONSQUEEZY_STARTER_PRODUCT_ID": "prod_starter",
            "LEMONSQUEEZY_STARTER_VARIANT_ID_MONTHLY": "starter_month",
            "LEMONSQUEEZY_STARTER_VARIANT_ID_YEARLY": "starter_year",
            "LEMONSQUEEZY_AGENCY_PRODUCT_ID": "",
            "LEMONSQUEEZY_AGENCY_VARIANT_ID_MONTHLY": "",
            "LEMONSQUEEZY_AGENCY_VARIANT_ID_YEARLY": "",
        },
    )

    assert list(mapping.keys()) == ["starter"]
