# LemonSqueezy Test Products - Product ID Mapping

**Created:** 2025-10-21
**Phase:** Phase 5 - Testing & Deployment
**Task:** 5.1.1 - Set up LemonSqueezy sandbox products
**Status:** ✅ Complete
**Store ID:** 230544
**Mode:** Test/Sandbox

---

## Overview

This document contains the mapping between our internal subscription plans and the LemonSqueezy test products created for Phase 5 testing.

**⚠️ IMPORTANT:** These are TEST MODE products only. Do NOT use in production.

---

## Product Mapping Table

| Internal Plan ID | Plan Name | Interval | LS Product ID | LS Variant ID | Price | Status |
|------------------|-----------|----------|---------------|---------------|-------|--------|
| `basic` | Basic | Monthly | `665157` | `1049347` | $9.99/month | ✅ Published |
| `basic` | Basic | Yearly | `665157` | `1045158` | $99.99/year | ✅ Published |
| `professional` | Pro | Monthly | `667795` | `1049346` | $29.99/month | ✅ Published |
| `professional` | Pro | Yearly | `667795` | `1049351` | $290.99/year | ✅ Published |

---

## Product Details

### 1. Basic Plan

**Product ID:** `665157`
**Product Name:** Basic
**Status:** Published
**Description:** (empty)

**Variants:**

| Variant Name | Variant ID | Billing Interval | Price | Trial Period |
|--------------|------------|------------------|-------|--------------|
| Basic - Monthly | `1049347` | Monthly | $9.99 | (check dashboard) |
| Basic - Yearly | `1045158` | Yearly | $99.99 | (check dashboard) |

**Internal Limits (from subscription_plans table):**
- Workspaces: 3
- Topics: 25
- Knowledge Items: 100
- AI Requests: 500/month

---

### 2. Professional Plan

**Product ID:** `667795`
**Product Name:** Pro
**Status:** Published
**Description:** (empty)

**Variants:**

| Variant Name | Variant ID | Billing Interval | Price | Trial Period |
|--------------|------------|------------------|-------|--------------|
| Pro - Monthly | `1049346` | Monthly | $29.99 | (check dashboard) |
| Pro - Yearly | `1049351` | Yearly | $290.99 | (check dashboard) |

**Internal Limits (from subscription_plans table):**
- Workspaces: 10
- Topics: 100
- Knowledge Items: 1000
- AI Requests: 2000/month

---

## Missing Products

The following products need to be created in LemonSqueezy dashboard:

### 3. Enterprise Plan ⚠️ NOT YET CREATED

**Recommended Configuration:**
- Product Name: Enterprise
- Monthly Variant: $100/month
- Yearly Variant: $1000/year
- Trial Period: 14 days

**Internal Limits:**
- Workspaces: Unlimited
- Topics: Unlimited
- Knowledge Items: Unlimited
- AI Requests: 10000/month

### 4. Lifetime License (for testing one-time purchases) ⚠️ NOT YET CREATED

**Recommended Configuration:**
- Product Name: WREXT Lifetime License (TEST)
- Type: License Key
- Price: $499 (one-time)
- License Settings:
  - Auto-generate keys: Yes
  - Activation limit: 5 devices

---

## Database Update

### SQL Update Script

Run the following SQL to update the `subscription_plans` table with LemonSqueezy IDs:

```sql
-- Update Basic Plan
UPDATE subscription_plans
SET
  lemonsqueezy_product_id = '665157',
  lemonsqueezy_monthly_variant_id = '1049347',
  lemonsqueezy_yearly_variant_id = '1045158'
WHERE plan_id = 'basic';

-- Update Professional Plan
UPDATE subscription_plans
SET
  lemonsqueezy_product_id = '667795',
  lemonsqueezy_monthly_variant_id = '1049346',
  lemonsqueezy_yearly_variant_id = '1049351'
WHERE plan_id = 'professional';

-- Enterprise Plan (when created)
-- UPDATE subscription_plans
-- SET
--   lemonsqueezy_product_id = 'XXXXX',
--   lemonsqueezy_monthly_variant_id = 'XXXXX',
--   lemonsqueezy_yearly_variant_id = 'XXXXX'
-- WHERE plan_id = 'enterprise';
```

