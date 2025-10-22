# Phase 5 Task 5.1.1: LemonSqueezy Sandbox Products Setup

**Created:** 2025-10-21
**Phase:** Phase 5 - Testing & Deployment
**Task:** 5.1.1 - Set up LemonSqueezy sandbox products
**Status:** 🚧 In Progress

---

## Objective

Set up a complete test store in LemonSqueezy's test mode with products, variants, and webhooks matching the production plan configuration for comprehensive sandbox testing.

---

## Prerequisites Checklist

- [x] LemonSqueezy account created (Phase 0)
- [x] API key generated and configured in `.env` (Phase 0)
- [x] Store ID obtained and configured in `.env` (Phase 0)
- [x] Test mode enabled (`LEMONSQUEEZY_SANDBOX_MODE=true`)

---

## Current Environment Configuration

From `wrext-backend/.env`:
```bash
PAYMENT_PROVIDER=lemonsqueezy
LEMONSQUEEZY_API_KEY=eyJ0eXAi... (configured)
LEMONSQUEEZY_STORE_ID=230544
LEMONSQUEEZY_WEBHOOK_SECRET=whsecret
LEMONSQUEEZY_SANDBOX_MODE=true
```

---

## Production Plans to Replicate

Based on the subscription architecture, we need to create test products for:

### 1. **Free Plan**
- **Plan ID:** `free`
- **Type:** Built-in (no LemonSqueezy product needed)
- **Limits:**
  - Workspaces: 1
  - Topics: 5
  - Knowledge Items: 10
  - AI Requests: 50/month

### 2. **Basic Plan**
- **Plan ID:** `basic`
- **Type:** Paid subscription
- **Variants:**
  - Monthly: $10/month
  - Yearly: $100/year (2 months free)
- **Limits:**
  - Workspaces: 3
  - Topics: 25
  - Knowledge Items: 100
  - AI Requests: 500/month
- **Trial:** 14 days

### 3. **Professional Plan**
- **Plan ID:** `professional`
- **Type:** Paid subscription
- **Variants:**
  - Monthly: $25/month
  - Yearly: $250/year (2 months free)
- **Limits:**
  - Workspaces: 10
  - Topics: 100
  - Knowledge Items: 1000
  - AI Requests: 2000/month
- **Trial:** 14 days

### 4. **Enterprise Plan**
- **Plan ID:** `enterprise`
- **Type:** Paid subscription
- **Variants:**
  - Monthly: $100/month
  - Yearly: $1000/year (2 months free)
- **Limits:**
  - Workspaces: Unlimited
  - Topics: Unlimited
  - Knowledge Items: Unlimited
  - AI Requests: 10000/month
- **Trial:** 14 days

---

## Task Breakdown

### Subtask 1: Create Test Products in LemonSqueezy Dashboard

#### Steps:
1. **Login to LemonSqueezy Dashboard**
   - URL: https://app.lemonsqueezy.com/
   - Enable Test Mode (toggle in top right)

2. **Create Basic Plan Product**
   - Navigate to Products → New Product
   - Name: "WREXT Basic Plan (TEST)"
   - Description: "Basic plan for WREXT knowledge management platform - TEST MODE"
   - Product Type: Subscription
   - Billing Period: Monthly
   - Price: $10.00
   - Trial Period: 14 days
   - Save and copy Product ID

3. **Create Basic Plan Yearly Variant**
   - In the Basic Plan product
   - Add Variant
   - Name: "Yearly"
   - Billing Period: Yearly
   - Price: $100.00
   - Trial Period: 14 days
   - Save and copy Variant ID

4. **Create Professional Plan Product**
   - Name: "WREXT Professional Plan (TEST)"
   - Description: "Professional plan for WREXT knowledge management platform - TEST MODE"
   - Product Type: Subscription
   - Billing Period: Monthly
   - Price: $25.00
   - Trial Period: 14 days
   - Save and copy Product ID

5. **Create Professional Plan Yearly Variant**
   - In the Professional Plan product
   - Add Variant
   - Name: "Yearly"
   - Billing Period: Yearly
   - Price: $250.00
   - Trial Period: 14 days
   - Save and copy Variant ID

6. **Create Enterprise Plan Product**
   - Name: "WREXT Enterprise Plan (TEST)"
   - Description: "Enterprise plan for WREXT knowledge management platform - TEST MODE"
   - Product Type: Subscription
   - Billing Period: Monthly
   - Price: $100.00
   - Trial Period: 14 days
   - Save and copy Product ID

