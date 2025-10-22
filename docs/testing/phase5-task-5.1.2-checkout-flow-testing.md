# Phase 5 Task 5.1.2: Test Complete Checkout Flow in Sandbox

**Created:** 2025-10-21
**Phase:** Phase 5 - Testing & Deployment
**Task:** 5.1.2 - Test complete checkout flow in sandbox
**Status:** 🚧 In Progress

---

## Objective

Test the end-to-end checkout flow in LemonSqueezy sandbox mode, including checkout overlay, webhook processing, database updates, and subscription dashboard access.

---

## Prerequisites

- [x] Task 5.1.1 complete (products configured)
- [x] Backend server running
- [x] Database accessible
- [x] Webhook endpoint configured (ngrok or staging)
- [x] LemonSqueezy test mode enabled

---

## Test Matrix

| Plan | Variant | Product ID | Variant ID | Price | Status |
|------|---------|------------|------------|-------|--------|
| Basic | Monthly | 665157 | 1049347 | $9.99/month | ⏳ Pending |
| Basic | Yearly | 665157 | 1045158 | $99.99/year | ⏳ Pending |
| Pro | Monthly | 667795 | 1049346 | $29.99/month | ⏳ Pending |
| Pro | Yearly | 667795 | 1049351 | $290.99/year | ⏳ Pending |

---

## Test Procedure

### Step 1: Start Backend Server

```bash
cd wrext-backend
source .venv/bin/activate  # or use .venv/bin/python
uvicorn src.api.server:app --reload --port 2024
```

**Expected Result:**
- Server starts on http://localhost:2024
- No startup errors
- Health check responds: `curl http://localhost:2024/health`

### Step 2: Start ngrok Tunnel (if not already running)

```bash
ngrok http 2024
```

**Note:** Copy the ngrok HTTPS URL (e.g., `https://abc123.ngrok.io`)

**Verify webhook endpoint:**
- LemonSqueezy webhook URL should be: `https://abc123.ngrok.io/api/v1/subscriptions/webhooks/lemonsqueezy`
- Check LemonSqueezy dashboard → Settings → Webhooks

### Step 3: Create/Login Test User

**Option A: Via API**
```bash
# Create test user
curl -X POST http://localhost:2024/api/v1/user/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test-checkout@example.com",
    "username": "testcheckout",
    "password": "TestPassword123!",
    "confirm_password": "TestPassword123!"
  }'

# Login to get token
curl -X POST http://localhost:2024/api/v1/user/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test-checkout@example.com",
    "password": "TestPassword123!"
  }'

# Copy the access_token from response
```

**Option B: Via Frontend**
- Navigate to http://localhost:3000 (if frontend running)
- Create new account or login

### Step 4: Test Checkout for Each Variant

For each plan variant, perform the following tests:

#### Test 4.1: Basic Monthly ($9.99/month)

**Create Checkout Session:**
```bash
TOKEN="<your-access-token>"

curl -X POST http://localhost:2024/api/v1/subscriptions/checkout \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "plan_id": "basic",
    "billing_interval": "month"
  }'
```

**Expected Response:**
```json
{
  "checkout_url": "https://checkout.lemonsqueezy.com/...",
  "variant_id": "1049347"
}
```

**Manual Steps:**
1. ✅ Copy checkout_url from response
2. ✅ Open URL in browser
3. ✅ Verify checkout overlay/page loads
4. ✅ Verify correct plan shown: "Basic - Monthly - $9.99/month"
5. ✅ Use LemonSqueezy test card to complete purchase:
   - Card: 4242 4242 4242 4242
   - Expiry: Any future date
   - CVC: Any 3 digits
6. ✅ Complete checkout
7. ✅ Verify redirect to success URL
8. ✅ Check backend logs for webhook received
9. ✅ Verify subscription in database
10. ✅ Verify user can access subscription dashboard

**Verification Queries:**
```sql
-- Check subscription created
SELECT
  id,
  user_id,
  plan_id,
  status,
  lemonsqueezy_subscription_id,
  lemonsqueezy_customer_id,
  current_period_start,
  current_period_end
FROM user_subscriptions
WHERE user_id = (SELECT id FROM users WHERE email = 'test-checkout@example.com')
ORDER BY created_at DESC
LIMIT 1;

-- Check webhook event logged
SELECT
  event_name,
  event_id,
  status,
  created_at
FROM webhook_events
ORDER BY created_at DESC
LIMIT 5;
```

#### Test 4.2: Basic Yearly ($99.99/year)