### Verification Query

After running the update, verify with:

```sql
SELECT
  plan_id,
  name,
  lemonsqueezy_product_id,
  lemonsqueezy_monthly_variant_id,
  lemonsqueezy_yearly_variant_id
FROM subscription_plans
WHERE plan_id IN ('basic', 'professional', 'enterprise')
ORDER BY plan_id;
```

---

## Test Checkout URLs

### Creating Test Checkout Sessions

Use these product/variant IDs when testing checkout:

**Basic Monthly:**
```python
variant_id = "1049347"
# or via API: product_id = "665157" with interval="month"
```

**Basic Yearly:**
```python
variant_id = "1045158"
# or via API: product_id = "665157" with interval="year"
```

**Professional Monthly:**
```python
variant_id = "1049346"
# or via API: product_id = "667795" with interval="month"
```

**Professional Yearly:**
```python
variant_id = "1049351"
# or via API: product_id = "667795" with interval="year"
```

---

## Testing Checklist

### Product Setup
- [x] Basic plan created with monthly variant ($9.99/month)
- [x] Basic plan created with yearly variant ($99.99/year)
- [x] Professional plan created with monthly variant ($29.99/month)
- [x] Professional plan created with yearly variant ($290.99/year)
- [ ] Enterprise plan created with monthly variant ($100/month)
- [ ] Enterprise plan created with yearly variant ($1000/year)
- [ ] Lifetime license product created ($499 one-time)

### Product Configuration
- [ ] Trial periods configured (14 days recommended)
- [ ] Product descriptions added
- [ ] Product statuses set to "published"
- [ ] Test mode confirmed (all products in test store)

### Database Integration
- [ ] Database updated with product IDs
- [ ] Verification query confirms IDs are stored
- [ ] Backend can retrieve products via API
- [ ] Checkout URLs can be generated programmatically

---

## Webhook Configuration

**Endpoint:** (configured in Phase 0)
- URL: `https://[your-ngrok-url]/api/v1/webhooks/lemonsqueezy`
- Secret: (stored in .env as `LEMONSQUEEZY_WEBHOOK_SECRET`)

**Events Subscribed:**
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

---

## Next Steps

1. **Create missing products:**
   - Enterprise plan (monthly + yearly)
   - Lifetime license product

2. **Configure trial periods:**
   - Update all products to have 14-day trials
   - Verify trial settings in LemonSqueezy dashboard

3. **Update database:**
   - Run SQL update script above
   - Verify with verification query

4. **Test checkout flow (Task 5.1.2):**
   - Test each variant can create checkout session
   - Verify checkout overlay opens correctly
   - Complete test purchase
   - Verify webhook received and processed

---

## Troubleshooting

### Issue: Product IDs not found
**Solution:** Ensure you're in Test Mode in LemonSqueezy dashboard

### Issue: Variants have wrong pricing
**Solution:** Edit variant in LemonSqueezy dashboard to update pricing

### Issue: Checkout fails with "product not found"
**Solution:** Verify product ID matches exactly and product is published

### Issue: Database update fails
**Solution:** Ensure subscription_plans table has the correct columns (check Phase 1 migrations)

---

## References

- LemonSqueezy Dashboard: https://app.lemonsqueezy.com/
- API Documentation: https://docs.lemonsqueezy.com/api
- Products API: https://docs.lemonsqueezy.com/api/products
- Variants API: https://docs.lemonsqueezy.com/api/variants
- Phase 0 Setup Doc: `wrext-backend/docs/lemonsqueezy-environment-variables.md`
- Phase 5 Task 5.1.1 Doc: `wrext-backend/docs/testing/phase5-task-5.1.1-sandbox-setup.md`

---

## Update History

| Date | Change | Updated By |
|------|--------|------------|
| 2025-10-21 | Initial creation with Basic and Pro products | Claude |
| | Identified missing Enterprise and License products | Claude |
| | | |

---

**Last Updated:** 2025-10-21
**Next Review:** After creating Enterprise and License products
