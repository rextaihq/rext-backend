# Task 143: Connect Cancel Feedback Collection to Backend Storage

## Metadata
- **Task ID:** TASK-143
- **Source:** Subscription & Billing (Finding #31 under P2 Medium)
- **Audit Report:** `audit-reports/backend-subscription-billing.md`
- **Priority:** P2 Medium
- **Category:** bug
- **Effort Estimate:** medium (1-4 hours)

---

## Description

The subscription cancellation modal (`rext-admin/components/subscription/cancel-subscription-modal.tsx`) collects detailed cancellation feedback from users — including 7 predefined reasons via checkboxes and a free-text feedback field — but this feedback is never sent to the backend. It is discarded when the modal closes.

The feedback collection pipeline has three distinct gaps:

**Gap 1 — Frontend modal does not pass feedback to the API call (line 85):** The `handleCancel()` function calls `cancelSubscription()` with zero arguments, even though the API client's `cancelSubscription()` method accepts an optional `reason` parameter. Lines 93-97 contain a TODO comment with commented-out pseudocode: `// await sendCancellationFeedback({ reasons: selectedReasons, feedback })`. The `selectedReasons` array and `feedback` string are captured in React state but never transmitted.

**Gap 2 — Backend service logs the reason but does not store it (line 620-621 of subscription_service.py):** The `cancel()` method in `SubscriptionService` accepts a `reason: Optional[str]` parameter and passes it to the audit logger at line 628. However, it never writes the reason to the `UserSubscription` database record. The reason is only logged to stdout via `logger.info(f"Cancellation reason: {reason}")` — ephemeral log output that is not queryable for analytics.

**Gap 3 — No database column exists for cancellation reasons:** The `UserSubscription` model in `subscriptions.py` has a `cancelled_at` timestamp column (line 46) but no `cancellation_reason` field. There is a `subscription_metadata` JSONB column (line 71) that could theoretically store the reason, but it is never used for this purpose.

The result: the product team has invested in building a polished cancellation feedback UI with 7 reason categories, but every piece of feedback collected is permanently lost. This is a complete waste of a critical churn analytics data source. Understanding why customers cancel is one of the most valuable metrics for a SaaS business, directly informing product roadmap, pricing strategy, and retention initiatives.

---

## Current Code

```typescript
// File: rext-admin/components/subscription/cancel-subscription-modal.tsx
// Lines: 52-60 — Cancellation reasons defined
const CANCELLATION_REASONS = [
  "Too expensive",
  "Not using it enough",
  "Missing features I need",
  "Found a better alternative",
  "Technical issues",
  "Temporary cancellation",
  "Other",
];
```

```typescript
// File: rext-admin/components/subscription/cancel-subscription-modal.tsx
// Lines: 71-72 — State that captures feedback (then is discarded)
const [selectedReasons, setSelectedReasons] = useState<string[]>([]);
const [feedback, setFeedback] = useState("");
```

```typescript
// File: rext-admin/components/subscription/cancel-subscription-modal.tsx
// Lines: 74-97 — Cancel handler that ignores collected feedback
const handleCancel = async () => {
    if (!confirmed) {
      toast.error("Please confirm cancellation");
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      await cancelSubscription();  // <-- Called with NO arguments

      toast.success("Subscription cancelled", { ... });

      // TODO: Send cancellation feedback to analytics or backend
      if (selectedReasons.length > 0 || feedback) {
        // In a real implementation, you would send this to your backend:
        // await sendCancellationFeedback({ reasons: selectedReasons, feedback });
      }
```

```python
# File: rext-backend/src/services/subscription_service.py
# Lines: 519-530, 620-621 — Service accepts reason but only logs it
async def cancel(
    self,
    user_id: UUID,
    reason: Optional[str] = None,
    cancel_immediately: bool = False,
    background_tasks: Optional[BackgroundTasks] = None
) -> UserSubscription:
    ...
    # Line 620-621: Only logged, never stored
    if reason:
        logger.info(f"Cancellation reason: {reason}")
```

```python
# File: rext-backend/src/api/models/subscription_models/subscriptions.py
# Lines: 30-91 — No cancellation_reason field exists
class UserSubscription(Base, SerializableMixin):
    __tablename__ = "user_subscriptions"
    ...
    cancelled_at = Column(TIMESTAMP, nullable=True)  # Line 46
    # No cancellation_reason field
    subscription_metadata = Column(JSONB, default=dict)  # Line 71 — exists but unused for this
```

---

## Why This Matters (Context & Reasoning)

Cancellation feedback is one of the most valuable data sources for SaaS businesses. Understanding why customers leave directly informs product decisions, pricing adjustments, and retention strategies. The Rext AI team invested development effort in building a polished cancellation UI with 7 predefined reason categories and a free-text field — indicating they recognize the value of this data. However, the pipeline is broken at three points, meaning none of this data reaches a persistent, queryable store.

For a subscription billing system, churn analytics capabilities directly correlate with the business's ability to reduce churn. Without stored cancellation reasons, the team cannot run queries like "what percentage of cancellations cite pricing vs. missing features?" or "did churn reasons change after our last feature release?" This data should be queryable via SQL for admin dashboards and export capabilities.

---

## Impact

- **Severity:** All cancellation feedback is permanently lost. No churn reason analytics are possible. The feedback UI creates a false impression that the team is collecting data.
- **Affected Users/Flows:** Every user who cancels their subscription. Admin analytics team who need churn data.
- **Blast Radius:** Isolated to the cancellation flow, but the lost data affects business strategy decisions across the entire product.

---

## Recommended Solution

### Step 1: Add cancellation_reason column to UserSubscription model

```python
# File: rext-backend/src/api/models/subscription_models/subscriptions.py
# Add after the cancelled_at column (line 46):

from sqlalchemy import Column, String, TIMESTAMP, Text
# ... (Text import may already exist)

class UserSubscription(Base, SerializableMixin):
    # ... existing columns ...
    cancelled_at = Column(TIMESTAMP, nullable=True)
    cancellation_reason = Column(Text, nullable=True)  # Stores JSON-serialized reasons + feedback
```

### Step 2: Create Alembic migration for the new column

```bash
cd rext-backend
alembic revision --autogenerate -m "add_cancellation_reason_to_user_subscriptions"
```

The generated migration should contain:

```python
def upgrade() -> None:
    op.add_column('user_subscriptions', sa.Column('cancellation_reason', sa.Text(), nullable=True))

def downgrade() -> None:
    op.drop_column('user_subscriptions', 'cancellation_reason')
```

### Step 3: Update SubscriptionService.cancel() to store the reason

```python
# File: rext-backend/src/services/subscription_service.py
# In the cancel() method, after setting cancelled_at (around line 597):

import json

# Store cancellation reason
if reason:
    subscription.cancellation_reason = reason
    logger.info(f"Cancellation reason stored for subscription {subscription.id}")
```

### Step 4: Update the frontend cancel modal to send feedback

```typescript
// File: rext-admin/components/subscription/cancel-subscription-modal.tsx
// Replace lines 83-97 (the try block inside handleCancel) with:

try {
  // Build reason string from selected reasons and feedback
  const reasonParts: string[] = [...selectedReasons];
  if (feedback.trim()) {
    reasonParts.push(`Additional feedback: ${feedback.trim()}`);
  }
  const reasonString = reasonParts.join("; ");

  // Cancel with reason passed to API
  await cancelSubscription(reasonString || undefined);

  toast.success("Subscription cancelled", {
    description: currentPeriodEnd
      ? `You'll have access until ${new Date(currentPeriodEnd).toLocaleDateString()}`
      : "Your subscription has been cancelled.",
  });

  onClose();
