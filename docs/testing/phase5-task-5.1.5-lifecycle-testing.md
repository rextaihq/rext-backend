# Subscription Lifecycle Testing - Phase 5 Task 5.1.5

**Created:** 2025-10-21
**Phase:** Phase 5 - Testing & Deployment
**Task:** 5.1.5 - Test subscription lifecycle
**Status:** ⏳ In Progress
**Test Script:** `scripts/test_subscription_lifecycle.py`

---

## Overview

This document describes the comprehensive subscription lifecycle testing performed to validate the complete subscription flow from trial creation through cancellation and reactivation.

### Test Objectives

1. **Verify Trial Creation** - Ensure subscriptions start with proper trial period
2. **Validate Trial Expiration** - Confirm trials expire correctly after period ends
3. **Test Trial Conversion** - Verify smooth transition from trial to paid
4. **Test Upgrades** - Validate plan upgrades work correctly
5. **Test Downgrades** - Ensure downgrades handle proration and limits
6. **Test Cancellation (Period End)** - Verify deferred cancellation works
7. **Test Immediate Cancellation** - Confirm instant cancellation functions
8. **Test Reactivation** - Validate subscription reactivation flow

---

## Test Coverage Matrix

| Test Scenario | Status | Priority | Dependencies | Automated |
|---------------|--------|----------|--------------|-----------|
| 1. Trial Creation | ⏳ Pending | High | None | Semi (manual checkout) |
| 2. Trial Expiration | ⏳ Pending | High | Scenario 1 | Semi (manual trigger) |
| 3. Trial Conversion | ⏳ Pending | High | Scenario 1 | Semi (manual payment) |
| 4. Subscription Upgrade | ⏳ Pending | High | Active subscription | Yes |
| 5. Subscription Downgrade | ⏳ Pending | High | Active subscription | Yes |
| 6. Cancel at Period End | ⏳ Pending | High | Active subscription | Yes |
| 7. Immediate Cancellation | ⏳ Pending | High | Active subscription | Yes |
| 8. Reactivation | ⏳ Pending | Medium | Cancelled subscription | Semi (manual checkout) |

---

## Test Environment

### Prerequisites

1. **Backend Server Running:**
   ```bash
   cd wrext-backend
   uvicorn src.api.server:app --reload --port 2024
   ```

2. **Database Available:**
   - PostgreSQL running on localhost:5432
   - Database: `wrext`
   - Migrations applied

3. **LemonSqueezy Configuration:**
   - Test mode enabled
   - API key configured in `.env`
   - Webhook endpoint configured
   - Products published:
     - Basic Monthly (Variant: 1049347)
     - Basic Yearly (Variant: 1045158)
     - Pro Monthly (Variant: 1049346)
     - Pro Yearly (Variant: 1049351)

4. **Environment Variables:**
   ```bash
   LEMONSQUEEZY_API_KEY=<test_api_key>
   LEMONSQUEEZY_STORE_ID=230544
   LEMONSQUEEZY_WEBHOOK_SECRET=<webhook_secret>
   API_BASE_URL=http://localhost:2024
   ```

---

## Running the Tests

### Quick Start

```bash
cd wrext-backend
python scripts/test_subscription_lifecycle.py
```

### Command Line Options

```bash
# Run all tests (default)
python scripts/test_subscription_lifecycle.py --scenario all

# Run specific scenario
python scripts/test_subscription_lifecycle.py --scenario trial
python scripts/test_subscription_lifecycle.py --scenario upgrade
python scripts/test_subscription_lifecycle.py --scenario downgrade
python scripts/test_subscription_lifecycle.py --scenario cancel

# Skip cleanup (keep test data)
python scripts/test_subscription_lifecycle.py --skip-cleanup

# Verbose output
python scripts/test_subscription_lifecycle.py --verbose
```

---

## Test Scenarios - Detailed

### Scenario 1: Trial Creation

**Objective:** Verify that new subscriptions start with a trial period

**Steps:**
1. Create test user
2. Generate checkout URL for Basic Monthly plan
3. Complete checkout using LemonSqueezy test card
4. Wait for webhooks to process (30-60 seconds)
5. Verify subscription created
6. Verify status is TRIAL (or ACTIVE in test mode)
7. Verify trial_end_date is set

