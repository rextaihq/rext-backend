"""
Helpers for loading LemonSqueezy plan identifiers from environment variables.
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
        return any(
            value is not None
            for value in (
                self.product_id,
                self.variant_id_monthly,
                self.variant_id_yearly,
                self.store_id,
            )
        )


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
    *,
    require_complete: bool = False,
) -> LemonSqueezyPlanConfig:
    """
    Resolve LemonSqueezy IDs for a plan from environment variables.

    Expected naming convention:
    - ``LEMONSQUEEZY_<PLAN>_PRODUCT_ID``
    - ``LEMONSQUEEZY_<PLAN>_VARIANT_ID_MONTHLY``
    - ``LEMONSQUEEZY_<PLAN>_VARIANT_ID_YEARLY``
    - optional ``LEMONSQUEEZY_<PLAN>_STORE_ID`` or global ``LEMONSQUEEZY_STORE_ID``
    """
    env = environ or os.environ
    names = get_plan_env_var_names(plan_name)

    config = LemonSqueezyPlanConfig(
        product_id=_normalize(env.get(names["product_id"])),
        variant_id_monthly=_normalize(env.get(names["variant_id_monthly"])),
        variant_id_yearly=_normalize(env.get(names["variant_id_yearly"])),
        store_id=_normalize(env.get(names["store_id"])) or _normalize(env.get(names["global_store_id"])),
    )

    required_fields = {
        "product_id": config.product_id,
        "variant_id_monthly": config.variant_id_monthly,
        "variant_id_yearly": config.variant_id_yearly,
    }
    present_fields = [field for field, value in required_fields.items() if value is not None]

    if present_fields and len(present_fields) != len(required_fields):
        missing_names = [
            names[field]
            for field, value in required_fields.items()
            if value is None
        ]
        raise ValueError(
            f"Incomplete LemonSqueezy configuration for plan '{plan_name}'. "
            f"Missing env vars: {', '.join(missing_names)}"
        )

    if require_complete and not present_fields:
        raise ValueError(
            f"Missing LemonSqueezy configuration for plan '{plan_name}'. "
            f"Expected env vars: {names['product_id']}, {names['variant_id_monthly']}, {names['variant_id_yearly']}"
        )

    return config


def get_configured_plan_mapping(
    plan_names: Iterable[str],
    environ: Mapping[str, str] | None = None,
) -> dict[str, LemonSqueezyPlanConfig]:
    """Return configs only for plans that have complete LemonSqueezy env values."""
    mapping: dict[str, LemonSqueezyPlanConfig] = {}
    for plan_name in plan_names:
        config = get_plan_config_from_env(plan_name, environ)
        if config.product_id and config.variant_id_monthly and config.variant_id_yearly:
            mapping[plan_name] = config
    return mapping
