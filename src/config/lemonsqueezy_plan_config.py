"""
Helpers for loading LemonSqueezy plan identifiers from environment variables.

Each paid plan's product/variant/store IDs are resolved from env vars named
after the plan, e.g. for plan "starter":
    LEMONSQUEEZY_STARTER_PRODUCT_ID
    LEMONSQUEEZY_STARTER_VARIANT_ID_MONTHLY
    LEMONSQUEEZY_STARTER_VARIANT_ID_YEARLY
    LEMONSQUEEZY_STARTER_STORE_ID (optional, falls back to LEMONSQUEEZY_STORE_ID)

This lets stage and main point at different LemonSqueezy stores (test vs
live mode) using the same variable names, with only the values differing
per environment.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class LemonSqueezyPlanConfig:
    """Resolved LemonSqueezy identifiers for a single subscription plan."""

    product_id: str | None
    variant_id_monthly: str | None
    variant_id_yearly: str | None
    store_id: str | None

    @property
    def is_configured(self) -> bool:
        return bool(self.product_id and self.variant_id_monthly and self.variant_id_yearly)


def _normalize(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _plan_env_token(plan_name: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", plan_name.strip().upper()).strip("_")


def get_plan_env_var_names(plan_name: str) -> dict[str, str]:
    """Return the env var names used for a given plan."""
    token = _plan_env_token(plan_name)
    return {
        "product_id": f"LEMONSQUEEZY_{token}_PRODUCT_ID",
        "variant_id_monthly": f"LEMONSQUEEZY_{token}_VARIANT_ID_MONTHLY",
        "variant_id_yearly": f"LEMONSQUEEZY_{token}_VARIANT_ID_YEARLY",
        "store_id": f"LEMONSQUEEZY_{token}_STORE_ID",
        "global_store_id": "LEMONSQUEEZY_STORE_ID",
    }


def get_plan_config_from_env(
    plan_name: str,
    environ: Mapping[str, str] | None = None,
) -> LemonSqueezyPlanConfig:
    """
    Resolve LemonSqueezy IDs for a plan from environment variables.

    Returns a config with whatever fields are present; missing fields are
    left as None. Callers should check `.is_configured` before relying on
    the result for checkout/webhook logic.
    """
    env = environ if environ is not None else os.environ
    names = get_plan_env_var_names(plan_name)

    return LemonSqueezyPlanConfig(
        product_id=_normalize(env.get(names["product_id"])),
        variant_id_monthly=_normalize(env.get(names["variant_id_monthly"])),
        variant_id_yearly=_normalize(env.get(names["variant_id_yearly"])),
        store_id=_normalize(env.get(names["store_id"]))
        or _normalize(env.get(names["global_store_id"])),
    )


def get_configured_plan_mapping(
    plan_names: Iterable[str],
    environ: Mapping[str, str] | None = None,
) -> dict[str, LemonSqueezyPlanConfig]:
    """Return configs only for plans that have complete LemonSqueezy env values."""
    mapping: dict[str, LemonSqueezyPlanConfig] = {}
    for plan_name in plan_names:
        config = get_plan_config_from_env(plan_name, environ)
        if config.is_configured:
            mapping[plan_name] = config
    return mapping
