# Task 136: Feature Gate is Client-Side Only with Default-Allow — No Server-Side Enforcement

## Metadata
- **Task ID:** TASK-136
- **Source:** Backend Subscription & Billing Audit (Finding #30 under P2 Medium)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P2 Medium
- **Category:** security
- **Effort Estimate:** large (4+ hours)

---

## Description

The `FeatureGate` component in `rext-admin/components/subscription/feature-gate.tsx` is the **only** mechanism enforcing feature access based on subscription plans. It checks the user's plan features client-side by comparing `subscription.plan_features[feature]` against the required feature. There is no corresponding server-side middleware or decorator that validates feature entitlements before executing API endpoint logic.

This creates two distinct security problems:

**1. Bypassable enforcement:** Any user can call premium API endpoints directly (via curl, Postman, or browser DevTools) without going through the React UI. The `FeatureGate` component never renders for these requests, so premium features are accessible to free-tier users who know the endpoint URLs. According to OWASP's Broken Access Control guidelines (A01:2021), access control must be enforced server-side where it cannot be bypassed by modifying the client.

**2. Default-allow during loading:** When subscription data hasn't loaded yet (`hasAccess === null`), the component shows a loading spinner (line 163-168). However, the `useFeatureAccess` hook (line 288-340) returns `null` when subscription is not loaded, and line 336 defaults to `setHasAccess(true)` when a feature is not found in `plan_features`. This means if plan features are missing or the key doesn't match, access is granted by default rather than denied.

The backend already has a `UsageTrackingService.check_limit()` method (in `src/services/usage_tracking_service.py`, line 110) that can check whether a user has exceeded a specific limit type (`workspaces`, `knowledge_items`, `api_calls`). However, this service is not called by any route handler as a pre-check — it's only used for reporting usage metrics, not for enforcement.

---

## Current Code

```typescript
// File: rext-admin/components/subscription/feature-gate.tsx
// Lines: 105-152 (access check logic)
  useEffect(() => {
    // Check if user has access to this feature
    if (!subscription) {
      setHasAccess(null); // Loading state
      return;
    }

    // Check plan-based access
    if (requiredPlan) {
      const allowedPlans = Array.isArray(requiredPlan)
        ? requiredPlan
        : [requiredPlan];

      if (
        !subscription.plan_name ||
        !allowedPlans.includes(subscription.plan_name.toLowerCase())
      ) {
        setHasAccess(false);
        return;
      }
    }

    // Check feature flags in plan
    if (subscription.plan_features) {
      const featureValue = subscription.plan_features[feature];

      if (typeof featureValue === "boolean") {
        setHasAccess(featureValue);
        return;
      }

      if (typeof featureValue === "number") {
        setHasAccess(featureValue > 0);
        return;
      }

      if (typeof featureValue === "string") {
        setHasAccess(featureValue.length > 0);
        return;
      }
    }

    // Default to allowing access if feature not found in plan
    setHasAccess(true);
  }, [subscription, feature, requiredPlan]);
```

```python
# File: src/services/usage_tracking_service.py
# Lines: 110-145 (existing check_limit method — not used for enforcement)
    async def check_limit(
        self,
        user_id: UUID,
        limit_type: str
    ) -> Tuple[bool, int, Optional[int]]:
        """
        Check if user has exceeded a specific limit.
        ...
        Returns:
            Tuple of (within_limit, used, limit)
        """
        usage = await self.get_usage_metrics(user_id)
        limit_data = usage.get(limit_type)

        if not limit_data:
            logger.warning(f"Unknown limit type: {limit_type}")
            return (True, 0, None)

        if limit_data.get("unlimited", False):
            return (True, limit_data["used"], None)

        used = limit_data["used"]
        limit = limit_data["limit"]

        within_limit = used < limit if limit is not None else True

        return (within_limit, used, limit)
```

---

## Why This Matters (Context & Reasoning)

Feature gating is a core monetization mechanism for SaaS products. If premium features can be accessed by free-tier users by simply calling API endpoints directly, the product loses its ability to enforce plan-based access control. This is both a security issue (unauthorized access) and a revenue issue (users getting paid features for free).

The client-side `FeatureGate` component serves a valid UX purpose — showing upgrade prompts, locking UI elements, and guiding users toward paid plans. But it should be the **presentation layer** of a feature gate, not the **enforcement layer**. The enforcement must happen server-side.

The existing `UsageTrackingService.check_limit()` method provides the foundation for server-side enforcement but is currently only used for displaying usage metrics, not for blocking requests.

---

## Impact

- **Severity:** Free-tier users can access premium features by calling API endpoints directly, bypassing client-side feature gates. This undermines plan-based monetization.
- **Affected Users/Flows:** All premium features gated by the `FeatureGate` component — workspace creation beyond free limits, knowledge base items beyond free limits, API calls beyond free limits.
- **Blast Radius:** All premium API endpoints that lack server-side feature checks.

---

## Recommended Solution

Implement a server-side feature gate as a FastAPI dependency that checks the user's subscription plan before allowing access to premium endpoints. Keep the client-side `FeatureGate` as a UX layer but add server-side enforcement as the security boundary.

### Step 1: Create a reusable feature gate dependency

```python
# File: src/api/dependencies/feature_gate.py

from typing import Optional, Callable
from uuid import UUID
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.services.usage_tracking_service import UsageTrackingService
from src.api.middleware.exceptions import RextAuthorizationException
from src.utils.logger import logger


class RequireFeature:
    """
    FastAPI dependency that enforces server-side feature gating.

    Usage:
        @router.post("/workspaces", dependencies=[Depends(RequireFeature("workspaces"))])
        async def create_workspace(...):
            ...

    Or as a function parameter:
        @router.post("/workspaces")
        async def create_workspace(
            feature_check: bool = Depends(RequireFeature("workspaces")),
            ...
        ):
            ...
    """

    def __init__(self, limit_type: str, error_message: Optional[str] = None):
        """
        Args:
            limit_type: The usage limit to check (e.g., "workspaces", "knowledge_items", "api_calls")
            error_message: Custom error message when limit is exceeded
        """
        self.limit_type = limit_type
        self.error_message = error_message

    async def __call__(
        self,
        request: Request,
        db: AsyncSession = Depends(get_async_db),
    ) -> bool:
        """Check if the current user is within their plan limits."""
        # Get user_id from the authenticated request
        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            raise RextAuthorizationException(
                message="Authentication required",
                required_permission=f"feature.{self.limit_type}"
            )

        usage_service = UsageTrackingService(db)

        try:
            usage = await usage_service.get_usage_metrics(UUID(str(user_id)))
        except Exception as e:
            logger.error(f"Feature gate check failed for user {user_id}: {e}")
            # Fail open for usage check errors to avoid blocking legitimate users
            # Log the error for monitoring
            return True

        # Check the specific limit
        current_key = f"current_{self.limit_type}"
        max_key = f"max_{self.limit_type}"

        # Handle api_calls separately (different key naming)
        if self.limit_type == "api_calls":
            current = usage.get("current_api_calls", 0) or 0
            limit = usage.get("max_api_calls_per_month", 0)
        else:
            current = usage.get(current_key, 0) or 0
            limit = usage.get(max_key, 0)

        if limit is not None and limit > 0 and current >= limit:
            plan_name = usage.get("plan_name", "your current plan")
            message = self.error_message or (
                f"You have reached the {self.limit_type.replace('_', ' ')} limit "
                f"for {plan_name} ({current}/{limit}). "
                f"Please upgrade your plan to continue."
            )
            raise RextAuthorizationException(
                message=message,
                required_permission=f"feature.{self.limit_type}"
            )

        return True
```

### Step 2: Apply the dependency to premium endpoints

```python
# File: src/api/routes/workspaces/workspace_routes.py (example)
# Add to the create workspace endpoint:

from src.api.dependencies.feature_gate import RequireFeature

@router.post(
    "/",
    dependencies=[Depends(RequireFeature("workspaces"))],
)
async def create_workspace(
    request: Request,
    workspace_data: WorkspaceCreateSchema,
    db: AsyncSession = Depends(get_async_db),
):
    # ... existing implementation ...
```

### Step 3: Fix the client-side default-allow behavior

```typescript
// File: rext-admin/components/subscription/feature-gate.tsx
// Replace line 150-151:
    // Default to DENYING access if feature not found in plan
    // This prevents unrecognized features from being accidentally accessible
    setHasAccess(false);
```

```typescript
// File: rext-admin/components/subscription/feature-gate.tsx
// Similarly in useFeatureAccess hook, replace line 336:
    // Default to denying access for unknown features
    setHasAccess(false);
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-admin/components/subscription/feature-gate.tsx` | `150-151, 336` | Default-allow behavior when feature not found in plan features |
| `rext-admin/__tests__/components/subscription/feature-gate.test.tsx` | All | Tests may need updating for new default-deny behavior |
| `src/services/usage_tracking_service.py` | `110-145` | `check_limit()` method exists but is not used for enforcement |
| Workspace creation routes | Various | Need `RequireFeature("workspaces")` dependency |
| Knowledge base routes | Various | Need `RequireFeature("knowledge_items")` dependency |
| API-call-heavy endpoints | Various | Need `RequireFeature("api_calls")` dependency |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Create a free-tier user account
2. Log in and note the workspace limit (e.g., 1 workspace max on free plan)
3. Using curl or Postman, call the workspace creation API endpoint directly with the free user's token
4. Verify that the workspace is created successfully despite being at the free-tier limit
5. The `FeatureGate` component in the UI would have blocked this, but the API does not

### After Fix (Verify the Solution):
1. Repeat step 3 — the API should now return a 403 with a message about exceeding the workspace limit
2. Upgrade the user to a paid plan and verify the API call succeeds
3. Verify the `FeatureGate` UI still shows upgrade prompts correctly
4. Test with a feature key that doesn't exist in `plan_features` — should deny (not allow) access

### Run Existing Tests:
```bash
cd rext-backend && python -m pytest tests/ -k "usage" -v
cd rext-admin && npx jest --testPathPattern="feature-gate" --verbose
```

---

## Acceptance Criteria

- [ ] Server-side `RequireFeature` dependency exists and checks plan limits before allowing endpoint execution
- [ ] At least workspace, knowledge item, and API call limits are enforced server-side
- [ ] Free-tier users cannot bypass feature limits by calling API endpoints directly
- [ ] Client-side `FeatureGate` defaults to denying access for unknown features (not allowing)
- [ ] `useFeatureAccess` hook defaults to denying access for unknown features
- [ ] Existing client-side FeatureGate UI continues to work correctly
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [FastAPI Dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/)
- **Security Advisory:** [OWASP A01:2021 — Broken Access Control](https://owasp.org/Top10/A01_2021-Broken_Access_Control/)
- **Migration Guide:** N/A
- **Best Practice Reference:** [OWASP Top 10 Client-Side Security Risks](https://owasp.org/www-project-top-10-client-side-security-risks/)
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-128 (No Rate Limiting on License Endpoints — similar enforcement gap)
