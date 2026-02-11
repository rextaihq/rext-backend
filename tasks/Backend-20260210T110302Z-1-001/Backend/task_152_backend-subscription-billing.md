# Task 152: Path Parameters Typed as `str` Instead of `UUID`

## Metadata
- **Task ID:** TASK-152
- **Source:** B5 - Subscription & Billing (Finding #34 under P3 Low)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P3 Low
- **Category:** broken-functionality
- **Effort Estimate:** small (< 1 hour)

---

## Description

Several subscription and license route endpoints accept path parameters typed as `str` (e.g., `subscription_id: str`, `license_id: str`) instead of using Python's `UUID` type annotation. FastAPI integrates with Pydantic's validation system to automatically validate path parameters based on their type annotations. When a parameter is typed as `UUID`, FastAPI validates the incoming string against the UUID format before the route handler executes, returning a clean HTTP 422 response with a detailed validation error if the format is invalid.

With `str` typing, any arbitrary string passes through to the route handler. The invalid value only fails later — typically deep in the service layer when SQLAlchemy attempts to use it in a database query against a UUID column, or when explicit `UUID(subscription_id)` conversion is called in the handler. This produces confusing error messages like `ValueError: badly formed hexadecimal UUID string` at line 77 of `admin_subscription_management.py` rather than a clean 422 validation error at the API boundary.

The affected endpoints are:

1. `trial_routes.py:94` — `subscription_id: str` in `POST /{subscription_id}/extend`
2. `admin_subscription_management.py:65` — `subscription_id: str` in `POST /{subscription_id}/extend`
3. `admin_subscription_management.py:92` — `subscription_id: str` in `POST /{subscription_id}/reset-usage`
4. `license_routes.py:240` — `license_id: str` in `POST /{license_id}/deactivate`
5. `license_routes.py:340` — `license_id: str` in `GET /{license_id}`
6. `license_routes.py:401` — `license_id: str` in `GET /{license_id}/activations`
7. `license_routes.py:459` — `license_id: str` in `POST /admin/{license_id}/revoke`

In each case, the handlers then manually convert with `UUID(subscription_id)` or `UUID(license_id)`, which is redundant and error-prone. Using `UUID` as the type annotation eliminates the manual conversion and pushes validation to the API boundary where it belongs.

---

## Current Code

```python
# File: src/api/routes/subscriptions/trial_routes.py
# Lines: 89-94
@router.post("/{subscription_id}/extend", response_model=dict, status_code=status.HTTP_200_OK)
@db_transaction_handler("extend trial")
@require_permissions("subscription.manage", workspace_scoped=False)
async def extend_trial_endpoint(
    request: Request,
    subscription_id: str,
```

```python
# File: src/api/routes/subscriptions/admin/admin_subscription_management.py
# Lines: 60-65
@router.post("/{subscription_id}/extend", response_model=dict)
@require_permissions("subscription.manage")
@db_transaction_handler("extend subscription", auto_commit=True)
async def extend_subscription(
    request: Request,
    subscription_id: str,
```

```python
# File: src/api/routes/subscriptions/license_routes.py
# Lines: 235-240
@router.post("/{license_id}/deactivate", response_model=dict, status_code=status.HTTP_200_OK)
@db_transaction_handler("deactivate license")
@require_permissions("license.deactivate", workspace_scoped=False)
async def deactivate_license_endpoint(
    request: Request,
    license_id: str,
```

---

## Why This Matters (Context & Reasoning)

Subscription IDs and license IDs are primary keys used throughout the billing system. Passing invalid UUIDs to these endpoints currently produces unhandled `ValueError` exceptions deep in the service layer, which may be caught by generic error handlers and returned as 500 Internal Server Error responses. This violates the principle of failing fast at the API boundary and provides a poor developer experience for API consumers.

By using FastAPI's built-in UUID validation, invalid requests are rejected immediately with a standardized 422 response that clearly indicates which parameter failed and why. This also eliminates the need for manual `UUID(subscription_id)` conversion calls scattered throughout the handlers, reducing boilerplate code.

The risk of NOT fixing this is that invalid UUID strings produce confusing 500 errors instead of clean 422 validation errors, and the manual UUID conversion adds unnecessary code that can be a source of bugs if forgotten in new endpoints.

---

## Impact

- **Severity:** Invalid UUIDs produce unclear error messages (500 instead of 422) and confuse API consumers.
- **Affected Users/Flows:** Any API consumer sending malformed IDs to subscription or license endpoints (trial extension, license deactivation, admin subscription management).
- **Blast Radius:** Isolated to the 7 identified endpoints. Backend functionality is correct once valid UUIDs are provided.

---

## Recommended Solution

### Step 1: Update `trial_routes.py`

The `UUID` import already exists at line 1 (`from uuid import UUID`), so no new import is needed.

```python
# File: src/api/routes/subscriptions/trial_routes.py
# Replace line 94:
# Old: subscription_id: str,
# New:
    subscription_id: UUID,
```

Then remove the manual conversion at line 125:
```python
# Old: subscription_id=UUID(subscription_id),
# New:
        subscription_id=subscription_id,
```

### Step 2: Update `admin_subscription_management.py`

The `UUID` import already exists at line 11.

```python
# File: src/api/routes/subscriptions/admin/admin_subscription_management.py

# Replace line 65 (extend_subscription):
# Old: subscription_id: str,
# New:
    subscription_id: UUID,

# Replace line 77 — remove UUID() conversion:
# Old: subscription_id=UUID(subscription_id),
# New:
        subscription_id=subscription_id,

# Replace line 92 (reset_usage):
# Old: subscription_id: str,
# New:
    subscription_id: UUID,

# Replace line 104 — remove UUID() conversion:
# Old: subscription_id=UUID(subscription_id),
# New:
        subscription_id=subscription_id,
```

### Step 3: Update `license_routes.py`

Verify `from uuid import UUID` is imported (it should be). Then update all 4 endpoints:

```python
# File: src/api/routes/subscriptions/license_routes.py

# Line 240 (deactivate_license_endpoint):
# Old: license_id: str,
# New:
    license_id: UUID,

# Line 340 (get_license_endpoint):
# Old: license_id: str,
# New:
    license_id: UUID,

# Line 401 (get_license_activations_endpoint):
# Old: license_id: str,
# New:
    license_id: UUID,

# Line 459 (revoke_license_endpoint):
# Old: license_id: str,
# New:
    license_id: UUID,
```

For each endpoint, also remove any manual `UUID(license_id)` conversion calls in the handler body, passing `license_id` directly to service methods.

### Step 4: Check `admin_subscription_retrieval.py`

```python
# File: src/api/routes/subscriptions/admin/admin_subscription_retrieval.py
# Line 59:
# Old: subscription_id: str,
# New:
    subscription_id: UUID,
```

Remove any manual `UUID()` conversion in the handler body.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `src/api/routes/subscriptions/subscription_routes.py` | Various | Check if any endpoints here also use `str` for UUID parameters |
| `src/api/routes/admin/export_routes.py` | Various | May have similar `str` typed UUID parameters |
| `src/api/routes/admin/refund_routes.py` | Various | May have similar `str` typed UUID parameters |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Send a request with an invalid UUID: `POST /api/v1/trials/not-a-uuid/extend`
2. Observe that the response is a 500 Internal Server Error with a `ValueError` about badly formed UUID string.

### After Fix (Verify the Solution):
1. Send the same request: `POST /api/v1/trials/not-a-uuid/extend`
2. Observe that the response is a 422 Unprocessable Entity with a clear validation error:
   ```json
   {
     "detail": [
       {
         "type": "uuid_parsing",
         "loc": ["path", "subscription_id"],
         "msg": "Input should be a valid UUID",
         "input": "not-a-uuid"
       }
     ]
   }
   ```
3. Send a request with a valid UUID: `POST /api/v1/trials/550e8400-e29b-41d4-a716-446655440000/extend`
4. Verify it processes normally (404 if subscription doesn't exist, 200 if it does).

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "trial or license or admin_subscription" -v
```

---

## Acceptance Criteria

- [ ] All 7 identified endpoints use `UUID` type annotation for path parameters instead of `str`
- [ ] Manual `UUID()` conversion calls are removed from handler bodies where the parameter is already typed as `UUID`
- [ ] Invalid UUID path parameters return HTTP 422 with clear validation error messages
- [ ] Valid UUID path parameters continue to work as before
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI — Extra Data Types (UUID)](https://fastapi.tiangolo.com/tutorial/extra-data-types/)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [FastAPI — Path Parameters and Numeric Validations](https://fastapi.tiangolo.com/tutorial/path-params-numeric-validations/)
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-151 (Decorator Ordering Issues — same files affected), TASK-134 (Cancel Endpoint — in subscription_routes.py)