**Expected Results:**
- ✅ Checkout URL generated successfully
- ✅ Subscription created in database
- ✅ Status: TRIAL or ACTIVE
- ✅ trial_end_date: 14 days from creation
- ✅ Webhooks received: `subscription_created`, `subscription_payment_success`

**Test Cards (LemonSqueezy):**
```
Card Number: 4242 4242 4242 4242
Expiry: Any future date
CVV: Any 3 digits
```

**Manual Steps:**
1. Script will display checkout URL
2. Open URL in browser
3. Complete checkout with test card
4. Press Enter in script to continue

**Verification Queries:**
```sql
-- Check subscription created
SELECT id, user_id, status, trial_end_date, created_at
FROM user_subscriptions
WHERE user_id = '<test_user_id>'
ORDER BY created_at DESC LIMIT 1;

-- Check webhook events
SELECT event_type, processed, created_at
FROM webhook_events
WHERE event_type IN ('subscription_created', 'subscription_payment_success')
ORDER BY created_at DESC LIMIT 5;
```

---

### Scenario 2: Trial Expiration

**Objective:** Verify that trials expire correctly when period ends

**Steps:**
1. Verify active TRIAL subscription exists
2. Manually trigger expiration (cannot wait 14 days)
3. Verify status changes to EXPIRED or CANCELLED

**Expected Results:**
- ✅ Trial status changes from TRIAL to EXPIRED
- ✅ end_date set to expiration time
- ✅ User loses access to subscription features

**Manual Trigger Options:**

**Option 1: Database Update**
```sql
-- Expire trial immediately
UPDATE user_subscriptions
SET trial_end_date = NOW() - INTERVAL '1 day'
WHERE id = '<subscription_id>' AND status = 'TRIAL';
```

**Option 2: Background Task**
```bash
# Run trial expiration task
python -m src.background.trial_expiration_task
```

**Option 3: API Call (if endpoint exists)**
```bash
# Admin endpoint to expire trial
curl -X POST http://localhost:2024/api/v1/admin/trials/<subscription_id>/expire \
  -H "Authorization: Bearer <admin_token>"
```

**Verification:**
```sql
-- Verify expiration
SELECT id, status, trial_end_date, end_date
FROM user_subscriptions
WHERE id = '<subscription_id>';
```

---

### Scenario 3: Trial to Paid Conversion

**Objective:** Verify smooth transition from trial to paid subscription

**Steps:**
1. Create trial subscription (Scenario 1)
2. Complete payment before trial ends
3. Verify webhook: `subscription_payment_success`
4. Verify status changes: TRIAL → ACTIVE
5. Verify trial_conversion record created

**Expected Results:**
- ✅ Status: TRIAL → ACTIVE
- ✅ trial_end_date cleared or marked as completed
- ✅ next_billing_date set correctly
- ✅ Trial conversion tracked in database

**Verification:**
```sql
-- Check conversion
SELECT user_id, subscription_id, trial_started_at, trial_ended_at,
       payment_amount, created_at
FROM trial_conversions
WHERE subscription_id = '<subscription_id>';

-- Check subscription status
SELECT status, trial_end_date, next_billing_date
FROM user_subscriptions
WHERE id = '<subscription_id>';
```

---

### Scenario 4: Subscription Upgrade

**Objective:** Test upgrading from Basic to Professional plan

**Steps:**
1. Start with Basic Monthly subscription (ACTIVE)
2. Call `POST /api/v1/subscriptions/upgrade`
3. Specify Professional Monthly plan
4. Verify LemonSqueezy API called: `update_subscription`
5. Verify webhook: `subscription_updated`
6. Verify plan changed in database

**Expected Results:**
- ✅ API call successful (200 OK)
- ✅ LemonSqueezy subscription updated
- ✅ plan_id changes: basic → professional
- ✅ Upgrade is immediate (no proration delay)
- ✅ New limits apply immediately

