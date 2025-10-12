# Usage Limits & Plan Enforcement

**Version:** 1.0
**Last Updated:** 2025-10-12
**Status:** Production Ready

---

## Overview

WREXT enforces subscription plan limits in real-time at the API route level, preventing users from exceeding their plan allocations. This document explains how limits work, how they're enforced, and how to configure them.

---

## Subscription Plan Limits

### Standard Limit Types

| Limit Type | Description | Scope | Reset Period |
|------------|-------------|-------|--------------|
| `max_workspaces` | Maximum workspaces user can create | Per user | Never (cumulative) |
| `max_members_per_workspace` | Maximum members in any workspace | Per workspace | Never |
| `max_topics` | Maximum topics across all workspaces | Per user | Never |
| `max_knowledge_items` | Maximum knowledge items (web, file, text) | Per user | Never |
| `max_api_calls_per_month` | Maximum AI API calls | Per user | Monthly |

### Special Values

- **`-1`** = Unlimited (no limit enforced)
- **`0`** = Feature disabled (always blocked)
- **`> 0`** = Specific limit

---

## How Limits Are Enforced

### 1. Middleware-Based Enforcement

Every resource-creation endpoint includes a usage limit checker as a FastAPI dependency:

```python
from src.api.middleware.usage_limiter import check_workspace_limit

@router.post("/workspace/create")
async def create_workspace(
    _: None = Depends(check_workspace_limit()),  # ← Enforced BEFORE business logic
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # If we reach here, limit check passed
    # Create workspace logic...
```

### 2. Enforcement Flow

```
1. User makes request to create resource
2. FastAPI calls check_xxx_limit() dependency
3. Query user's active subscription
4. Get plan limits
5. Count current usage
6. Compare: IF used >= limit THEN return 429 error ELSE proceed
7. Execute business logic
8. (Optional) Increment counter (for API calls)
```

### 3. Error Response

When limit exceeded, API returns **HTTP 429 (Too Many Requests)**:

```json
{
    "detail": "Workspace limit reached (10/10). Upgrade your plan to create more workspaces."
}
```

**Frontend Handling:**
- Display upgrade prompt
- Link to `/pricing` page
- Show current usage vs. limit

---

## Limit Enforcement Details

### Workspaces

**Limit:** `max_workspaces`
**Counted:** Total workspaces created by user (not deleted)
**Enforced At:** `POST /workspace/create`

**Query:**
```sql
SELECT COUNT(*) FROM workspaces WHERE creator_id = '<user_id>';
```

**Free Tier Default:** 1 workspace

**Example Error:**
```
Workspace limit reached (1/1). Please subscribe to a plan to create more workspaces.
```

---

### Members

**Limit:** `max_members_per_workspace`
**Counted:** Total members in the workspace (including owner)
**Enforced At:**
- `POST /{workspace_id}/invitations`
- `POST /{workspace_id}/invitations/bulk`

**Query:**
```sql
SELECT COUNT(*) FROM workspace_members WHERE workspace_id = '<workspace_id>';
```

**Free Tier Default:** 3 members per workspace

**Notes:**
- Limit applies per workspace, not globally
- Workspace owner always counts as 1 member
- Pending invitations may or may not count (configurable)

---

### Topics

**Limit:** `max_topics`
**Counted:** Total topics across all user's workspaces
**Enforced At:** `POST /topic/save-topic`

**Query:**
```sql
SELECT COUNT(topics.id)
FROM topics
JOIN workspaces ON topics.workspace_id = workspaces.id
WHERE workspaces.creator_id = '<user_id>';
```

**Free Tier Default:** 50 topics

**Notes:**
- Topics are counted globally across all workspaces
- Deleted topics don't count (soft-delete removes from count)

---

### Knowledge Items

**Limit:** `max_knowledge_items`
**Counted:** Total knowledge items (web + file + text) across all workspaces
**Enforced At:**
- `POST /{workspace_id}/knowledge/web`
- `POST /{workspace_id}/knowledge/files`
- `POST /{workspace_id}/knowledge/text`

**Query:**
```sql
SELECT
    (SELECT COUNT(*) FROM web_knowledge WHERE workspace_id IN (
        SELECT id FROM workspaces WHERE creator_id = '<user_id>'
    )) +
    (SELECT COUNT(*) FROM file_knowledge WHERE workspace_id IN (
        SELECT id FROM workspaces WHERE creator_id = '<user_id>'
    )) +
    (SELECT COUNT(*) FROM text_knowledge WHERE workspace_id IN (
        SELECT id FROM workspaces WHERE creator_id = '<user_id>'
    )) AS total;
```

