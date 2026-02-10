# Task 154: Debug Log Statements with Emoji Prefixes in Subscription Service

## Metadata
- **Task ID:** TASK-154
- **Source:** B5 - Subscription & Billing (Finding #35 under P3 Low)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P3 Low
- **Category:** code-quality
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `SubscriptionService` class in `src/services/subscription_service.py` contains five debug-level log statements logged at `INFO` level with emoji prefixes (`🔍 DEBUG:`). These were clearly left behind during development and should not be in production code. The statements are:

- **Line 202:** `logger.info(f"🔍 DEBUG: User has existing subscription on plan: {existing_subscription.plan.name}")`
- **Line 207:** `logger.info(f"🔍 DEBUG: Plan is not free/trial ({existing_subscription.plan.name}), blocking checkout")`
- **Line 214:** `logger.info(f"🔍 DEBUG: Plan is {existing_subscription.plan.name}, allowing checkout to proceed")`
- **Line 232:** `logger.info(f"🔍 DEBUG: Variant ID is {variant_id}")`
- **Line 270:** `logger.info(f"🔍 DEBUG: Customer ID is {customer_id}")`

These statements are problematic for three reasons:

1. **Log level mismatch:** Debug-level information is logged at `INFO` level. In production, `INFO` logs are typically always enabled while `DEBUG` logs are filtered out. This means these debug messages pollute production logs with noise that should only be visible during development.

2. **Potential data exposure:** The logs emit subscription plan names, variant IDs, and customer IDs (which are LemonSqueezy customer identifiers) at the INFO level. While not directly PII, these are internal business identifiers that could aid an attacker in understanding the system's payment infrastructure if logs are compromised or exposed.

3. **Emoji characters in logs:** Emoji prefixes (`🔍`) can cause issues with some log aggregation systems, monitoring tools, and terminal environments that don't handle Unicode well. They also make structured log searching harder (grepping for "DEBUG" would find both these fake debug messages and actual debug-level logs).

The audit report describes these as `print()` statements, but the actual code uses `logger.info()` with f-strings — which is equally problematic because f-strings in logger calls evaluate their expressions eagerly regardless of whether the log level is enabled, adding unnecessary computation overhead.

---

## Current Code

```python
# File: src/services/subscription_service.py
# Line 202
            logger.info(f"🔍 DEBUG: User has existing subscription on plan: {existing_subscription.plan.name}")

# Line 207
                logger.info(f"🔍 DEBUG: Plan is not free/trial ({existing_subscription.plan.name}), blocking checkout")

# Line 214
            logger.info(f"🔍 DEBUG: Plan is {existing_subscription.plan.name}, allowing checkout to proceed")

# Line 232
        logger.info(f"🔍 DEBUG: Variant ID is {variant_id}")

# Line 270
        logger.info(f"🔍 DEBUG: Customer ID is {customer_id}")
```

---

## Why This Matters (Context & Reasoning)

The `SubscriptionService.create_checkout()` method is called every time a user initiates a checkout session. This is a high-traffic path in the billing flow. Each checkout request generates 3-5 unnecessary INFO log lines with debug content, polluting the production log stream.

In a structured logging environment (the project uses `structlog` based on `pyproject.toml`), INFO-level logs are typically indexed, stored, and potentially alerted on. Having debug noise at this level increases log storage costs, makes it harder to find meaningful INFO logs, and could trigger false positives in monitoring systems that watch for unusual log patterns.

Additionally, using f-strings directly in logger calls (e.g., `logger.info(f"...")`) defeats Python's lazy log formatting. The standard practice is to use `logger.info("message %s", variable)` with `%`-style formatting, which only evaluates the string interpolation if the log level is actually enabled. However, since the recommendation is to remove these lines entirely (or downgrade to `logger.debug()` with lazy formatting), this point is moot for removal but relevant if converting to debug.

---

## Impact

- **Severity:** Log pollution in production. Minor data exposure risk (internal customer/variant IDs in logs). Performance overhead from eager f-string evaluation on every checkout request.
- **Affected Users/Flows:** Every checkout flow execution produces 3-5 extra INFO log lines.
- **Blast Radius:** Isolated to `subscription_service.py:create_checkout()`. Only affects logging output.

---

## Recommended Solution

Remove all five debug log statements. If any of the information is genuinely useful for troubleshooting, convert to `logger.debug()` with lazy `%`-style formatting.

### Step 1: Remove debug log statements

```python
# File: src/services/subscription_service.py

# DELETE line 202:
# logger.info(f"🔍 DEBUG: User has existing subscription on plan: {existing_subscription.plan.name}")

# DELETE line 207:
# logger.info(f"🔍 DEBUG: Plan is not free/trial ({existing_subscription.plan.name}), blocking checkout")

# DELETE line 214:
# logger.info(f"🔍 DEBUG: Plan is {existing_subscription.plan.name}, allowing checkout to proceed")

# DELETE line 232:
# logger.info(f"🔍 DEBUG: Variant ID is {variant_id}")

# DELETE line 270:
# logger.info(f"🔍 DEBUG: Customer ID is {customer_id}")
```

### Alternative: Convert to proper debug logging

If the team wants to preserve this debugging information for troubleshooting, convert to `logger.debug()` with lazy formatting:

```python
# File: src/services/subscription_service.py

# Replace line 202:
logger.debug("User has existing subscription on plan: %s", existing_subscription.plan.name)

# Replace line 207:
logger.debug("Plan is not free/trial (%s), blocking checkout", existing_subscription.plan.name)

# Replace line 214:
logger.debug("Plan is %s, allowing checkout to proceed", existing_subscription.plan.name)

# Replace line 232:
logger.debug("Variant ID is %s", variant_id)

# Replace line 270:
logger.debug("Customer ID is %s", customer_id)
```

Note: Using `%`-style formatting with `logger.debug()` ensures string interpolation only happens when debug logging is enabled, avoiding unnecessary computation in production.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/services/subscription_service.py` | `53` | Duplicate `from src.utils.logger import logger` import — can be cleaned up while editing this file |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Set log level to INFO.
2. Trigger a checkout flow by calling `POST /api/v1/subscriptions/checkout`.
3. Observe the log output — you'll see multiple lines with `🔍 DEBUG:` prefix at INFO level.

### After Fix (Verify the Solution):
1. Set log level to INFO.
2. Trigger a checkout flow by calling `POST /api/v1/subscriptions/checkout`.
3. Observe the log output — no `🔍 DEBUG:` lines should appear.
4. If using the `logger.debug()` alternative: set log level to DEBUG and verify the messages now appear at DEBUG level without emoji prefixes.

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "subscription" -v
```

---

## Acceptance Criteria

- [ ] All five `logger.info(f"🔍 DEBUG: ...")` lines are removed (or converted to `logger.debug()` with `%`-style formatting)
- [ ] No emoji characters remain in log messages
- [ ] No debug-level content is logged at INFO level
- [ ] The checkout flow still works correctly end-to-end
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Python Logging HOWTO — Optimization](https://docs.python.org/3/howto/logging.html#optimization)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Python Logging Best Practices — Use lazy formatting](https://docs.python.org/3/howto/logging.html#optimization) — "Formatting of message arguments is deferred until it cannot be avoided."
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-127 (Internal Error Messages Leaked to Clients — also in subscription service layer, related to information exposure), TASK-112 (F-String in Logger Calls — same anti-pattern in workspace routes)