**API Request:**
```bash
curl -X POST http://localhost:2024/api/v1/subscriptions/upgrade \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "new_plan_id": "<professional_plan_uuid>",
    "billing_period": "monthly"
  }'
```

**Verification:**
```sql
-- Check plan change
SELECT plan_id, status, updated_at
FROM user_subscriptions
WHERE id = '<subscription_id>';

-- Check audit log
SELECT event_type, old_values, new_values
FROM audit_logs
WHERE resource_type = 'subscription'
  AND resource_id = '<subscription_id>'
ORDER BY created_at DESC LIMIT 1;
```

---

### Scenario 5: Subscription Downgrade

**Objective:** Test downgrading from Professional to Basic plan

**Steps:**
1. Start with Professional Monthly subscription (ACTIVE)
2. Call `POST /api/v1/subscriptions/upgrade` (same endpoint)
3. Specify Basic Monthly plan
4. Verify usage limits checked
5. Verify proration calculated (if applicable)
6. Verify plan changed in database

**Expected Results:**
- ✅ Usage validation performed
- ✅ Downgrade succeeds if usage < new limits
- ✅ Downgrade fails if usage > new limits
- ✅ plan_id changes: professional → basic
- ✅ Proration credit applied (if mid-cycle)

**Usage Limit Validation:**
```python
# Current usage must not exceed new plan limits
Current: 5 workspaces, 50 topics, 200 knowledge items
Basic Plan Limits: 3 workspaces, 25 topics, 100 knowledge items
Result: FAIL - Usage exceeds limits
```

**API Request:**
```bash
curl -X POST http://localhost:2024/api/v1/subscriptions/upgrade \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "new_plan_id": "<basic_plan_uuid>",
    "billing_period": "monthly"
  }'
```

**Error Response (if usage exceeds limits):**
```json
{
  "error": "ValidationException",
  "message": "Current usage exceeds new plan limits",
  "details": {
    "workspaces": {
      "current": 5,
      "limit": 3,
      "exceeded": true
    },
    "topics": {
      "current": 50,
      "limit": 25,
      "exceeded": true
    }
  }
}
```

---

### Scenario 6: Cancel at Period End

**Objective:** Test deferred cancellation (cancel at billing period end)

**Steps:**
1. Verify active subscription exists
2. Call `POST /api/v1/subscriptions/cancel`
3. Set `cancel_immediately: false`
4. Verify `cancel_at_period_end` flag set
5. Verify subscription remains ACTIVE
6. Verify `cancels_at` date set

**Expected Results:**
- ✅ cancel_at_period_end: true
- ✅ Status remains: ACTIVE
- ✅ cancels_at: Set to end of billing period
- ✅ User retains access until period ends
- ✅ No refund (used full period)

**API Request:**
```bash
curl -X POST http://localhost:2024/api/v1/subscriptions/cancel \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "cancel_immediately": false,
    "reason": "Testing cancellation at period end"
  }'
```

**Verification:**
```sql
-- Check cancellation flags
SELECT status, cancel_at_period_end, cancels_at, end_date
FROM user_subscriptions
WHERE id = '<subscription_id>';

-- Check audit log
SELECT event_type, metadata
FROM audit_logs
WHERE resource_type = 'subscription'
  AND resource_id = '<subscription_id>'
  AND event_type = 'subscription.cancelled'
ORDER BY created_at DESC LIMIT 1;
```

**Webhook Expected:**
```json
{
  "event_type": "subscription_cancelled",
  "data": {
    "id": "<subscription_id>",
    "attributes": {
      "status": "cancelled",
      "ends_at": "2025-11-21T00:00:00Z"
    }
  }
}
```

---

### Scenario 7: Immediate Cancellation

**Objective:** Test instant cancellation with immediate access revocation

**Steps:**
1. Verify active subscription exists
2. Call `POST /api/v1/subscriptions/cancel`
3. Set `cancel_immediately: true`
4. Verify subscription cancelled immediately
5. Verify status: CANCELLED
6. Verify end_date set to now

**Expected Results:**
- ✅ cancel_at_period_end: false
- ✅ Status: ACTIVE → CANCELLED (immediate)
- ✅ end_date: Current timestamp
- ✅ User loses access immediately
- ✅ Partial refund (if applicable)

