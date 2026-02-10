# Task 131: Sandbox Mode Permanently Broken — Payment Provider Validator Rejects Sandbox Configuration

## Metadata
- **Task ID:** TASK-131
- **Source:** Backend Subscription & Billing Audit (Finding #7 under P1 High)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P1 High
- **Category:** broken-functionality
- **Effort Estimate:** small (< 1 hour)

---

## Description

The LemonSqueezy payment provider cannot be configured in sandbox/test mode due to a logical contradiction between two files. In `src/providers/payment/provider_factory.py` (line 45), the `sandbox_mode` flag is determined by checking if the payment provider string equals `"lemonsqueezy_sandbox"`:

```python
sandbox_mode=(payment_settings.payment_provider == "lemonsqueezy_sandbox")
```

However, in `src/config/payment_config.py` (line 12), the `payment_provider` field is constrained to only accept the literal value `"lemonsqueezy"` via a `Literal` type and a `@field_validator`:

```python
PaymentProviderType = Literal["lemonsqueezy"]
```

And line 35-44:
```python
@field_validator("payment_provider")
@classmethod
def validate_payment_provider(cls, v: str) -> str:
    if v != "lemonsqueezy":
        raise ValueError(
            f"Invalid payment provider: {v}. Only 'lemonsqueezy' is supported. "
            f"Mock payment provider has been removed."
        )
    return v
```

Setting `PAYMENT_PROVIDER=lemonsqueezy_sandbox` in the environment causes a `ValueError` during application startup because the validator explicitly rejects any value other than `"lemonsqueezy"`. This means `sandbox_mode` is **always** `False`, and LemonSqueezy's test mode can never be enabled through configuration.

Additionally, the `LemonSqueezyProvider` class (`src/providers/payment/providers/lemonsqueezy.py:62-76`) accepts `sandbox_mode` as a constructor parameter and stores it as `self.sandbox_mode`, but never actually uses it anywhere in the class — the `sandbox_mode` flag has no effect on API calls, URLs, or behavior even if it could be set to `True`. Furthermore, there's a reference in `src/api/routes/admin/refund_routes.py:52` to `settings.LEMONSQUEEZY_SANDBOX_MODE`, suggesting an alternative approach was attempted but never integrated into the provider factory.

LemonSqueezy's test mode is controlled by using test-mode API keys and test-mode stores. The same API endpoint (`https://api.lemonsqueezy.com/v1`) is used for both production and test mode — the API key determines which mode is active. This means `sandbox_mode` as a concept should control which API key is used, not which URL to hit.

---

## Current Code

```python
# File: src/config/payment_config.py
# Lines: 12-44
PaymentProviderType = Literal["lemonsqueezy"]


class PaymentSettings(BaseSettings):
    """Payment provider settings"""

    # Provider selection (only lemonsqueezy supported)
    payment_provider: PaymentProviderType = "lemonsqueezy"

    # ... other settings ...

    @field_validator("payment_provider")
    @classmethod
    def validate_payment_provider(cls, v: str) -> str:
        """Validate that only lemonsqueezy is used as payment provider"""
        if v != "lemonsqueezy":
            raise ValueError(
                f"Invalid payment provider: {v}. Only 'lemonsqueezy' is supported. "
                f"Mock payment provider has been removed."
            )
        return v
```

```python
# File: src/providers/payment/provider_factory.py
# Lines: 40-46
            return LemonSqueezyProvider(
                api_key=payment_settings.lemonsqueezy_api_key,
                store_id=payment_settings.lemonsqueezy_store_id,
                webhook_secret=payment_settings.lemonsqueezy_webhook_secret,
                sandbox_mode=(payment_settings.payment_provider == "lemonsqueezy_sandbox")
            )
```

---

## Why This Matters (Context & Reasoning)

LemonSqueezy is the sole payment provider for the Rext AI platform. Without sandbox mode, developers must use production API keys during development and testing, which creates several serious risks:

1. **Accidental real charges:** Development/testing operations like creating checkout sessions, processing subscriptions, or triggering webhooks will use real payment processing, potentially charging real credit cards.
2. **No safe testing of webhook flows:** The webhook processing pipeline (subscription creation, payment success/failure, refund handling) cannot be tested without risking real financial transactions.
3. **CI/CD limitations:** Automated tests that involve subscription flows cannot use a sandbox environment, making integration testing unsafe.
4. **Developer onboarding friction:** New developers need production API keys to work on billing features.

LemonSqueezy provides a built-in test mode: when an API key is generated from a test-mode store (or a "test" API key is used), all operations go through the same API endpoint but use test data. The correct approach is to add a separate boolean config field for sandbox mode and use different API key/store ID environment variables for test vs production.

---

## Impact

- **Severity:** All development and testing of the billing system must use production LemonSqueezy credentials, risking real financial transactions. Sandbox mode cannot be enabled under any configuration.
- **Affected Users/Flows:** All developer workflows involving billing features, CI/CD pipeline, staging environments, QA testing of subscription/checkout/webhook flows.
- **Blast Radius:** Affects the entire billing/subscription development workflow. Does not impact production users directly (production correctly uses non-sandbox mode), but severely impacts development velocity and safety.

---

## Recommended Solution

The recommended approach is to add a dedicated `PAYMENT_SANDBOX_MODE` boolean configuration field rather than overloading the provider name string. This is cleaner and follows the existing pattern used in `refund_routes.py` which already references `LEMONSQUEEZY_SANDBOX_MODE`.

### Step 1: Add sandbox mode configuration field

```python
# File: src/config/payment_config.py
# Replace the entire file with:

"""
Payment Provider Configuration

This module handles configuration for the LemonSqueezy payment provider.
"""

from typing import Literal
from pydantic_settings import BaseSettings
from pydantic import field_validator


PaymentProviderType = Literal["lemonsqueezy"]


class PaymentSettings(BaseSettings):
    """Payment provider settings"""

    # Provider selection (only lemonsqueezy supported)
    payment_provider: PaymentProviderType = "lemonsqueezy"

    # Sandbox/test mode toggle
    payment_sandbox_mode: bool = False

    # Generic settings
    payment_currency: str = "USD"
    payment_success_url: str = "http://localhost:3000/checkout/success"
    payment_cancel_url: str = "http://localhost:3000/pricing"

    # LemonSqueezy configuration (production)
    lemonsqueezy_api_key: str = ""
    lemonsqueezy_store_id: str = ""
    lemonsqueezy_webhook_secret: str = ""

    # Webhook Security (Phase 2, Task CRITICAL-4)
    webhook_ip_validation_enabled: bool = True
    lemonsqueezy_webhook_ips: str = "159.223.172.0/24"  # Comma-separated IPs/CIDR ranges

    @field_validator("payment_provider")
    @classmethod
    def validate_payment_provider(cls, v: str) -> str:
        """Validate that only lemonsqueezy is used as payment provider"""
        if v != "lemonsqueezy":
            raise ValueError(
                f"Invalid payment provider: {v}. Only 'lemonsqueezy' is supported. "
                f"Mock payment provider has been removed."
            )
        return v

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


# Global settings instance
payment_settings = PaymentSettings()
```

### Step 2: Update provider factory to use the new config field

```python
# File: src/providers/payment/provider_factory.py
# Replace lines 40-46 with:

            # Initialize with configuration from settings
            return LemonSqueezyProvider(
                api_key=payment_settings.lemonsqueezy_api_key,
                store_id=payment_settings.lemonsqueezy_store_id,
                webhook_secret=payment_settings.lemonsqueezy_webhook_secret,
                sandbox_mode=payment_settings.payment_sandbox_mode
            )
```

### Step 3: Log sandbox mode status on startup

```python
# File: src/providers/payment/provider_factory.py
# After line 28, add a warning log when sandbox mode is active:

    if payment_settings.payment_sandbox_mode:
        logger.warning(
            "Payment provider initialized in SANDBOX MODE. "
            "No real charges will be processed."
        )
```

### Step 4: Add environment variable documentation

Add to `.env.example` (or equivalent):

```bash
# Payment Sandbox Mode (set to true for development/testing)
# Uses LemonSqueezy test mode - ensure API key is a test-mode key
PAYMENT_SANDBOX_MODE=false
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/admin/refund_routes.py` | 52 | References `settings.LEMONSQUEEZY_SANDBOX_MODE` — should be updated to use `payment_settings.payment_sandbox_mode` |
| `src/providers/payment/providers/lemonsqueezy.py` | 76, 89-92 | Stores `self.sandbox_mode` but never uses it — consider logging or adjusting behavior based on mode |
| `.env` / `.env.example` | N/A | Add `PAYMENT_SANDBOX_MODE=false` documentation |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Set environment variable: `PAYMENT_PROVIDER=lemonsqueezy_sandbox`
2. Start the application: `uvicorn src.main:app`
3. Observe: Application fails to start with `ValueError: Invalid payment provider: lemonsqueezy_sandbox`
4. Alternatively, check that `sandbox_mode` is always `False`:
   - Set `PAYMENT_PROVIDER=lemonsqueezy` (default)
   - Add a debug log in `provider_factory.py` after line 45: `logger.info(f"sandbox_mode={payment_settings.payment_provider == 'lemonsqueezy_sandbox'}")`
   - Confirm it always logs `sandbox_mode=False`

### After Fix (Verify the Solution):
1. Set `PAYMENT_SANDBOX_MODE=true` in `.env`
2. Start the application
3. Verify the warning log appears: `"Payment provider initialized in SANDBOX MODE"`
4. Check that `LemonSqueezyProvider` receives `sandbox_mode=True`:
   - Add temporary debug log or use debugger to verify `self.sandbox_mode` is `True`
5. Set `PAYMENT_SANDBOX_MODE=false` (or omit it)
6. Verify the provider initializes normally without the sandbox warning

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "payment or provider or subscription" -v
```

---

## Acceptance Criteria

- [ ] New `PAYMENT_SANDBOX_MODE` environment variable controls sandbox mode (boolean, defaults to `false`)
- [ ] Setting `PAYMENT_SANDBOX_MODE=true` correctly passes `sandbox_mode=True` to `LemonSqueezyProvider`
- [ ] The `PaymentProviderType` validator no longer blocks sandbox mode (no need to set `lemonsqueezy_sandbox`)
- [ ] A warning log is emitted when sandbox mode is active
- [ ] The `refund_routes.py` reference to `LEMONSQUEEZY_SANDBOX_MODE` is updated to use the new config
- [ ] Application starts successfully with `PAYMENT_SANDBOX_MODE=true`
- [ ] Application starts successfully with `PAYMENT_SANDBOX_MODE=false` (default)
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** https://docs.lemonsqueezy.com/guides/developer-guide/testing — LemonSqueezy Testing Guide (test mode API keys)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** https://docs.pydantic.dev/latest/concepts/pydantic_settings/ — Pydantic Settings documentation for environment variable configuration
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-124 (APScheduler Not Declared in Dependencies — both are "infrastructure broken" findings in B5)