**Free Tier Default:** 100 items

**Notes:**
- All knowledge types count toward same limit
- Deleted items don't count

---

### API Calls

**Limit:** `max_api_calls_per_month`
**Counted:** Cumulative AI API calls during current billing period
**Enforced At:** `POST /topic/generate-topic` (and other AI endpoints)

**Storage:**
```sql
-- Counter stored in user_subscriptions table
SELECT current_api_calls, usage_reset_date
FROM user_subscriptions
WHERE user_id = '<user_id>' AND status = 'active';
```

**Free Tier Default:** 1,000 calls/month

**Special Behavior:**
- Counter increments on EVERY AI API call
- Resets monthly on `usage_reset_date`
- Auto-reset via cron job or on-access

**Example:**
```
API call limit reached (10000/10000). Upgrade your plan or wait until 2025-11-01.
```

---

## Free Tier Behavior

### Users Without Subscription

When user has **no active subscription**, they get free tier limits:

| Resource | Free Tier Limit |
|----------|----------------|
| Workspaces | 1 |
| Members per Workspace | 3 |
| Topics | 50 |
| Knowledge Items | 100 |
| API Calls/Month | 1,000 |

**Implementation:**
```python
if not subscription or not plan:
    # Apply free tier limits
    if current_count >= FREE_TIER_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"Limit reached. Please subscribe to a plan."
        )
```

---

## Super Admin Bypass

**Super admins** bypass ALL usage limits:

```python
if current_user.role == "super_admin":
    return  # Skip limit check
```

**Why?**
- Testing and debugging
- Support operations
- Emergency fixes

---

## Monthly Usage Reset

### Automatic Reset

**Trigger:** Background cron job (runs daily)

**Process:**
```python
# Reset all subscriptions with expired usage_reset_date
for subscription in subscriptions_needing_reset:
    subscription.current_api_calls = 0
    subscription.usage_reset_date = datetime.utcnow() + timedelta(days=30)
```

**Cron Schedule:**
```bash
# Run daily at 2 AM
0 2 * * * python -m src.utils.cron.reset_monthly_usage
```

### On-Demand Reset

**When:** User makes API call after `usage_reset_date` has passed

**Process:**
```python
if subscription.usage_reset_date < datetime.utcnow():
    subscription.current_api_calls = 0
    subscription.usage_reset_date = datetime.utcnow() + timedelta(days=30)
```

**Benefit:** Self-healing if cron fails

---

## Configuration

### Plan Configuration

**Location:** Database (`subscription_plans` table)

**Example:**
```sql
INSERT INTO subscription_plans (
    name, display_name,
    max_workspaces, max_members_per_workspace, max_topics,
    max_knowledge_items, max_api_calls_per_month
) VALUES (
    'pro', 'Pro Plan',
    10, 20, 500,
    1000, 10000
);
```

### Free Tier Configuration

**Location:** `src/api/middleware/usage_limiter.py`

**Constants:**
```python
FREE_TIER_LIMITS = {
    "workspaces": 1,
    "members_per_workspace": 3,
    "topics": 50,
    "knowledge_items": 100,
    "api_calls_per_month": 1000
}
```

---

## Testing Usage Limits

### Manual Testing (Development)

1. **Create user without subscription**
   ```sql
   -- No subscription = free tier
   ```

2. **Try creating 2 workspaces**
   ```bash
   # First workspace: ✅ Success
   # Second workspace: ❌ 429 error
   ```

3. **Assign subscription manually**
   ```sql
   INSERT INTO user_subscriptions (
       user_id, plan_id, status, billing_period,
       provider_subscription_id, provider_customer_id
   ) VALUES (
       '<user_id>',
       (SELECT id FROM subscription_plans WHERE name = 'pro'),
       'active', 'monthly',
       'manual_sub_123', 'manual_cus_123'
   );
   ```

4. **Try creating 2nd workspace**
   ```bash
   # Now succeeds (limit is 10 on Pro plan)
   ```

### Automated Testing

**Location:** `tests/integration/test_usage_limits.py`

```python
async def test_workspace_limit_enforcement():
    # Create user with 1-workspace limit
    # Create 1 workspace: should succeed
    # Try creating 2nd workspace: should fail with 429
```

---

## Upgrade Flow