**API Request:**
```bash
curl -X POST http://localhost:2024/api/v1/subscriptions/cancel \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "cancel_immediately": true,
    "reason": "Testing immediate cancellation"
  }'
```

**Verification:**
```sql
-- Check immediate cancellation
SELECT status, cancel_at_period_end, end_date, cancelled_at
FROM user_subscriptions
WHERE id = '<subscription_id>';
```

---

### Scenario 8: Subscription Reactivation

**Objective:** Test reactivating a cancelled subscription

**Note:** LemonSqueezy typically doesn't support true "reactivation" of cancelled subscriptions. Instead, users must create a new subscription.

**Steps:**
1. Verify cancelled subscription exists
2. Attempt reactivation (or create new subscription)
3. Verify new subscription created
4. Verify status: ACTIVE or TRIAL

**Expected Results:**
- ✅ New subscription created
- ✅ Status: TRIAL or ACTIVE
- ✅ User regains access
- ✅ Previous subscription remains CANCELLED

**Alternative Approach:**
Since LemonSqueezy doesn't support reactivation, users will:
1. Create new checkout session
2. Complete new checkout
3. Get new subscription (with new trial if applicable)

**Verification:**
```sql
-- Check new subscription
SELECT id, user_id, status, created_at
FROM user_subscriptions
WHERE user_id = '<user_id>'
ORDER BY created_at DESC LIMIT 2;
```

---

## Test Results Template

### Test Execution Report

**Test Date:** YYYY-MM-DD
**Tester:** [Your Name]
**Environment:** Sandbox/Test
**Backend Version:** [Git commit hash]

| Scenario | Status | Pass/Fail | Notes |
|----------|--------|-----------|-------|
| 1. Trial Creation | ✅ Complete | PASS | Subscription created successfully |
| 2. Trial Expiration | ✅ Complete | PASS | Manual trigger worked |
| 3. Trial Conversion | ✅ Complete | PASS | Converted to ACTIVE |
| 4. Upgrade | ✅ Complete | PASS | Basic → Pro successful |
| 5. Downgrade | ✅ Complete | PASS | Pro → Basic successful |
| 6. Cancel (Period End) | ✅ Complete | PASS | Deferred cancellation working |
| 7. Cancel (Immediate) | ✅ Complete | PASS | Instant cancellation working |
| 8. Reactivation | ✅ Complete | PASS | New subscription created |

**Summary:**
- Total Tests: 8
- Passed: 8
- Failed: 0
- Skipped: 0
- Pass Rate: 100%

---

## Common Issues & Troubleshooting

### Issue 1: Checkout URL Not Generated

**Symptoms:**
- API returns error when creating checkout
- No checkout URL returned

**Possible Causes:**
- LemonSqueezy API key invalid
- Product/variant not published
- Store not configured

**Solutions:**
```bash
# Verify API key
echo $LEMONSQUEEZY_API_KEY

# Check product IDs in database
SELECT plan_id, lemonsqueezy_product_id, lemonsqueezy_monthly_variant_id
FROM subscription_plans;

# Verify LemonSqueezy products
python scripts/list_ls_products_simple.py
```

---

### Issue 2: Webhooks Not Received

**Symptoms:**
- Subscription not created after checkout
- Status not updated after changes

**Possible Causes:**
- Webhook endpoint not configured
- Webhook signature verification failing
- Ngrok tunnel expired

**Solutions:**
```bash
# Check webhook configuration
curl https://api.lemonsqueezy.com/v1/webhooks \
  -H "Authorization: Bearer $LEMONSQUEEZY_API_KEY"

# Restart ngrok
ngrok http 2024

# Update webhook URL in LemonSqueezy dashboard
# Check webhook events in database
SELECT event_type, processed, error_message, created_at
FROM webhook_events
ORDER BY created_at DESC LIMIT 10;
```

---

### Issue 3: Upgrade/Downgrade Fails

**Symptoms:**
- API returns error on upgrade/downgrade
- Plan not changed in database

**Possible Causes:**
- LemonSqueezy subscription ID missing
- Variant ID invalid
- Usage exceeds limits (downgrade)