**Create Checkout Session:**
```bash
TOKEN="<your-access-token>"

curl -X POST http://localhost:2024/api/v1/subscriptions/checkout \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "plan_id": "basic",
    "billing_interval": "year"
  }'
```

**Repeat all verification steps from Test 4.1**

#### Test 4.3: Pro Monthly ($29.99/month)

**Create Checkout Session:**
```bash
TOKEN="<your-access-token>"

curl -X POST http://localhost:2024/api/v1/subscriptions/checkout \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "plan_id": "pro",
    "billing_interval": "month"
  }'
```

**Repeat all verification steps from Test 4.1**

#### Test 4.4: Pro Yearly ($290.99/year)

**Create Checkout Session:**
```bash
TOKEN="<your-access-token>"

curl -X POST http://localhost:2024/api/v1/subscriptions/checkout \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "plan_id": "pro",
    "billing_interval": "year"
  }'
```

**Repeat all verification steps from Test 4.1**

---

## Step 5: Webhook Verification

### Check Webhook Delivery in LemonSqueezy Dashboard

1. Login to https://app.lemonsqueezy.com/
2. Navigate to Settings → Webhooks
3. Click on your webhook endpoint
4. Check "Recent deliveries" section
5. Verify all webhook events delivered successfully (200 status)

### Webhook Events to Verify

For each checkout, you should see these webhook events:

| Event | Purpose | Expected Result |
|-------|---------|----------------|
| `subscription_created` | New subscription created | Subscription record in DB |
| `subscription_payment_success` | Initial payment succeeded | Payment recorded |
| `order_created` | Order created | Order reference stored |

### Check Backend Logs

```bash
# In the terminal running the backend server
# Look for logs like:
[INFO] Webhook received: subscription_created
[INFO] Webhook signature verified successfully
[INFO] Processing subscription_created event
[INFO] Subscription created for user: <user_id>
```

---

## Step 6: Database Verification

### Verify Subscription Created

```sql
SELECT
  us.id,
  u.email,
  sp.name as plan_name,
  us.status,
  us.lemonsqueezy_subscription_id,
  us.lemonsqueezy_customer_id,
  us.lemonsqueezy_variant_id,
  us.billing_interval,
  us.current_period_start,
  us.current_period_end,
  us.trial_ends_at,
  us.created_at
FROM user_subscriptions us
JOIN users u ON us.user_id = u.id
JOIN subscription_plans sp ON us.plan_id = sp.id
WHERE u.email = 'test-checkout@example.com'
ORDER BY us.created_at DESC;
```

**Expected Results:**
- Record exists for test user
- `status` = 'active' or 'on_trial'
- `lemonsqueezy_subscription_id` is populated
- `lemonsqueezy_customer_id` is populated
- `lemonsqueezy_variant_id` matches the variant tested
- `billing_interval` matches (month or year)
- `current_period_end` is set correctly
- `trial_ends_at` is set if trial period applies

### Verify Webhook Events Logged

```sql
SELECT
  event_name,
  event_id,
  subscription_id,
  status,
  processed_at,
  error_message,
  created_at
FROM webhook_events
WHERE subscription_id IN (
  SELECT lemonsqueezy_subscription_id
  FROM user_subscriptions
  WHERE user_id = (SELECT id FROM users WHERE email = 'test-checkout@example.com')
)
ORDER BY created_at DESC;
```

**Expected Results:**
- At least 2-3 events per checkout
- All events have `status` = 'processed'
- No `error_message` values
- `processed_at` timestamp is set

---

## Step 7: Subscription Dashboard Access

### Via Frontend (if running)

1. Login to frontend as test user
2. Navigate to /subscription or /dashboard/subscription
3. Verify:
   - ✅ Current plan displayed correctly
   - ✅ Billing interval shown
   - ✅ Next billing date shown
   - ✅ Subscription status shown
   - ✅ Usage metrics displayed
   - ✅ "Manage Subscription" button works

### Via API

```bash
TOKEN="<your-access-token>"

# Get current subscription
curl http://localhost:2024/api/v1/subscriptions/current \
  -H "Authorization: Bearer $TOKEN"
```

**Expected Response:**
```json
{
  "id": "uuid",
  "plan_name": "Basic" or "Pro",
  "status": "active",
  "billing_interval": "month" or "year",
  "current_period_end": "2025-11-21T...",
  "trial_ends_at": "2025-11-04T..." or null,
  "lemonsqueezy_customer_portal_url": "https://..."
}
```

---

## Step 8: Customer Portal Access

### Test Customer Portal Link

```bash
TOKEN="<your-access-token>"

# Get customer portal URL
curl http://localhost:2024/api/v1/subscriptions/customer-portal \
  -H "Authorization: Bearer $TOKEN"
```