```

### Step 5: Ensure the subscription store passes the reason through

```typescript
// File: rext-admin/stores/subscription-store.ts
// Verify the cancelSubscription action passes the reason parameter.
// The apiClient.subscriptions.cancelSubscription() already accepts a reason parameter,
// so the store action needs to forward it:

cancelSubscription: async (reason?: string) => {
  // ... existing logic ...
  await apiClient.subscriptions.cancelSubscription(reason, false);
  // ... existing logic ...
},
```

### Step 6: Update the cancel modal's props to accept cancelSubscription with reason

Ensure the `cancelSubscription` prop passed to the cancel modal accepts a `reason` parameter:

```typescript
// File: rext-admin/components/subscription/cancel-subscription-modal.tsx
// Update the interface:

interface CancelSubscriptionModalProps {
  isOpen: boolean;
  onClose: () => void;
  cancelSubscription: (reason?: string) => Promise<void>;
  currentPeriodEnd?: string;
}
```

---

## Other Affected Locations

| File | Line(s) | Description |
|------|---------|-------------|
| `rext-admin/lib/api-client/subscriptions.ts` | `170-187` | `cancelSubscription()` method already accepts `reason?: string` — no changes needed |
| `rext-backend/src/api/routes/subscriptions/subscription_routes.py` | `423-493` | Cancel endpoint already passes `cancel_data.reason` to service — no changes needed |
| `rext-backend/src/api/schema/subscription/subscription_schemas.py` | Various | `SubscriptionCancelRequest` schema — verify it has a `reason` field |
| `rext-backend/src/services/subscription_analytics_service.py` | Various | Add churn reason aggregation queries to leverage the new data |

---

## Testing Instructions

### Before Fix (Reproduce the Issue):
1. Navigate to a subscription management page
2. Click "Cancel Subscription"
3. In the cancel modal, select reasons (e.g., "Too expensive", "Not using it enough")
4. Enter additional feedback text
5. Confirm cancellation
6. Check the backend logs — the reason should NOT appear in any database query (only in stdout logs if it even gets there)
7. Query the database: `SELECT cancellation_reason FROM user_subscriptions WHERE cancelled_at IS NOT NULL` — column does not exist

### After Fix (Verify the Solution):
1. Repeat the same cancellation flow
2. Query the database: `SELECT id, cancellation_reason FROM user_subscriptions WHERE cancelled_at IS NOT NULL ORDER BY cancelled_at DESC LIMIT 1`
3. Verify the result contains the selected reasons and feedback text
4. Example expected value: `"Too expensive; Not using it enough; Additional feedback: The pricing doesn't match the value for small teams"`

### Run Existing Tests:
```bash
cd rext-backend && alembic upgrade head
cd rext-backend && python -m pytest tests/ -k "cancel" -v
cd rext-admin && npm test -- --testPathPattern="cancel"
```

---

## Acceptance Criteria

- [ ] `cancellation_reason` column added to `UserSubscription` model
- [ ] Alembic migration created and applies cleanly
- [ ] `SubscriptionService.cancel()` stores the reason in `subscription.cancellation_reason`
- [ ] Cancel modal sends `selectedReasons` and `feedback` to `cancelSubscription()` call
- [ ] API client's `cancelSubscription(reason)` is called with the collected feedback
- [ ] The TODO comment (lines 93-97) is removed and replaced with working code
- [ ] Cancellation reasons are queryable via SQL
- [ ] No new warnings or errors introduced
- [ ] Existing tests still pass
- [ ] Code has been reviewed by a senior developer

---

## References & Resources

- **Official Docs:** [Alembic Operations — add_column](https://alembic.sqlalchemy.org/en/latest/ops.html#alembic.operations.Operations.add_column) — reference for creating the migration to add the new column
- **Security Advisory:** N/A
- **Migration Guide:** N/A
- **Best Practice Reference:** [Cancellation Flow Examples from Famous SaaS to Reduce Churn](https://userpilot.com/blog/cancellation-flow-examples/) — SaaS best practices for collecting and using cancellation feedback
- **Related Issues/PRs:** None identified

---

## Dependencies & Related Tasks

- **Depends on:** None
- **Blocks:** None — but enables future churn analytics features
- **Related:** TASK-141 (Legacy Billing Page Bypasses API Client — the billing page has its own cancel flow that should be reconciled), TASK-133 (Duplicate Trial Expiration — another incomplete pipeline in the billing system)
