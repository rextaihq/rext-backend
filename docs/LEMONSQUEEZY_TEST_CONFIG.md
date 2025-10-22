# LemonSqueezy Test Configuration

**Last Updated:** 2025-10-20
**Purpose:** Configuration guide for testing LemonSqueezy integration in sandbox mode
**Phase:** Phase 5 - Testing & Deployment

---

## Overview

This document details the test environment configuration for LemonSqueezy integration, including sandbox products, webhook endpoints, and testing procedures.

---

## 1. Environment Configuration

### Current Backend Configuration

**Server:**
- **Port:** `2024` (see `.env` line 30)
- **Host:** `0.0.0.0`
- **Environment:** `development`
- **LemonSqueezy Mode:** `LEMONSQUEEZY_SANDBOX_MODE=true` (line 116)

**Key Environment Variables:**
```bash
LEMONSQUEEZY_API_KEY=eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9...  # Line 103
LEMONSQUEEZY_STORE_ID=230544                                # Line 107
LEMONSQUEEZY_WEBHOOK_SECRET=whsecret                     # Line 112 (NEEDS UPDATE)
LEMONSQUEEZY_SANDBOX_MODE=true                              # Line 116
PAYMENT_PROVIDER=mock                                        # Line 75 (Change to 'lemonsqueezy' for testing)
```

