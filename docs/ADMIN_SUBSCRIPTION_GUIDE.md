# Admin Subscription Management Guide

**Version:** 1.0
**Last Updated:** 2025-10-12
**Audience:** System Administrators, Support Team
**Status:** Production Ready

---

## Overview

This guide covers administrative tasks for managing user subscriptions, including manual subscription assignment, troubleshooting, and emergency procedures.

---

## Prerequisites

### Required Access

- Database access (PostgreSQL)
- Super admin account in WREXT
- Knowledge of SQL
- Understanding of subscription architecture

### Tools Needed

- `psql` command-line tool
- Database credentials
- Admin API access

---

## Common Admin Tasks

### 1. Manually Create Subscription (Testing/Support)

**Use Case:**
- Testing subscription features
- Granting complimentary access
- Fixing failed checkout issues

**SQL Command:**
```sql
-- Step 1: Get user ID
SELECT id, email, username FROM users WHERE email = 'user@example.com';

-- Step 2: Get plan ID
SELECT id, name, display_name FROM subscription_plans WHERE name = 'pro';

-- Step 3: Create subscription
INSERT INTO user_subscriptions (
    id,
    user_id,
    plan_id,
    status,
    billing_period,
    provider_subscription_id,
    provider_customer_id,
    start_date,
    end_date,
    usage_reset_date,
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    '<user_id_from_step_1>',
    '<plan_id_from_step_2>',
    'active',
    'monthly',  -- or 'yearly'
    'manual_sub_' || floor(random() * 1000000)::text,
    'manual_cus_' || floor(random() * 1000000)::text,
    NOW(),
    NOW() + INTERVAL '30 days',  -- or '365 days' for yearly
    NOW() + INTERVAL '30 days',
    NOW(),
    NOW()
);
```

**Verification:**
```sql
SELECT
    u.email,
    u.username,
    p.name AS plan_name,
    s.status,
    s.billing_period,
    s.start_date,
    s.end_date
FROM user_subscriptions s
JOIN users u ON s.user_id = u.id
JOIN subscription_plans p ON s.plan_id = p.id
WHERE u.email = 'user@example.com';
```

---

### 2. Check User's Subscription Status

**Quick Status Check:**
```sql
SELECT
    u.email,
    p.name AS plan_name,
    s.status,
    s.billing_period,
    s.current_api_calls,
    s.start_date,
    s.end_date,
    s.cancelled_at
FROM users u
LEFT JOIN user_subscriptions s ON u.id = s.user_id AND s.status IN ('active', 'trial')
LEFT JOIN subscription_plans p ON s.plan_id = p.id
WHERE u.email = 'user@example.com';
```

**Output:**
```
email              | plan_name | status | billing_period | current_api_calls | start_date | end_date   | cancelled_at
-------------------+-----------+--------+----------------+-------------------+------------+------------+-------------
user@example.com   | pro       | active | monthly        | 1250              | 2025-10-01 | 2025-11-01 | NULL
```

---

### 3. Check Usage Metrics

**Detailed Usage Report:**
```sql
WITH user_usage AS (
    SELECT
        u.id AS user_id,
        u.email,
        -- Count workspaces
        (SELECT COUNT(*) FROM workspaces WHERE creator_id = u.id) AS workspace_count,
        -- Count topics
        (SELECT COUNT(t.id) FROM topics t
         JOIN workspaces w ON t.workspace_id = w.id
         WHERE w.creator_id = u.id) AS topic_count,
        -- Count knowledge items
        (
            (SELECT COUNT(*) FROM web_knowledge wk
             JOIN workspaces w ON wk.workspace_id = w.id
             WHERE w.creator_id = u.id) +
            (SELECT COUNT(*) FROM file_knowledge fk
             JOIN workspaces w ON fk.workspace_id = w.id
             WHERE w.creator_id = u.id) +
            (SELECT COUNT(*) FROM text_knowledge tk
             JOIN workspaces w ON tk.workspace_id = w.id
             WHERE w.creator_id = u.id)
        ) AS knowledge_item_count
    FROM users u
    WHERE u.email = 'user@example.com'
)
SELECT
    uu.email,
    p.name AS plan_name,
    -- Workspaces
    uu.workspace_count AS workspaces_used,
    p.max_workspaces AS workspaces_limit,
    -- Topics
    uu.topic_count AS topics_used,
    p.max_topics AS topics_limit,
    -- Knowledge Items
    uu.knowledge_item_count AS knowledge_items_used,
    p.max_knowledge_items AS knowledge_items_limit,
    -- API Calls
    s.current_api_calls AS api_calls_used,
    p.max_api_calls_per_month AS api_calls_limit,
    s.usage_reset_date AS api_reset_date
FROM user_usage uu
LEFT JOIN user_subscriptions s ON uu.user_id = s.user_id AND s.status IN ('active', 'trial')
LEFT JOIN subscription_plans p ON s.plan_id = p.id;
```

