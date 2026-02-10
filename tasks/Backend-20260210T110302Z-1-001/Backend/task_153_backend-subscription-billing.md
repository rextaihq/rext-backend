# Task 153: Billing Page Uses DELETE for Cancel vs apiClient Uses POST

## Metadata
- **Task ID:** TASK-153
- **Source:** B5 - Subscription & Billing (Finding #38 under P3 Low)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P3 Low
- **Category:** broken-functionality
- **Effort Estimate:** small (< 1 hour)

---

## Description

The application has two completely different code paths for cancelling a subscription, using different HTTP methods against different (or the same) endpoint, producing inconsistent behavior:

**Legacy billing page** (`rext-admin/app/settings/billing/page.tsx`, line 145–153):
```typescript
const response = await fetch(
  `${apiUrl}/api/v1/subscriptions/cancel?at_period_end=true`,
  {
    method: "DELETE",
    headers: { Authorization: `Bearer ${session.user.accessToken}` },
  },
);
```

**apiClient** (`rext-admin/lib/api-client/subscriptions.ts`, lines 170–187):
```typescript
cancelSubscription: async (reason?, cancelImmediately = false) => {
  return client.request("/api/v1/subscriptions/cancel", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason, cancel_immediately: cancelImmediately }),
  });
},
```

**Backend route** (`rext-backend/src/api/routes/subscriptions/subscription_routes.py`, line 423):
```python
@router.post("/cancel", response_model=dict)
```

The backend cancel endpoint is registered as `POST /api/v1/subscriptions/cancel`. The legacy billing page sends a `DELETE` request to the same URL. Since FastAPI's router only matches the `POST` method for this route, the `DELETE` request from the legacy page will return **HTTP 405 Method Not Allowed** — meaning the cancel button on the legacy billing page is completely broken.

Additionally, the legacy page passes `at_period_end=true` as a query parameter, while the backend expects a JSON body with `cancel_immediately` and `reason` fields (via `SubscriptionCancelRequest`). Even if the method matched, the request format is incompatible.

This is fundamentally a symptom of the legacy billing page bypassing the `apiClient` (covered in TASK-141). The billing page uses raw `fetch()` calls directly to the backend API instead of going through the centralized `apiClient`, which leads to these method/format mismatches.

---

## Current Code

```typescript
// File: rext-admin/app/settings/billing/page.tsx
// Lines: 141-174
  const handleCancelSubscription = async () => {
    if (
      !confirm(
        "Are you sure you want to cancel your subscription? You will retain access until the end of your billing period.",
      )
    ) {
      return;
    }

    if (!session?.user?.accessToken) {
      toast.error("Please log in to cancel subscription");
      return;
    }

    setCancelLoading(true);
    try {
      const apiUrl =
        process.env.NEXT_PUBLIC_BACKEND_API_URL || "http://127.0.0.1:2024";
      const response = await fetch(
        `${apiUrl}/api/v1/subscriptions/cancel?at_period_end=true`,
        {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${session.user.accessToken}`,
          },
        },
      );

      const result = await response.json();

      if (result.success) {
        toast.success(
          "Your subscription will be cancelled at the end of the billing period.",
        );
        fetchSubscriptionStatus();
      } else {
        throw new Error(
          result.error?.message || "Failed to cancel subscription",
        );
      }
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Cancellation Failed",
      );
    } finally {
      setCancelLoading(false);
    }
  };
```

```typescript
// File: rext-admin/lib/api-client/subscriptions.ts
// Lines: 170-187
    cancelSubscription: async (
      reason?: string,
      cancelImmediately = false,
    ): Promise<{ success: boolean; message: string }> => {
      const requestData: SubscriptionCancelRequest = {
        reason,
        cancel_immediately: cancelImmediately,
      };

      return client.request<{
        success: boolean;
        message: string;
      }>("/api/v1/subscriptions/cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestData),
      });
    },