**Expected Response:**
```json
{
  "url": "https://mysubscriptions.lemonsqueezy.com/..."
}
```

**Manual Verification:**
1. ✅ Copy portal URL
2. ✅ Open in browser
3. ✅ Verify portal loads
4. ✅ Verify subscription details shown
5. ✅ Test updating payment method (optional)
6. ✅ Test viewing invoices

---

## Test Results Log

### Test 1: Basic Monthly
- [ ] Checkout URL generated
- [ ] Checkout page loads
- [ ] Correct plan/price displayed
- [ ] Test card accepted
- [ ] Checkout completed
- [ ] Webhook received
- [ ] Subscription in database
- [ ] Dashboard accessible
- [ ] Portal link works

**Issues Found:** (none or list issues)

**Timestamp:**

**Tester:**

---

### Test 2: Basic Yearly
- [ ] Checkout URL generated
- [ ] Checkout page loads
- [ ] Correct plan/price displayed
- [ ] Test card accepted
- [ ] Checkout completed
- [ ] Webhook received
- [ ] Subscription in database
- [ ] Dashboard accessible
- [ ] Portal link works

**Issues Found:** (none or list issues)

**Timestamp:**

**Tester:**

---

### Test 3: Pro Monthly
- [ ] Checkout URL generated
- [ ] Checkout page loads
- [ ] Correct plan/price displayed
- [ ] Test card accepted
- [ ] Checkout completed
- [ ] Webhook received
- [ ] Subscription in database
- [ ] Dashboard accessible
- [ ] Portal link works

**Issues Found:** (none or list issues)

**Timestamp:**

**Tester:**

---

### Test 4: Pro Yearly
- [ ] Checkout URL generated
- [ ] Checkout page loads
- [ ] Correct plan/price displayed
- [ ] Test card accepted
- [ ] Checkout completed
- [ ] Webhook received
- [ ] Subscription in database
- [ ] Dashboard accessible
- [ ] Portal link works

**Issues Found:** (none or list issues)

**Timestamp:**

**Tester:**

---

## Common Issues & Troubleshooting

### Issue: Checkout URL not generated
**Possible Causes:**
- Variant ID not found in database
- Plan not active
- User already has active subscription

**Solution:**
```sql
-- Check plan configuration
SELECT * FROM subscription_plans WHERE name = 'basic';

-- Check existing subscriptions
SELECT * FROM user_subscriptions WHERE user_id = '<user-id>';
```

### Issue: Webhook not received
**Possible Causes:**
- ngrok tunnel not running
- Webhook URL incorrect in LemonSqueezy
- Webhook secret mismatch

**Solution:**
- Check ngrok status: `curl http://localhost:4040/api/tunnels`
- Verify webhook URL in LemonSqueezy dashboard
- Check `LEMONSQUEEZY_WEBHOOK_SECRET` in .env

### Issue: Webhook signature verification failed
**Possible Causes:**
- Webhook secret mismatch
- Webhook payload corrupted

**Solution:**
```bash
# Check webhook secret in .env
cat .env | grep LEMONSQUEEZY_WEBHOOK_SECRET

# Check backend logs for signature details
# Update secret if needed
```

### Issue: Subscription not created in database
**Possible Causes:**
- Webhook handler error
- Database connection issue
- Missing required fields

**Solution:**
- Check backend error logs
- Check webhook_events table for error_message
- Verify database connection

---

## Success Criteria

Task 5.1.2 is complete when:

- ✅ All 4 plan variants tested successfully
- ✅ Checkout URLs generated for all variants
- ✅ Checkout pages load correctly
- ✅ Test purchases complete successfully
- ✅ All webhooks received and processed
- ✅ Subscriptions created in database
- ✅ Users can access subscription dashboard
- ✅ Customer portal links work
- ✅ No critical errors in logs
- ✅ Test results documented

---

## Next Steps

After completing Task 5.1.2:

1. Move to **Task 5.1.3:** Test webhook delivery and processing
2. Document any issues found
3. Update Phase 5 progress tracker
4. Commit test results and documentation

---

## References

- LemonSqueezy Test Cards: https://docs.lemonsqueezy.com/help/getting-started/test-mode
- LemonSqueezy Checkout API: https://docs.lemonsqueezy.com/api/checkouts
- Phase 5 Task 5.1.1 Doc: `wrext-backend/docs/testing/phase5-task-5.1.1-sandbox-setup.md`
- Product ID Mapping: `wrext-backend/docs/testing/lemonsqueezy-test-products.md`

---

**Last Updated:** 2025-10-21