### When User Hits Limit

1. **API returns 429** with helpful message
2. **Frontend displays upgrade prompt:**
   ```
   ⚠️ You've reached your workspace limit (5/5)

   [Upgrade to Pro] to create unlimited workspaces
   ```
3. **User clicks "Upgrade"**
4. **Redirect to `/pricing`**
5. **User selects plan and completes checkout**
6. **Webhook creates subscription** with new limits
7. **User can now create more resources**

### Seamless Transition

- No data loss
- No downtime
- Limits apply immediately after subscription activation

---

## Usage Metrics API

### Get Current Usage

**Endpoint:** `GET /api/v1/subscriptions/usage`

**Response:**
```json
{
    "success": true,
    "data": {
        "workspaces": {
            "used": 3,
            "limit": 10,
            "percentage": 30,
            "unlimited": false
        },
        "members": {
            "used": 12,
            "limit": 20,
            "percentage": 60,
            "unlimited": false
        },
        "topics": {
            "used": 87,
            "limit": 500,
            "percentage": 17,
            "unlimited": false
        },
        "knowledge_items": {
            "used": 234,
            "limit": 1000,
            "percentage": 23,
            "unlimited": false
        },
        "api_calls": {
            "used": 4521,
            "limit": 10000,
            "percentage": 45,
            "unlimited": false,
            "reset_date": "2025-11-01T00:00:00Z"
        }
    }
}
```

**Frontend Display:**
```tsx
<ProgressBar
    value={usage.workspaces.percentage}
    label={`${usage.workspaces.used}/${usage.workspaces.limit} workspaces`}
/>
```

---

## Best Practices

### 1. Proactive Alerts

Show usage warnings before hitting limit:

```tsx
{usage.workspaces.percentage > 80 && (
    <Alert variant="warning">
        You're using {usage.workspaces.percentage}% of your workspace limit.
        Consider upgrading to avoid interruptions.
    </Alert>
)}
```

### 2. Clear Error Messages

Always include:
- Current usage
- Limit value
- Call-to-action (upgrade link)

**Good:**
```
Workspace limit reached (10/10). Upgrade to Pro for unlimited workspaces.
```

**Bad:**
```
Limit exceeded
```

### 3. Graceful Degradation

For non-critical limits, allow view-only access:

```python
if usage_exceeded and read_only_operation:
    return data  # Allow viewing
elif usage_exceeded:
    raise LimitExceeded  # Block creation
```

---

## Troubleshooting

### "False Positive" Limit Errors

**Symptom:** User gets limit error despite being under limit

**Possible Causes:**
1. Subscription not marked as `active`
2. Multiple active subscriptions (should be unique)
3. Cached data (subscription not refreshed)
4. Soft-deleted resources still counting

**Solution:**
```sql
-- Check subscription status
SELECT status, current_api_calls, usage_reset_date
FROM user_subscriptions
WHERE user_id = '<user_id>';

-- Check for multiple active subscriptions
SELECT COUNT(*) FROM user_subscriptions
WHERE user_id = '<user_id>' AND status IN ('active', 'trial');
-- Should return 1 or 0
```

### Usage Not Resetting

**Symptom:** API call counter doesn't reset monthly

**Check:**
```sql
SELECT current_api_calls, usage_reset_date, NOW()
FROM user_subscriptions
WHERE user_id = '<user_id>';
```

**Solutions:**
1. Check if `usage_reset_date` is in the past
2. Manually reset:
   ```sql
   UPDATE user_subscriptions
   SET current_api_calls = 0,
       usage_reset_date = NOW() + INTERVAL '30 days'
   WHERE user_id = '<user_id>';
   ```
3. Check cron job logs

---

## Future Enhancements

- [ ] Overage charges (pay-as-you-go)
- [ ] Per-resource rate limiting (API calls/minute)
- [ ] Usage forecasting and alerts
- [ ] Temporary limit boosts
- [ ] Grace period before hard cutoff
- [ ] Usage-based pricing tiers

---

## References

- [Usage Limiter Middleware](../src/api/middleware/usage_limiter.py)
- [Usage Tracking Service](../src/services/usage_tracking_service.py)
- [Subscription Architecture](./SUBSCRIPTION_ARCHITECTURE.md)
- [Plan 01A Documentation](../../plans/01A-subscription-core-infrastructure-plan.md)

---

**Document Version:** 1.0
**Last Review:** 2025-10-12
**Next Review:** After Plan 01B completion