7. **Create Enterprise Plan Yearly Variant**
   - In the Enterprise Plan product
   - Add Variant
   - Name: "Yearly"
   - Billing Period: Yearly
   - Price: $1000.00
   - Trial Period: 14 days
   - Save and copy Variant ID

8. **Create Test License Product (for Task 5.1.6)**
   - Name: "WREXT Lifetime License (TEST)"
   - Description: "One-time purchase lifetime license - TEST MODE"
   - Product Type: License Key
   - Price: $499.00
   - License Key Settings: Enable automatic key generation
   - Activation Limit: 5 devices
   - Save and copy Product ID

#### Expected Output:
- 3 subscription products with 2 variants each (monthly/yearly)
- 1 license key product
- Total: 7 product/variant IDs to document

---

### Subtask 2: Create Test Variants (Monthly/Yearly)

**Status:** ✅ Included in Subtask 1 above

---

### Subtask 3: Configure Test Webhook Endpoint

#### Options:

**Option A: Use ngrok for Local Testing** (Recommended for development)

1. **Install ngrok** (if not already installed)
   ```bash
   brew install ngrok  # macOS
   # or download from https://ngrok.com/download
   ```

2. **Start ngrok tunnel**
   ```bash
   ngrok http 2024
   ```

3. **Copy ngrok HTTPS URL**
   - Example: `https://abc123.ngrok.io`
   - Webhook endpoint: `https://abc123.ngrok.io/api/v1/subscriptions/webhooks/lemonsqueezy`

4. **Configure webhook in LemonSqueezy**
   - Navigate to Settings → Webhooks
   - Add Endpoint
   - URL: `https://abc123.ngrok.io/api/v1/subscriptions/webhooks/lemonsqueezy`
   - Select Events (all subscription events):
     - `subscription_created`
     - `subscription_updated`
     - `subscription_cancelled`
     - `subscription_resumed`
     - `subscription_expired`
     - `subscription_paused`
     - `subscription_unpaused`
     - `subscription_payment_success`
     - `subscription_payment_failed`
     - `subscription_payment_recovered`
     - `order_created`
     - `license_key_created`
   - Save and copy Webhook Secret

5. **Update `.env` with webhook secret**
   ```bash
   LEMONSQUEEZY_WEBHOOK_SECRET=whsec_... (copy from LemonSqueezy)
   ```

**Option B: Use Staging Server** (if available)

1. **Deploy to staging server**
   - URL: `https://staging.wrext.com/api/v1/subscriptions/webhooks/lemonsqueezy`

2. **Configure webhook in LemonSqueezy**
   - Same steps as Option A but use staging URL

**Option C: Use webhook.site for Testing** (for webhook format inspection only)

1. Visit https://webhook.site
2. Copy unique URL
3. Configure in LemonSqueezy
4. Use for inspecting webhook payload structure

#### Expected Output:
- Webhook endpoint configured in LemonSqueezy
- Webhook secret stored in `.env`
- Ability to receive test webhooks

---

### Subtask 4: Generate Test API Keys

**Status:** ✅ Already completed in Phase 0

Current API key configured in `.env`:
```bash
LEMONSQUEEZY_API_KEY=eyJ0eXAi... (configured)
```

#### Validation:
- [ ] API key is valid (test with API call)
- [ ] API key has necessary permissions
- [ ] API key is for test mode

---

### Subtask 5: Document Test Product IDs

#### Product ID Mapping Table

Create a mapping document for test product IDs to use in testing:

| Plan | Interval | LemonSqueezy Product ID | LemonSqueezy Variant ID | Internal Plan ID |
|------|----------|------------------------|------------------------|------------------|
| Basic | Monthly | `prod_XXXXX` | `var_XXXXX` | `basic` |
| Basic | Yearly | `prod_XXXXX` | `var_XXXXX` | `basic` |
| Professional | Monthly | `prod_XXXXX` | `var_XXXXX` | `professional` |
| Professional | Yearly | `prod_XXXXX` | `var_XXXXX` | `professional` |
| Enterprise | Monthly | `prod_XXXXX` | `var_XXXXX` | `enterprise` |
| Enterprise | Yearly | `prod_XXXXX` | `var_XXXXX` | `enterprise` |
| Lifetime License | One-time | `prod_XXXXX` | `var_XXXXX` | `lifetime` |

