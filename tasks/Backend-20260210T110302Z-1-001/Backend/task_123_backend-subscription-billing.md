# Task 123: Fix Two Runtime Crash Bugs in Webhook Monitoring Service

## Metadata
- **Task ID:** TASK-123
- **Source:** Backend Subscription & Billing Audit (Finding #4 under P0 Critical)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P0 Critical
- **Category:** bug
- **Effort Estimate:** small (< 1 hour)

---

## Description

The `WebhookMonitoringService` at `src/services/webhook_monitoring_service.py` has two independent runtime crash bugs that make the webhook statistics endpoint and the webhook retry feature completely non-functional.

**Bug 1: Missing `Integer` import (line 386).** The `get_webhook_statistics()` method uses `func.cast(WebhookEvent.processed, Integer)` on line 386 and `func.cast(WebhookEvent.error_message.isnot(None), Integer)` on line 388 to aggregate boolean columns as integers for SUM operations. However, `Integer` is never imported from `sqlalchemy`. The imports at the top of the file (line 12) include `func, and_, or_, desc` from `sqlalchemy` but not `Integer`. This causes a `NameError: name 'Integer' is not defined` whenever `get_webhook_statistics()` is called.

The correct import is `from sqlalchemy import Integer` (or alternatively `from sqlalchemy.types import Integer`). Per the [SQLAlchemy 2.0 documentation](https://docs.sqlalchemy.org/en/20/core/sqlelement.html), `Integer` is a core type available directly from the `sqlalchemy` module.

**Bug 2: Wrong method name in retry (line 268).** The `retry_webhook()` method calls `self.webhook_service.process_webhook_event()` on line 268, but `LemonSqueezyWebhookService` at `src/services/lemonsqueezy_webhook_service.py:76` defines the method as `process_webhook()` — not `process_webhook_event()`. This causes an `AttributeError: 'LemonSqueezyWebhookService' object has no attribute 'process_webhook_event'` whenever `retry_webhook()` is called.

Additionally, the method signatures don't match. The call at line 268-272 passes `event_id`, `event_name`, and `payload` as keyword arguments:
```python
await self.webhook_service.process_webhook_event(
    event_id=event.event_id,
    event_name=event.event_name,
    payload=event.payload
)
```
But `process_webhook()` accepts `payload: bytes` and `signature: str` as parameters (line 76-79). The retry code would need to either (a) call the method with the correct parameters, or (b) use a different method that accepts already-parsed payload data.

---

## Current Code

```python
# File: src/services/webhook_monitoring_service.py
# Lines: 1-18 — Imports (Integer is missing)
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy import func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.api.models.subscription_models.webhooks import WebhookEvent
from src.services.lemonsqueezy_webhook_service import LemonSqueezyWebhookService
from src.utils.logger import logger
```

```python
# File: src/services/webhook_monitoring_service.py
# Lines: 383-389 — func.cast uses undefined Integer
            stmt_by_type = select(
                WebhookEvent.event_name,
                func.count(WebhookEvent.id).label('count'),
                func.sum(func.cast(WebhookEvent.processed, Integer)).label('processed'),
                func.sum(
                    func.cast(WebhookEvent.error_message.isnot(None), Integer)
                ).label('failed')
            ).group_by(WebhookEvent.event_name)
```

```python
# File: src/services/webhook_monitoring_service.py
# Lines: 267-272 — Wrong method name
                # Process the webhook using the webhook service
                await self.webhook_service.process_webhook_event(
                    event_id=event.event_id,
                    event_name=event.event_name,
                    payload=event.payload
                )
```

```python
# File: src/services/lemonsqueezy_webhook_service.py
# Lines: 76-80 — Actual method signature
    async def process_webhook(
        self,
        payload: bytes,
        signature: str
    ) -> Dict[str, Any]:
```

---

## Why This Matters (Context & Reasoning)

The webhook monitoring service provides visibility into the health of the LemonSqueezy webhook integration — the critical pipeline through which all payment events (subscription created, updated, cancelled, payment failed, refunded) flow into the system. Without working statistics, admins have no way to know if webhooks are being processed correctly, what the failure rate is, or which event types are problematic.

The retry feature is the only mechanism to recover from webhook processing failures. When a webhook fails (e.g., due to a transient database error or a bug), the admin needs to retry it to ensure the subscription state stays synchronized with LemonSqueezy. Without working retry, failed webhooks remain permanently stuck, leading to subscription state drift (e.g., a user cancels on LemonSqueezy but the local database still shows them as active).

Both bugs are straightforward to fix (one import addition, one method name correction), but the impact of leaving them unfixed is significant: no webhook health monitoring and no failure recovery.

---

## Impact

- **Severity:** The webhook statistics endpoint returns HTTP 500 for every request. The webhook retry feature crashes for every attempt. Admins cannot monitor webhook health or recover from failures.
- **Affected Users/Flows:** Admin users accessing webhook monitoring dashboard. Any workflow that relies on webhook retry for failure recovery. Indirectly affects all subscription lifecycle events if failed webhooks cannot be retried.
- **Blast Radius:** All webhook monitoring admin endpoints that depend on `get_webhook_statistics()` or `retry_webhook()`. The core webhook processing pipeline (`process_webhook`) is NOT affected — only the monitoring/retry layer.

---

## Recommended Solution

### Step 1: Add `Integer` to the SQLAlchemy imports

```python
# File: src/services/webhook_monitoring_service.py
# Replace line 12:
from sqlalchemy import func, and_, or_, desc
# With:
from sqlalchemy import func, and_, or_, desc, Integer
```

### Step 2: Fix the retry method to call the correct service method

The `process_webhook()` method on `LemonSqueezyWebhookService` expects raw `payload: bytes` and `signature: str`. For a retry scenario, we have the already-parsed payload stored in the database (as a dict/JSON) but not the original signature. The retry should reprocess the stored event data directly, bypassing signature verification (since the event was already verified when it was first received).

The cleanest approach is to check if `LemonSqueezyWebhookService` has a method for processing an already-verified event. If not, we need to route the event through the handler registry directly.

Looking at the webhook service, `process_webhook()` does: (1) verify signature, (2) parse payload, (3) check idempotency, (4) log event, (5) route to handler. For retry, we should skip steps 1-2 (already done) and go directly to the handler routing.

```python
# File: src/services/webhook_monitoring_service.py
# Replace lines 262-272 with:

            # Attempt to reprocess
            logger.info(f"Retrying webhook event: {webhook_id} (event_name: {event.event_name})")

            try:
                # Increment retry count
                event.retry_count += 1
                event.updated_at = datetime.utcnow()

                # For retry, we route directly to the event handler since the payload
                # is already parsed and was previously signature-verified.
                # We use the webhook service's internal handler routing.
                import json
                payload_bytes = json.dumps(event.payload).encode('utf-8') if isinstance(event.payload, dict) else event.payload

                # Use a bypass signature for retry (signature already verified on first receipt)
                # The webhook service's route_event method handles the actual processing
                from src.services.webhook_handlers.subscription_handlers import SubscriptionWebhookHandlers
                from src.services.webhook_handlers.order_handlers import OrderWebhookHandlers

                # Initialize handlers
                subscription_handlers = SubscriptionWebhookHandlers(self.db)
                order_handlers = OrderWebhookHandlers(self.db)

                # Route to appropriate handler based on event name
                event_name = event.event_name
                handler = None
                if hasattr(subscription_handlers, f'handle_{event_name}'):
                    handler = getattr(subscription_handlers, f'handle_{event_name}')
                elif hasattr(order_handlers, f'handle_{event_name}'):
                    handler = getattr(order_handlers, f'handle_{event_name}')

                if handler:
                    await handler(event.payload)
                else:
                    raise ValueError(f"No handler found for event: {event_name}")
```

**Alternative simpler approach** — If the handler routing above is too complex or the handler classes don't follow a `handle_{event_name}` convention, a simpler fix is to just correct the method name and adapt the parameters:

```python
# File: src/services/webhook_monitoring_service.py
# Replace lines 268-272 with:

                # Reprocess by calling the webhook service
                # Note: For retry, we serialize the stored payload back to bytes
                # and skip signature verification by passing directly to handlers
                import json
                payload_bytes = json.dumps(event.payload).encode('utf-8') if isinstance(event.payload, dict) else event.payload

                # Create a dummy signature for retry (original was already verified)
                # TODO: Store original signature in WebhookEvent model for proper retry
                logger.warning(
                    f"Retrying webhook {webhook_id} without signature verification "
                    f"(original signature not stored)"
                )
                await self.webhook_service.process_webhook(
                    payload=payload_bytes,
                    signature=""  # Signature verification will fail — need to add a skip_verification parameter
                )
```

**Recommended: Add a retry-specific method to the webhook service** for the cleanest solution:

```python
# File: src/services/lemonsqueezy_webhook_service.py
# Add after the process_webhook method:

    async def reprocess_event(
        self,
        event_name: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Reprocess a previously-received webhook event.

        This skips signature verification and idempotency checks since the event
        was already verified on initial receipt. Used for admin retry operations.

        Args:
            event_name: The webhook event name (e.g., "subscription_created")
            payload: The parsed webhook payload (dict)

        Returns:
            Dict with processing result
        """
        logger.info(f"Reprocessing webhook event: {event_name}")

        # Route to appropriate handler
        handler = self._handlers.get(event_name)
        if handler:
            await handler(payload)
            return {"success": True, "event_name": event_name, "message": "Reprocessed successfully"}
        else:
            raise ValueError(f"No handler registered for event: {event_name}")
```

Then update the monitoring service:

```python
# File: src/services/webhook_monitoring_service.py
# Replace lines 268-272 with:

                await self.webhook_service.reprocess_event(
                    event_name=event.event_name,
                    payload=event.payload
                )
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/subscriptions/admin/webhook_monitoring_routes.py` | All endpoints | Admin routes that call `WebhookMonitoringService` — these will work once the service is fixed |
| `src/services/lemonsqueezy_webhook_service.py` | 76-99 | The `process_webhook()` method — correct method name, needs potential `reprocess_event()` addition for retry support |
| `src/api/models/subscription_models/webhooks.py` | All | The `WebhookEvent` model — the `processed` and `error_message` fields used in the statistics query |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Authenticate as a super admin user.
2. Call the webhook statistics endpoint `GET /api/v1/subscriptions/admin/webhooks/statistics` — observe HTTP 500 with `NameError: name 'Integer' is not defined`.
3. If there are any failed webhook events, call the retry endpoint `POST /api/v1/subscriptions/admin/webhooks/{webhook_id}/retry` — observe HTTP 500 with `AttributeError: 'LemonSqueezyWebhookService' object has no attribute 'process_webhook_event'`.

### After Fix (Verify the Solution):
1. Call `GET /api/v1/subscriptions/admin/webhooks/statistics` — expect HTTP 200 with statistics JSON including `total_events`, `processed`, `failed`, `success_rate`, `by_event_type`.
2. Create a test webhook event in the database with `processed=False` and an `error_message`.
3. Call `POST /api/v1/subscriptions/admin/webhooks/{webhook_id}/retry` — expect HTTP 200 with retry result.
4. Verify the webhook event is now marked as `processed=True` (if the handler succeeds) or has an updated `error_message` (if it fails again).

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -v -k "webhook" --no-header
```

---

## Acceptance Criteria

- [ ] `Integer` is imported from `sqlalchemy` at the top of `webhook_monitoring_service.py`
- [ ] `get_webhook_statistics()` returns valid statistics without NameError
- [ ] `retry_webhook()` calls the correct method on `LemonSqueezyWebhookService` (either `reprocess_event()` if added, or adapted call to `process_webhook()`)
- [ ] Webhook retry successfully reprocesses failed events
- [ ] Statistics endpoint correctly aggregates processed/failed counts per event type
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [SQLAlchemy 2.0 - Column Elements and Expressions](https://docs.sqlalchemy.org/en/20/core/sqlelement.html) — Documentation for `func.cast()` and type imports including `Integer`
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [SQLAlchemy 2.0 - SQL Expression Language Tutorial](https://docs.sqlalchemy.org/en/20/tutorial/data_select.html) — Correct patterns for aggregation queries with type casting
- **Related Issues/PRs:** [SQLAlchemy Issue #9451 - cast(Integer) typing](https://github.com/sqlalchemy/sqlalchemy/issues/9451) — Related discussion on `cast(Integer)` usage patterns

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-120 (Missing admin auth on export endpoints — same admin security pattern), TASK-122 (Export service crashes — similar pattern of service-level runtime errors in the billing system)