**Webhook Endpoint:**
- **Path:** `/api/v1/subscriptions/webhooks/lemonsqueezy`
- **Full Local URL:** `http://localhost:2024/api/v1/subscriptions/webhooks/lemonsqueezy`
- **Method:** POST
- **Authentication:** Signature verification using `LEMONSQUEEZY_WEBHOOK_SECRET`
- **Implementation:** [src/api/routes/subscriptions/webhook_routes.py:197](../src/api/routes/subscriptions/webhook_routes.py#L197)

---

## 2. LemonSqueezy Test Products

### Current Test Products (as of 2025-10-20)

All products created in **Test Mode** on LemonSqueezy Dashboard.

#### Product 1: Basic Plan
- **Product Name:** Basic
- **Description:** Basic tier subscription
- **Product ID:** `665157`
- **Product URL:** https://app.lemonsqueezy.com/products/665157
- **Variants:**
  1. **Basic Monthly**
     - Price: $9.99/month
     - Billing Interval: Monthly
     - Product ID: `665157`
     - Variant ID: `1045158`
     - Variant URL: https://app.lemonsqueezy.com/products/665157/variants/1045158
  2. **Basic Yearly**
     - Price: $99.99/year (17% savings)
     - Billing Interval: Yearly
     - Product ID: `665157`
     - Variant ID: `1049347`
     - Variant URL: https://app.lemonsqueezy.com/products/665157/variants/1049347

#### Product 2: Pro Plan
- **Product Name:** Pro
- **Description:** Professional tier subscription
- **Product ID:** `667795`
- **Product URL:** https://app.lemonsqueezy.com/products/667795
- **Variants:**
  1. **Pro Monthly**
     - Price: $29.99/month
     - Billing Interval: Monthly
     - Product ID: `667795`
     - Variant ID: `1049346`
     - Variant URL: https://app.lemonsqueezy.com/products/667795/variants/1049346
  2. **Pro Yearly**
     - Price: $290.99/year (19% savings)
     - Billing Interval: Yearly
     - Product ID: `667795`
     - Variant ID: `1049351`
     - Variant URL: https://app.lemonsqueezy.com/products/667795/variants/1049351

#### Free Plan
**Decision:** Free plan is **NOT** created in LemonSqueezy.

**Rationale:**
- Avoid transaction fees on $0 subscriptions
- Simpler logic (no payment processing for free users)
- Free tier handled entirely in application code
- Users upgrade to paid plans via LemonSqueezy checkout
- Users downgrade/cancel return to free tier (no LemonSqueezy subscription)

---

## 3. ngrok Setup for Local Webhook Testing

### Installation

ngrok is installed via Homebrew:
```bash
brew install --cask ngrok
```

**Version:** 3.30.0
**Location:** `/opt/homebrew/bin/ngrok`

### Setup Steps

#### Step 1: Get ngrok Auth Token

1. Sign up at [ngrok.com](https://ngrok.com/) (free account)
2. Get your auth token from: https://dashboard.ngrok.com/get-started/your-authtoken
3. Add token to ngrok:
   ```bash
   ngrok config add-authtoken <YOUR_TOKEN>
   ```

#### Step 2: Start ngrok Tunnel

Start ngrok to tunnel to your backend server on port 2024:

```bash
ngrok http 2024
```

**Expected Output:**
```
ngrok                                                                    (Ctrl+C to quit)

Session Status                online
Account                       Your Name (Plan: Free)
Version                       3.30.0
Region                        United States (us)
Latency                       -
Web Interface                 http://127.0.0.1:4040
Forwarding                    https://abcd-1234-5678.ngrok-free.app -> http://localhost:2024

Connections                   ttl     opn     rt1     rt5     p50     p90
                              0       0       0.00    0.00    0.00    0.00
```

**Important URLs:**
- **Public URL:** `https://abcd-1234-5678.ngrok-free.app` (changes each time)
- **Webhook URL:** `https://abcd-1234-5678.ngrok-free.app/api/v1/subscriptions/webhooks/lemonsqueezy`
- **Web Interface:** `http://127.0.0.1:4040` (view incoming requests)

#### Step 3: Register Webhook in LemonSqueezy

1. Go to LemonSqueezy Dashboard → Settings → Webhooks (Test Mode)
2. Click "Add Endpoint"
3. **URL:** `https://your-ngrok-url.ngrok-free.app/api/v1/subscriptions/webhooks/lemonsqueezy`
4. **Events to Send:** Select all subscription and order events:
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
   - `order_refunded`
   - `license_key_created`
   - `license_key_updated`
5. **Save** and copy the **Signing Secret** (starts with `whsec_`)
6. Update `.env` file:
   ```bash
   LEMONSQUEEZY_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxx
   ```

#### Step 4: Test Webhook Delivery

Use ngrok's web interface to monitor webhook deliveries:
```bash
open http://127.0.0.1:4040
```

Or test manually using LemonSqueezy's webhook testing tool in the dashboard.

---

## 4. Testing Checklist

### Before Testing
- [ ] Backend server running on port 2024 (⚠️ RESTART REQUIRED after .env changes)
- [ ] ngrok tunnel active
- [x] Webhook registered in LemonSqueezy with ngrok URL ✅
- [x] `LEMONSQUEEZY_WEBHOOK_SECRET` updated in `.env` (confirmed: `whsecret`) ✅
- [x] `PAYMENT_PROVIDER=lemonsqueezy` in `.env` ✅ (changed from `mock`)
- [ ] Frontend running on port 3000
- [x] Database is up-to-date (migration ls20251020 applied successfully) ✅
- [ ] Redis is running

### Test Products Created
- [x] Basic Monthly variant created in LemonSqueezy (product ID: 665157, variant ID: 1045158) ✅
- [x] Basic Yearly variant created in LemonSqueezy (product ID: 665157, variant ID: 1049347) ✅
- [x] Pro Monthly variant created in LemonSqueezy (product ID: 667795, variant ID: 1049346) ✅
- [x] Pro Yearly variant created in LemonSqueezy (product ID: 667795, variant ID: 1049351) ✅
- [x] Database migration completed - Basic plan added and all plans updated with LemonSqueezy IDs ✅

### Webhook Configuration
- [x] Webhook endpoint registered in LemonSqueezy dashboard (ngrok URL: 2ed506f31af6.ngrok-free.app) ✅
- [x] Signing secret copied to `.env` (⚠️ `whsecret` - verify this is correct) ✅
- [ ] Test webhook sent from LemonSqueezy dashboard
- [ ] Webhook received and processed successfully (check ngrok web interface)
- [ ] Signature verification passing

### Integration Tests Ready
- [ ] Test checkout flow (Task 5.1.2)
- [ ] Test webhook processing (Task 5.1.3)
- [ ] Test edge cases (Task 5.1.4)
- [ ] Test subscription lifecycle (Task 5.1.5)
- [ ] Test license management (Task 5.1.6)
- [ ] Test email notifications (Task 5.1.7)

---

## 5. Product ID Mapping

### Database Plan to LemonSqueezy Product Mapping

**✅ ACTUAL PRODUCT IDs (as of 2025-10-20):**

```python
# Production-ready mapping - use these IDs in backend configuration:
LEMONSQUEEZY_PRODUCT_MAP = {
    "basic_monthly": {
        "variant_id": "1045158",  # Basic Monthly variant ID
        "product_id": "665157",   # Basic product ID
    },
    "basic_yearly": {
        "variant_id": "1049347",  # Basic Yearly variant ID
        "product_id": "665157",   # Same Basic product ID
    },
    "pro_monthly": {
        "variant_id": "1049346",  # Pro Monthly variant ID
        "product_id": "667795",   # Pro product ID
    },
    "pro_yearly": {
        "variant_id": "1049351",  # Pro Yearly variant ID
        "product_id": "667795",   # Same Pro product ID
    },
}
```

**Webhook Configuration:**
- **ngrok URL:** `https://2ed506f31af6.ngrok-free.app`
- **Webhook Endpoint:** `https://2ed506f31af6.ngrok-free.app/api/v1/subscriptions/webhooks/lemonsqueezy`
- **Signing Secret:** `whsecret` (⚠️ Verify this is correct - typically longer)

**Current Database Plan IDs:**
Check `wrext-backend/src/api/models/subscription_models/plan.py` for internal plan identifiers.

---

## 6. Test Cards & Test Mode

### LemonSqueezy Test Cards

When testing in sandbox mode, use these test card numbers:

**Successful Payment:**
- Card Number: `4242 4242 4242 4242`
- Expiry: Any future date (e.g., `12/25`)
- CVC: Any 3 digits (e.g., `123`)
- ZIP: Any 5 digits (e.g., `12345`)

**Failed Payment:**
- Card Number: `4000 0000 0000 0002`
- Expiry: Any future date
- CVC: Any 3 digits
- ZIP: Any 5 digits

**See more test cards:** https://docs.lemonsqueezy.com/help/getting-started/test-mode#test-cards

---

## 7. Common Issues & Troubleshooting

### Issue: Webhook not receiving events

**Symptoms:**
- Checkout completes but no database update
- No webhook events in ngrok web interface

**Solutions:**
1. Check ngrok is running: `curl https://your-ngrok-url.ngrok-free.app/health` (if health endpoint exists)
2. Check webhook is registered in LemonSqueezy dashboard (Test Mode)
3. Check webhook URL matches ngrok URL exactly
4. Check backend server logs for errors
5. Check ngrok web interface for incoming requests: http://127.0.0.1:4040

### Issue: Signature verification failing

**Symptoms:**
- Webhook received but returns 401/403 error
- Logs show "Invalid webhook signature"

**Solutions:**
1. Verify `LEMONSQUEEZY_WEBHOOK_SECRET` matches LemonSqueezy dashboard
2. Check secret starts with `whsec_`
3. Restart backend server after updating `.env`
4. Check webhook implementation uses correct header (`X-Signature`)

### Issue: ngrok URL changes

**Problem:**
- Free ngrok accounts get a new URL on each restart
- Webhook URL in LemonSqueezy becomes invalid

**Solutions:**
1. Update webhook URL in LemonSqueezy dashboard after each ngrok restart
2. Use ngrok paid plan for permanent URL
3. Use a staging server with fixed URL instead of ngrok

### Issue: Cannot connect to backend

**Symptoms:**
- ngrok shows 502 Bad Gateway
- Connection refused errors

**Solutions:**
1. Ensure backend server is running: `lsof -i :2024`
2. Check `HOST=0.0.0.0` in `.env` (not `127.0.0.1`)
3. Check firewall settings
4. Restart backend server

---

## 8. Next Steps After Configuration

Once all products are created and ngrok is configured:

1. **Document Product IDs**: Update section 5 with actual LemonSqueezy IDs
2. **Update Backend Config**: Add product mapping to `settings.py`
3. **Switch Payment Provider**: Change `PAYMENT_PROVIDER=lemonsqueezy` in `.env`
4. **Restart Backend**: Apply new configuration
5. **Proceed to Task 5.1.2**: Test complete checkout flow

---

## 9. Security Reminders

- ✅ Always use Test Mode during development (`LEMONSQUEEZY_SANDBOX_MODE=true`)
- ✅ Never commit `.env` file with real API keys to git
- ✅ Keep webhook signing secret secure
- ✅ Use environment variables for all sensitive data
- ✅ Verify webhook signatures on all incoming webhooks
- ⚠️ Remember to update webhook URL when switching from ngrok to production

---

## 10. Additional Resources

- **LemonSqueezy Docs:** https://docs.lemonsqueezy.com/
- **LemonSqueezy API Reference:** https://docs.lemonsqueezy.com/api
- **LemonSqueezy Test Mode:** https://docs.lemonsqueezy.com/help/getting-started/test-mode
- **ngrok Documentation:** https://ngrok.com/docs
- **Webhook Implementation:** [src/api/routes/subscriptions/webhook_routes.py](../src/api/routes/subscriptions/webhook_routes.py)
- **Provider Implementation:** [src/providers/payment/lemonsqueezy_provider.py](../src/providers/payment/lemonsqueezy_provider.py)

---

## Contact & Support

For questions or issues during testing, refer to:
- Main integration prompt: `LEMONSQUEEZY_INTEGRATION_PROMPT.md`
- Integration plan: `lemonsqueezy-integration-plan.md`
- Requirements doc: `lemonsqueezy-integration-requirements.md`
