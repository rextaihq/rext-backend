# Task 141: Migrate Legacy Billing Page from Raw fetch() to apiClient

## Metadata
- **Task ID:** TASK-141
- **Source:** Subscription & Billing (Finding #20 under P2 Medium)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P2 Medium
- **Category:** bug
- **Effort Estimate:** large (4+ hours)

---

## Description

The billing settings page at `rext-admin/app/settings/billing/page.tsx` (709 lines) completely bypasses the established API client architecture (`lib/api-client/`) and instead makes raw `fetch()` calls with manually constructed authentication headers. This creates three categories of problems:

**1. Authentication fragility:** The page constructs Bearer tokens directly from `session.user.accessToken` in three separate locations (lines 87-91, 145-153, 186-190). The proper `apiClient` uses `authenticatedFetch()` from `lib/auth-utils` which automatically handles access token retrieval, refresh token rotation, and token expiration. The billing page has none of this — if the user's access token expires during their session, all billing operations silently fail with 401 errors that are poorly handled.

**2. Endpoint inconsistency:** The billing page calls different endpoints than the API client for the same operations. For subscription status, it calls `GET /api/v1/subscriptions/status` while the apiClient calls `GET /api/v1/subscriptions/my-subscription`. For cancellation, it sends `DELETE /api/v1/subscriptions/cancel?at_period_end=true` while the apiClient sends `POST /api/v1/subscriptions/cancel` with a JSON body containing `{ reason, cancel_immediately }`. This means the billing page and other parts of the application may produce different results for the same action.

**3. Hardcoded plan details:** Lines 561-693 render three hardcoded plan cards (Free at $0/month, Pro at $29/month, Enterprise at "Custom") with fixed feature limits. This data should be fetched via `apiClient.subscriptions.getPlans()`. When plan prices or limits change in the database, the billing page displays stale information.

The API base URL `process.env.NEXT_PUBLIC_BACKEND_API_URL || "http://127.0.0.1:2024"` is also constructed independently in each fetch call instead of being centralized. Error handling is minimal — the page does not check `response.ok` before parsing JSON, does not extract FastAPI validation error details, and catches exceptions with generic messages.

---

## Current Code

```typescript
// File: rext-admin/app/settings/billing/page.tsx
// Lines: 85-91 — Raw fetch for subscription status
const apiUrl = process.env.NEXT_PUBLIC_BACKEND_API_URL || "http://127.0.0.1:2024";
const response = await fetch(`${apiUrl}/api/v1/subscriptions/status`, {
  headers: {
    Authorization: `Bearer ${session.user.accessToken}`,
  },
});
```

```typescript
// File: rext-admin/app/settings/billing/page.tsx
// Lines: 143-153 — Raw fetch for cancellation using DELETE
const apiUrl = process.env.NEXT_PUBLIC_BACKEND_API_URL || "http://127.0.0.1:2024";
const response = await fetch(
  `${apiUrl}/api/v1/subscriptions/cancel?at_period_end=true`,
  {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${session.user.accessToken}`,
    },
  },
);
```

```typescript
// File: rext-admin/app/settings/billing/page.tsx
// Lines: 184-190 — Raw fetch for billing portal
const apiUrl = process.env.NEXT_PUBLIC_BACKEND_API_URL || "http://127.0.0.1:2024";
const response = await fetch(`${apiUrl}/api/v1/subscriptions/portal`, {
  headers: {
    Authorization: `Bearer ${session.user.accessToken}`,
  },
});
```

```typescript
// File: rext-admin/app/settings/billing/page.tsx
// Lines: 614 — Hardcoded plan price
<span className="text-3xl font-bold">$29</span>
```

---

## Why This Matters (Context & Reasoning)

The billing settings page is the primary interface where paying customers manage their subscriptions — view plan details, cancel, and access the billing portal. It is one of the highest-stakes pages in the application because errors directly affect revenue (failed cancellations leading to customer complaints, stale pricing misleading users). Using raw fetch() bypasses all of the reliability, error handling, and authentication infrastructure that the API client provides. The centralized API client (`lib/api-client/core.ts`) provides authenticated fetch with token refresh, comprehensive error parsing (including FastAPI validation errors), request tracking via AbortControllers, and consistent response envelope unwrapping. None of this is available to the billing page.

Additionally, the mismatch between DELETE and POST for cancellation means the legacy billing page and the cancel-subscription-modal may trigger different backend code paths for the same user action. This is confusing for developers debugging cancellation issues.

---

## Impact

- **Severity:** Authentication failures silently break all billing operations. Hardcoded plan data shows incorrect prices when plans are updated. Cancel via DELETE may not properly forward cancellation reason data.
- **Affected Users/Flows:** Every user who visits Settings > Billing. Cancel, manage billing, and plan display flows.
- **Blast Radius:** Isolated to the billing settings page, but this is a revenue-critical page affecting all paying customers.

---

## Recommended Solution

### Step 1: Replace subscription status fetch with apiClient

```typescript
// File: rext-admin/app/settings/billing/page.tsx
// Replace the fetchSubscriptionStatus function's fetch call with:

import { apiClient } from "@/lib/api-client";

const fetchSubscriptionStatus = async () => {
  try {
    setLoading(true);
    const result = await apiClient.subscriptions.getCurrentPlan();
    if (result) {
      setData(result);
    }
  } catch (error) {
    console.error("Failed to fetch subscription status:", error);
    toast.error("Failed to load subscription details");
  } finally {
    setLoading(false);
  }
};
```

### Step 2: Replace cancellation fetch with apiClient

```typescript
// File: rext-admin/app/settings/billing/page.tsx
// Replace the handleCancelSubscription function with:

const handleCancelSubscription = async () => {
  try {
    setCancelLoading(true);
    await apiClient.subscriptions.cancelSubscription(
      undefined,  // reason - handled by cancel modal
      false       // cancelImmediately = false (cancel at period end)
    );
    toast.success("Your subscription will be cancelled at the end of the billing period.");
    fetchSubscriptionStatus();
  } catch (error) {
    console.error("Failed to cancel subscription:", error);
    toast.error(
      error instanceof Error ? error.message : "Failed to cancel subscription"
    );
  } finally {
    setCancelLoading(false);
  }
};
```

### Step 3: Replace billing portal fetch with apiClient

```typescript
// File: rext-admin/app/settings/billing/page.tsx
// Replace the handleManageBilling function with:

const handleManageBilling = async () => {
  try {
    const result = await apiClient.subscriptions.getCustomerPortalUrl();
    if (result?.url) {
      window.open(result.url, "_blank");
    }
  } catch (error) {
    console.error("Failed to get billing portal URL:", error);
    toast.error("Failed to open billing portal");
  }
};
```

### Step 4: Replace hardcoded plan cards with dynamic data

```typescript
// File: rext-admin/app/settings/billing/page.tsx
// Add a plans query to fetch plan data:

const [plans, setPlans] = useState<SubscriptionPlan[]>([]);

useEffect(() => {
  const fetchPlans = async () => {
    try {
      const result = await apiClient.subscriptions.getPlans();
      if (result?.plans) {
        setPlans(result.plans);
      }
    } catch (error) {
      console.error("Failed to fetch plans:", error);
    }
  };
  fetchPlans();
}, []);

// Then replace the hardcoded plan cards (lines 561-693) with:
{plans.map((plan) => (
  <div key={plan.id} className="border rounded-xl p-6">
    <h3 className="text-lg font-semibold">{plan.display_name}</h3>
    <p className="text-sm text-muted-foreground">{plan.description}</p>
    <span className="text-3xl font-bold">
      ${Number(plan.price_monthly).toFixed(0)}
    </span>
    <span className="text-muted-foreground">/month</span>
    {/* Render feature limits dynamically from plan data */}
  </div>
))}
```

### Step 5: Remove all manual API URL construction and auth headers

Remove all instances of:
```typescript
const apiUrl = process.env.NEXT_PUBLIC_BACKEND_API_URL || "http://127.0.0.1:2024";
```
and all manual `Authorization: Bearer ${session.user.accessToken}` header construction from the billing page.

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-admin/services/backend.ts` | `~400-600` | Legacy backend service with billing methods — also bypasses apiClient. Should be deprecated after this migration. |
| `rext-admin/lib/api-client/subscriptions.ts` | `31-255` | The proper API client subscriptions namespace that this page should use instead |
| `rext-admin/stores/subscription-store.ts` | `~1-527` | The subscription Zustand store that wraps apiClient methods — consider using the store instead of apiClient directly |
| `rext-admin/components/subscription/cancel-subscription-modal.tsx` | `74-119` | The cancel modal component — may need to be integrated with the billing page's cancel flow |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Open browser DevTools Network tab
2. Navigate to Settings > Billing
3. Observe raw fetch calls to `/api/v1/subscriptions/status` with manually constructed headers
4. Note the hardcoded plan prices displayed ($0, $29, Custom)
5. Verify plan prices in the database do not necessarily match these hardcoded values

### After Fix (Verify the Solution):
1. Navigate to Settings > Billing
2. Verify subscription status loads correctly via apiClient (check Network tab — request should go through the apiClient's authenticated fetch)
3. Verify plan cards show dynamic data from the API
4. Test cancellation flow — verify it uses POST method (not DELETE) through apiClient
5. Test billing portal redirect — verify it opens LemonSqueezy portal
6. Test with an expired access token — verify the page handles refresh correctly (apiClient's authenticatedFetch should handle this)

### Run Existing Tests:
```bash
cd rext-admin && npm test -- --testPathPattern="billing"
cd rext-admin && npx tsc --noEmit
```

---

## Acceptance Criteria

- [ ] All raw `fetch()` calls removed from `app/settings/billing/page.tsx`
- [ ] All manual `Authorization` header construction removed
- [ ] All manual API URL construction (`NEXT_PUBLIC_BACKEND_API_URL || "http://127.0.0.1:2024"`) removed
- [ ] Subscription status fetched via `apiClient.subscriptions.getCurrentPlan()`
- [ ] Cancellation uses `apiClient.subscriptions.cancelSubscription()` with POST method
- [ ] Billing portal uses `apiClient.subscriptions.getCustomerPortalUrl()`
- [ ] Plan cards display dynamic data from the API instead of hardcoded values
- [ ] Error handling uses apiClient's built-in error parsing
- [ ] Token refresh works automatically via authenticatedFetch
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Next.js Data Fetching Patterns](https://nextjs.org/docs/app/getting-started/server-and-client-components) — current guidance on client-side data fetching in Next.js App Router
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Next.js Authentication Best Practices 2025](https://www.franciscomoretti.com/blog/modern-nextjs-authentication-best-practices) — recommends centralized auth handling rather than per-page token management
- **Related Issues/PRs:** None identified

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-143 (Cancel Feedback Collected But Never Sent — the cancel flow in this page should be reconciled with the cancel modal's feedback collection), TASK-142 (Frontend Admin Pages Double-Unwrap Response Envelope — another frontend API integration pattern issue)