```

---

## Why This Matters (Context & Reasoning)

The billing page (`/settings/billing`) is a user-facing page where customers manage their subscription and cancel if needed. The cancel button on this page is currently broken — it sends a `DELETE` request to a `POST`-only endpoint, resulting in an HTTP 405 error that the user sees as "Cancellation Failed". This means users visiting the legacy billing page cannot cancel their subscription.

The `apiClient` version works correctly (`POST` with JSON body), but it's only used by newer components. The legacy billing page still uses raw `fetch()` calls and has the wrong HTTP method.

The risk of NOT fixing this is that users who navigate to `/settings/billing` and click "Cancel Subscription" will see an error and be unable to cancel. This could lead to customer support tickets and user frustration.

---

## Impact

- **Severity:** The cancel subscription button on the legacy billing page is broken (sends DELETE to a POST endpoint = 405 error).
- **Affected Users/Flows:** Any user who visits `/settings/billing` and attempts to cancel their subscription via the legacy billing page.
- **Blast Radius:** Isolated to the legacy billing page's cancel flow. The `apiClient`-based cancel flow (used by newer components) works correctly.

---

## Recommended Solution

The ideal fix is to migrate the entire legacy billing page to use the `apiClient` (as described in TASK-141). However, as a targeted fix for the broken cancel button, replace the raw `fetch()` call with the `apiClient` method.

### Step 1: Import the apiClient in the billing page

```typescript
// File: rext-admin/app/settings/billing/page.tsx
// Add import at the top of the file, after existing imports:
import { apiClient } from "@/lib/api-client/core";
```

### Step 2: Replace the `handleCancelSubscription` function

```typescript
// File: rext-admin/app/settings/billing/page.tsx
// Replace the handleCancelSubscription function (lines 127-174):
  const handleCancelSubscription = async () => {
    if (
      !confirm(
        "Are you sure you want to cancel your subscription? You will retain access until the end of your billing period.",
      )
    ) {
      return;
    }

    setCancelLoading(true);
    try {
      const result = await apiClient.subscriptions.cancelSubscription(
        undefined, // no reason (legacy page doesn't collect one)
        false,     // cancel at period end, not immediately
      );

      toast.success(
        "Your subscription will be cancelled at the end of the billing period.",
      );
      fetchSubscriptionStatus();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Cancellation Failed",
      );
    } finally {
      setCancelLoading(false);
    }
  };
```

### Step 3: Verify the apiClient is properly initialized

Ensure that `apiClient` from `@/lib/api-client/core` is set up to use the user's access token from the session. Check how other components that use the `apiClient` handle authentication. If the `apiClient` automatically attaches the auth token (common pattern), no additional auth handling is needed. If it requires explicit token passing, update accordingly.

### Alternative: Quick fix without apiClient dependency

If migrating to `apiClient` introduces complexity (e.g., auth token wiring), the minimum fix is to change the HTTP method from `DELETE` to `POST` and add the correct JSON body:

```typescript
// File: rext-admin/app/settings/billing/page.tsx
// Replace lines 145-153:
      const response = await fetch(
        `${apiUrl}/api/v1/subscriptions/cancel`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${session.user.accessToken}`,
          },
          body: JSON.stringify({
            reason: undefined,
            cancel_immediately: false,
          }),
        },
      );
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-admin/app/settings/billing/page.tsx` | `78-101` | `fetchSubscriptionStatus` also uses raw `fetch()` instead of `apiClient` |
| `rext-admin/app/settings/billing/page.tsx` | `176-210` | `handleManageBilling` also uses raw `fetch()` instead of `apiClient` |
| `rext-admin/lib/api-client/subscriptions.ts` | `170-187` | The correct `cancelSubscription` implementation that should be used |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Navigate to `/settings/billing` while logged in with an active subscription.
2. Click "Cancel Subscription" and confirm the dialog.
3. Open browser DevTools Network tab and observe a `DELETE` request to `/api/v1/subscriptions/cancel?at_period_end=true`.
4. The response will be HTTP 405 Method Not Allowed.
5. The user sees a "Cancellation Failed" toast error.

### After Fix (Verify the Solution):
1. Navigate to `/settings/billing` while logged in with an active subscription.
2. Click "Cancel Subscription" and confirm the dialog.
3. In DevTools Network tab, observe a `POST` request to `/api/v1/subscriptions/cancel` with a JSON body.
4. The response should be HTTP 200 with a success message.
5. The user sees a success toast: "Your subscription will be cancelled at the end of the billing period."
6. The subscription status on the page updates to show cancellation pending.

### Run Existing Tests:
```bash
cd rext-admin && npm run test -- --grep "billing"
cd rext-admin && npm run build
```

---

## Acceptance Criteria

- [ ] The billing page cancel button sends a `POST` request (not `DELETE`) to `/api/v1/subscriptions/cancel`
- [ ] The request includes a JSON body with `reason` and `cancel_immediately` fields
- [ ] The cancel flow works end-to-end: user clicks cancel → confirmation → API call → success toast → UI update
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] The build completes successfully
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Next.js Fetch API](https://nextjs.org/docs/app/api-reference/functions/fetch)
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [HTTP Methods — MDN Web Docs](https://developer.mozilla.org/en-US/docs/Web/HTTP/Methods) — DELETE is for resource deletion, POST is for actions/commands. Subscription cancellation is an action, so POST is semantically correct.
- **Related Issues/PRs:** None

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None
- **Related:** TASK-141 (Legacy Billing Page Bypasses API Client — the root cause of this issue), TASK-143 (Cancel Feedback Collected But Never Sent — cancel reason is not sent from legacy page)