---

### 4. Upgrade/Downgrade User's Plan

**Upgrade Process:**
```sql
-- Step 1: Get new plan ID
SELECT id, name FROM subscription_plans WHERE name = 'enterprise';

-- Step 2: Update subscription
UPDATE user_subscriptions
SET
    plan_id = '<new_plan_id>',
    updated_at = NOW()
WHERE user_id = (SELECT id FROM users WHERE email = 'user@example.com')
  AND status = 'active';

-- Step 3: Verify
SELECT u.email, p.name AS new_plan
FROM user_subscriptions s
JOIN users u ON s.user_id = u.id
JOIN subscription_plans p ON s.plan_id = p.id
WHERE u.email = 'user@example.com' AND s.status = 'active';
```

**Important Notes:**
- No proration in manual upgrades (handled by payment provider in real flow)
- Usage limits take effect immediately
- User keeps existing usage (doesn't reset)

---

### 5. Extend Subscription Period

**Use Case:** Grant extra time due to service issues, as goodwill gesture

```sql
UPDATE user_subscriptions
SET
    end_date = end_date + INTERVAL '30 days',  -- Add 30 days
    updated_at = NOW()
WHERE user_id = (SELECT id FROM users WHERE email = 'user@example.com')
  AND status = 'active';

-- Verify new end date
SELECT email, end_date
FROM user_subscriptions s
JOIN users u ON s.user_id = u.id
WHERE u.email = 'user@example.com' AND s.status = 'active';
```

---

### 6. Cancel Subscription

**Immediate Cancellation:**
```sql
UPDATE user_subscriptions
SET
    status = 'cancelled',
    cancelled_at = NOW(),
    updated_at = NOW()
WHERE user_id = (SELECT id FROM users WHERE email = 'user@example.com')
  AND status = 'active';
```

**Cancel at Period End:**
```sql
UPDATE user_subscriptions
SET
    cancelled_at = NOW(),
    updated_at = NOW()
    -- Status remains 'active' until end_date
WHERE user_id = (SELECT id FROM users WHERE email = 'user@example.com')
  AND status = 'active';
```

---

### 7. Reset Monthly Usage (API Calls)

**Manual Reset:**
```sql
UPDATE user_subscriptions
SET
    current_api_calls = 0,
    usage_reset_date = NOW() + INTERVAL '30 days',
    updated_at = NOW()
WHERE user_id = (SELECT id FROM users WHERE email = 'user@example.com')
  AND status IN ('active', 'trial');
```

**Batch Reset (All Users):**
```sql
-- Reset all subscriptions with expired reset dates
UPDATE user_subscriptions
SET
    current_api_calls = 0,
    usage_reset_date = NOW() + INTERVAL '30 days',
    updated_at = NOW()
WHERE usage_reset_date < NOW()
  AND status IN ('active', 'trial');
```

---

## Troubleshooting Guide

### Issue: User Can't Create Workspace Despite Active Subscription

**Diagnosis Steps:**

1. **Check subscription status:**
   ```sql
   SELECT status FROM user_subscriptions
   WHERE user_id = '<user_id>' AND status IN ('active', 'trial');
   ```

   **Expected:** One row with `status = 'active'`

2. **Check workspace count vs. limit:**
   ```sql
   SELECT
       (SELECT COUNT(*) FROM workspaces WHERE creator_id = '<user_id>') AS current_count,
       p.max_workspaces AS limit
   FROM user_subscriptions s
   JOIN subscription_plans p ON s.plan_id = p.id
   WHERE s.user_id = '<user_id>' AND s.status = 'active';
   ```

3. **Check for soft-deleted workspaces:**
   ```sql
   SELECT id, name, deleted_at
   FROM workspaces
   WHERE creator_id = '<user_id>';
   ```

**Common Solutions:**

- **Multiple active subscriptions:**
  ```sql
  -- Find duplicates
  SELECT user_id, COUNT(*)
  FROM user_subscriptions
  WHERE status IN ('active', 'trial')
  GROUP BY user_id
  HAVING COUNT(*) > 1;

  -- Keep newest, deactivate old
  UPDATE user_subscriptions
  SET status = 'expired'
  WHERE id = '<old_subscription_id>';
  ```

- **Soft-deleted workspaces counting:**
  - Hard delete or exclude from count query

---

### Issue: API Calls Not Resetting

**Diagnosis:**
```sql
SELECT
    current_api_calls,
    usage_reset_date,
    NOW() AS current_time,
    usage_reset_date < NOW() AS should_have_reset
FROM user_subscriptions
WHERE user_id = '<user_id>' AND status = 'active';
```

**Solution:**
```sql
-- Manual reset
UPDATE user_subscriptions
SET
    current_api_calls = 0,
    usage_reset_date = NOW() + INTERVAL '30 days'
WHERE user_id = '<user_id>';
```

---

### Issue: Subscription Shows as Active But User Sees Free Tier

**Diagnosis:**
```sql
-- Check subscription-plan linkage
SELECT
    s.id AS subscription_id,
    s.status,
    s.plan_id,
    p.id AS plan_lookup_id,
    p.name
FROM user_subscriptions s
LEFT JOIN subscription_plans p ON s.plan_id = p.id
WHERE s.user_id = '<user_id>';
```

**Common Causes:**
- `plan_id` references non-existent plan
- Plan marked as `is_active = false`

**Solution:**
```sql
-- Re-link to valid plan
UPDATE user_subscriptions
SET plan_id = (SELECT id FROM subscription_plans WHERE name = 'pro' AND is_active = true)
WHERE user_id = '<user_id>';
```

---

## Reporting Queries

### 1. Active Subscriptions by Plan

```sql
SELECT
    p.name AS plan_name,
    COUNT(*) AS active_subscriptions,
    COUNT(*) FILTER (WHERE s.billing_period = 'monthly') AS monthly_count,
    COUNT(*) FILTER (WHERE s.billing_period = 'yearly') AS yearly_count
FROM user_subscriptions s
JOIN subscription_plans p ON s.plan_id = p.id
WHERE s.status = 'active'
GROUP BY p.name
ORDER BY active_subscriptions DESC;
```

### 2. Subscriptions Expiring Soon

```sql
SELECT
    u.email,
    p.name AS plan_name,
    s.end_date,
    s.end_date - NOW() AS days_remaining
FROM user_subscriptions s
JOIN users u ON s.user_id = u.id
JOIN subscription_plans p ON s.plan_id = p.id
WHERE s.status = 'active'
  AND s.end_date BETWEEN NOW() AND NOW() + INTERVAL '7 days'
ORDER BY s.end_date;
```

### 3. High API Usage Users

```sql
SELECT
    u.email,
    p.name AS plan_name,
    s.current_api_calls,
    p.max_api_calls_per_month AS limit,
    ROUND((s.current_api_calls::numeric / p.max_api_calls_per_month) * 100, 2) AS usage_percentage
FROM user_subscriptions s
JOIN users u ON s.user_id = u.id
JOIN subscription_plans p ON s.plan_id = p.id
WHERE s.status = 'active'
  AND p.max_api_calls_per_month > 0
  AND s.current_api_calls::numeric / p.max_api_calls_per_month > 0.8
ORDER BY usage_percentage DESC;
```

### 4. Revenue Report (Manual Subscriptions Only)

```sql
SELECT
    p.name AS plan_name,
    COUNT(*) AS subscription_count,
    COUNT(*) FILTER (WHERE s.billing_period = 'monthly') * p.price_monthly AS monthly_mrr,
    COUNT(*) FILTER (WHERE s.billing_period = 'yearly') * p.price_yearly AS yearly_arr
FROM user_subscriptions s
JOIN subscription_plans p ON s.plan_id = p.id
WHERE s.status = 'active'
GROUP BY p.name, p.price_monthly, p.price_yearly;
```

---

## Emergency Procedures

### Emergency: Give User Unlimited Access

```sql
-- Create/update to enterprise plan with unlimited limits
UPDATE subscription_plans
SET
    max_workspaces = -1,
    max_members_per_workspace = -1,
    max_topics = -1,
    max_knowledge_items = -1,
    max_api_calls_per_month = -1
WHERE name = 'emergency_unlimited';

-- Assign to user
UPDATE user_subscriptions
SET plan_id = (SELECT id FROM subscription_plans WHERE name = 'emergency_unlimited')
WHERE user_id = '<user_id>' AND status = 'active';
```

### Emergency: Disable All Limits Temporarily

**Option 1: Promote to Super Admin (CAUTION)**
```sql
-- Super admins bypass all limits
-- Use sparingly, remove after issue resolved
UPDATE users
SET role = 'super_admin'
WHERE id = '<user_id>';

-- Restore later
UPDATE users
SET role = 'user'
WHERE id = '<user_id>';
```

**Option 2: Extend All Limits**
```sql
UPDATE subscription_plans
SET
    max_workspaces = max_workspaces * 10,
    max_topics = max_topics * 10,
    max_knowledge_items = max_knowledge_items * 10,
    max_api_calls_per_month = max_api_calls_per_month * 10
WHERE id = '<plan_id>';

-- Remember to restore limits after resolution!
```

---

## Best Practices

### 1. Always Document Manual Changes

Create audit log entry:
```sql
INSERT INTO audit_logs (
    user_id,
    action,
    resource_type,
    resource_id,
    metadata,
    created_at
) VALUES (
    '<admin_user_id>',
    'subscription.manually_created',
    'subscription',
    '<subscription_id>',
    '{"reason": "Support ticket #12345", "granted_by": "admin@wrext.com"}'::jsonb,
    NOW()
);
```

### 2. Test Changes in Staging First

- Never modify production subscriptions directly without testing SQL
- Use transactions:
  ```sql
  BEGIN;
  UPDATE user_subscriptions SET ... WHERE ...;
  -- Verify changes
  SELECT * FROM user_subscriptions WHERE ...;
  -- If correct:
  COMMIT;
  -- If incorrect:
  ROLLBACK;
  ```

### 3. Communicate with Users

After manual changes, notify user:
- Email confirmation
- In-app notification
- Explain what was changed and why

### 4. Keep Backup Before Bulk Operations

```sql
-- Backup before bulk update
CREATE TABLE user_subscriptions_backup_20251012 AS
SELECT * FROM user_subscriptions WHERE status = 'active';

-- Perform bulk operation
UPDATE user_subscriptions SET ... WHERE ...;

-- Restore if needed
DELETE FROM user_subscriptions WHERE status = 'active';
INSERT INTO user_subscriptions SELECT * FROM user_subscriptions_backup_20251012;
```

---

## Tools & Scripts

### Quick Status Script

```bash
#!/bin/bash
# check_user_subscription.sh

EMAIL="$1"

if [ -z "$EMAIL" ]; then
    echo "Usage: ./check_user_subscription.sh user@example.com"
    exit 1
fi

psql -h localhost -U wrext -d wrext_db -c "
SELECT
    u.email,
    p.name AS plan,
    s.status,
    s.billing_period,
    s.current_api_calls,
    p.max_api_calls_per_month,
    s.end_date
FROM users u
LEFT JOIN user_subscriptions s ON u.id = s.user_id AND s.status IN ('active', 'trial')
LEFT JOIN subscription_plans p ON s.plan_id = p.id
WHERE u.email = '$EMAIL';
"
```

**Usage:**
```bash
chmod +x check_user_subscription.sh
./check_user_subscription.sh user@example.com
```

---

## Security Notes

- **Access Control:** Only super admins should have direct database access
- **Audit Trail:** All manual changes should be logged
- **Least Privilege:** Use read-only database users for reporting
- **Secrets:** Never log payment provider IDs or secrets

---

## Support Ticket Workflow

### User Reports Billing Issue

1. **Gather Information:**
   - User email
   - Description of issue
   - Expected vs. actual behavior

2. **Check Subscription:**
   ```sql
   SELECT * FROM user_subscriptions WHERE user_id = ...;
   ```

3. **Check Usage:**
   ```sql
   -- Run usage metrics query (see section 3 above)
   ```

4. **Diagnose & Fix:**
   - Follow troubleshooting guide
   - Apply fix via SQL

5. **Verify & Communicate:**
   - Test fix (have user try action again)
   - Send confirmation email
   - Update support ticket

---

## References

- [Subscription Architecture](./SUBSCRIPTION_ARCHITECTURE.md)
- [Usage Limits Documentation](./USAGE_LIMITS.md)
- [Database Schema](./database-schema.md)
- [Plan 01A Implementation](../../plans/01A-subscription-core-infrastructure-plan.md)

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-10-12 | Initial release |

---

**Document Version:** 1.0
**Last Review:** 2025-10-12
**Next Review:** After Plan 01B completion
**Maintained By:** Engineering Team