**Action Items:**
1. Fill in actual product/variant IDs after creating products
2. Update database migration to add LemonSqueezy IDs to subscription_plans table
3. Update test fixtures with real product IDs
4. Document in `wrext-backend/docs/testing/lemonsqueezy-test-products.md`

---

## Database Updates Required

After obtaining product IDs, update the `subscription_plans` table:

```sql
-- Update Basic Plan
UPDATE subscription_plans
SET
  lemonsqueezy_product_id = 'prod_XXXXX',
  lemonsqueezy_monthly_variant_id = 'var_XXXXX',
  lemonsqueezy_yearly_variant_id = 'var_XXXXX'
WHERE plan_id = 'basic';

-- Update Professional Plan
UPDATE subscription_plans
SET
  lemonsqueezy_product_id = 'prod_XXXXX',
  lemonsqueezy_monthly_variant_id = 'var_XXXXX',
  lemonsqueezy_yearly_variant_id = 'var_XXXXX'
WHERE plan_id = 'professional';

-- Update Enterprise Plan
UPDATE subscription_plans
SET
  lemonsqueezy_product_id = 'prod_XXXXX',
  lemonsqueezy_monthly_variant_id = 'var_XXXXX',
  lemonsqueezy_yearly_variant_id = 'var_XXXXX'
WHERE plan_id = 'enterprise';
```

---

## Testing Checklist

After setup, verify:

- [ ] All products visible in LemonSqueezy test mode dashboard
- [ ] All variants configured with correct pricing
- [ ] Trial period set correctly (14 days)
- [ ] Webhook endpoint responding (test with ngrok)
- [ ] API key validates successfully
- [ ] Product IDs documented
- [ ] Database updated with LemonSqueezy IDs
- [ ] Can create test checkout URL programmatically
- [ ] Webhook signature verification works

---

## Testing Commands

### 1. Validate API Key
```bash
cd wrext-backend
python scripts/validate_lemonsqueezy_key.py
```

### 2. Test Product Retrieval
```python
# In Python REPL or script
from src.providers.payment.providers.lemonsqueezy import LemonSqueezyProvider

provider = LemonSqueezyProvider()
# This will test API connectivity
```

### 3. Test Webhook Signature Verification
```bash
# Start backend server
cd wrext-backend
python -m uvicorn src.api.server:app --reload --port 2024

# In another terminal, trigger test webhook from LemonSqueezy dashboard
# Check logs for signature verification success
```

---

## Success Criteria

Task 5.1.1 is complete when:

✅ All test products created in LemonSqueezy test mode
✅ All variants (monthly/yearly) configured correctly
✅ Webhook endpoint configured and reachable
✅ Webhook secret stored securely in `.env`
✅ Test API key validated and working
✅ Product/variant IDs documented
✅ Database updated with LemonSqueezy IDs
✅ Basic connectivity tests passing

---

## Next Steps

After completing this task:

1. Move to **Task 5.1.2:** Test complete checkout flow in sandbox
2. Use documented product IDs for testing
3. Verify webhook delivery with real events

---

## Troubleshooting

### Issue: ngrok tunnel closes
**Solution:** Use ngrok's background mode or paid plan for persistent tunnels

### Issue: Webhook signature verification fails
**Solution:** Verify webhook secret matches exactly in `.env`

### Issue: Product IDs not found
**Solution:** Ensure test mode is enabled both in dashboard and API calls

### Issue: API key invalid
**Solution:** Regenerate API key in test mode, update `.env`

---

## References

- LemonSqueezy Dashboard: https://app.lemonsqueezy.com/
- LemonSqueezy API Docs: https://docs.lemonsqueezy.com/api
- LemonSqueezy Webhooks Guide: https://docs.lemonsqueezy.com/guides/developer-guide/webhooks
- Phase 0 Environment Variables Doc: `wrext-backend/docs/lemonsqueezy-environment-variables.md`
- Phase 0 Knowledge Base: `wrext-backend/docs/lemonsqueezy-knowledge-base.md`

---

## Notes

- All products created in this task are for **TEST MODE ONLY**
- Production products will be created separately in Task 5.3.4
- Keep test and production product IDs clearly separated
- Do NOT use test products in production environment
- Test charges will not actually process real payments