**Solutions:**
```bash
# Check subscription IDs
SELECT id, lemonsqueezy_subscription_id, provider_subscription_id
FROM user_subscriptions
WHERE user_id = '<user_id>';

# Check usage
curl http://localhost:2024/api/v1/subscriptions/usage \
  -H "Authorization: Bearer <token>"

# Check variant IDs
SELECT plan_id, lemonsqueezy_monthly_variant_id, lemonsqueezy_yearly_variant_id
FROM subscription_plans;
```

---

### Issue 4: Cancellation Not Working

**Symptoms:**
- Cancel API call fails
- Subscription remains active after immediate cancel

**Possible Causes:**
- LemonSqueezy API error
- Webhook not processed
- Database transaction failure

**Solutions:**
```bash
# Check LemonSqueezy subscription status
curl https://api.lemonsqueezy.com/v1/subscriptions/<subscription_id> \
  -H "Authorization: Bearer $LEMONSQUEEZY_API_KEY"

# Check audit logs
SELECT event_type, metadata, created_at
FROM audit_logs
WHERE resource_type = 'subscription'
  AND resource_id = '<subscription_id>'
ORDER BY created_at DESC LIMIT 5;

# Force cancel in database (development only)
UPDATE user_subscriptions
SET status = 'CANCELLED',
    end_date = NOW(),
    cancelled_at = NOW()
WHERE id = '<subscription_id>';
```

---

## Database Queries for Verification

### Check Subscription Status
```sql
SELECT
  us.id,
  us.user_id,
  us.plan_id,
  sp.name AS plan_name,
  us.status,
  us.trial_end_date,
  us.cancel_at_period_end,
  us.cancels_at,
  us.end_date,
  us.created_at
FROM user_subscriptions us
JOIN subscription_plans sp ON us.plan_id = sp.id
WHERE us.user_id = '<user_id>'
ORDER BY us.created_at DESC;
```

### Check Trial Conversions
```sql
SELECT
  tc.user_id,
  tc.subscription_id,
  tc.trial_started_at,
  tc.trial_ended_at,
  tc.payment_amount,
  tc.created_at
FROM trial_conversions tc
WHERE tc.user_id = '<user_id>'
ORDER BY tc.created_at DESC;
```

### Check Webhook Events
```sql
SELECT
  we.event_type,
  we.event_id,
  we.processed,
  we.error_message,
  we.created_at
FROM webhook_events we
WHERE we.created_at > NOW() - INTERVAL '1 hour'
ORDER BY we.created_at DESC
LIMIT 20;
```

### Check Audit Logs
```sql
SELECT
  al.event_type,
  al.user_id,
  al.resource_type,
  al.resource_id,
  al.old_values,
  al.new_values,
  al.created_at
FROM audit_logs al
WHERE al.resource_type = 'subscription'
  AND al.created_at > NOW() - INTERVAL '1 hour'
ORDER BY al.created_at DESC;
```

---

## Success Criteria

Task 5.1.5 is complete when:

- ✅ All 8 test scenarios executed
- ✅ Test script runs without errors
- ✅ Documentation complete
- ✅ Pass rate ≥ 90%
- ✅ All critical bugs fixed
- ✅ Lifecycle flows validated end-to-end

---

## Next Steps

After completing Task 5.1.5:

1. **Task 5.1.6:** Test license key management (one-time purchases)
2. **Task 5.1.7:** Validate email notifications
3. **Section 5.2:** Migration strategy
4. **Section 5.3:** Staging deployment
5. **Section 5.4:** Production validation

---

## References

- **Test Script:** `wrext-backend/scripts/test_subscription_lifecycle.py`
- **LemonSqueezy API Docs:** https://docs.lemonsqueezy.com/api
- **Subscription Service:** `wrext-backend/src/services/subscription_service.py`
- **Trial Service:** `wrext-backend/src/services/trial_service.py`
- **Phase 5 Plan:** `lemonsqueezy-integration-plan.md` Section "Phase 5 > Task 5.1.5"

---

**Last Updated:** 2025-10-21
**Status:** ⏳ Ready for execution
