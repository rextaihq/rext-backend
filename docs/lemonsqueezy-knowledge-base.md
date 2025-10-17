# LemonSqueezy Integration - Knowledge Base

**Created:** 2025-10-17
**Phase:** Phase 0 - Discovery & Analysis
**Task:** 0.3.4 - Study LemonSqueezy Documentation
**Status:** ✅ Complete

---

## Executive Summary

This knowledge base consolidates critical information from the official LemonSqueezy documentation to guide the integration implementation. It covers API architecture, authentication, subscription management, webhooks, checkout implementation, and best practices.

### Key Takeaways

✅ **REST API** with JSON:API format
✅ **300 API calls per minute** rate limit
✅ **Test mode** available for safe development
✅ **9 subscription webhook events** to handle
✅ **Signature verification** required for webhook security
✅ **Checkout overlay** for seamless user experience
✅ **Official JavaScript SDK** available

---

## Table of Contents

1. [API Architecture](#api-architecture)
2. [Authentication](#authentication)
3. [Rate Limiting](#rate-limiting)
4. [Test Mode vs Live Mode](#test-mode-vs-live-mode)
5. [Key API Endpoints](#key-api-endpoints)
6. [Subscription Management](#subscription-management)
7. [Webhooks](#webhooks)
8. [Checkout Implementation](#checkout-implementation)
9. [Error Handling](#error-handling)
10. [Best Practices](#best-practices)
11. [SDKs and Libraries](#sdks-and-libraries)
12. [Implementation Checklist](#implementation-checklist)

---

## API Architecture

### REST API Design

**Architecture:**
- REST API with resource-oriented URLs
- Returns JSON:API encoded responses
- Uses standard HTTP response codes
- Follows JSON:API specification

**Base URL:**
```
https://api.lemonsqueezy.com/v1
```

**Versioning:**
- Major version number included in endpoint prefix (`/v1`)
- Backwards compatibility maintained when possible
- Breaking changes will result in new version (e.g., `/v2`)

**Response Format:**
```json
{
  "data": {
    "type": "subscriptions",
    "id": "123456",
    "attributes": {
      "store_id": 12345,
      "customer_id": 67890,
      "product_id": 11111,
      "status": "active",
      // ... more attributes
    },
    "relationships": {
      "store": { ... },
      "customer": { ... },
      "product": { ... }
    }
  },
  "meta": {
    "page": {
      "currentPage": 1,
      "from": 1,
      "lastPage": 5,
      "perPage": 10,
      "to": 10,
      "total": 50
    }
  }
}
```

**Key Characteristics:**
- Consistent structure across all endpoints
- Relationships include links to related resources
- Meta information for pagination and additional context
- Attributes contain the actual data

---

## Authentication

### API Key Authentication

**Method:** Bearer token authentication

**Header Format:**
```http
Authorization: Bearer {api_key}
```

**Obtaining API Keys:**
1. Log into LemonSqueezy Dashboard
2. Navigate to: https://app.lemonsqueezy.com/settings/api
3. Click "Create API Key"
4. Name your key (e.g., "WREXT Production")
5. Copy the key immediately (shown only once)

**Security Best Practices:**
- ✅ Use separate keys for test and live modes
- ✅ Never commit API keys to version control
- ✅ Store keys in environment variables
- ✅ Rotate keys periodically
- ✅ Revoke compromised keys immediately

**Example Request:**
```python
import requests

headers = {
    "Authorization": f"Bearer {LEMONSQUEEZY_API_KEY}",
    "Accept": "application/vnd.api+json",
    "Content-Type": "application/vnd.api+json"
}

response = requests.get(
    "https://api.lemonsqueezy.com/v1/subscriptions/123456",
    headers=headers
)
```

---

## Rate Limiting

### API Call Limits

**Limit:** 300 API calls per minute (per API key)

**Rate Limit Headers:**
```http
X-Ratelimit-Limit: 300
X-Ratelimit-Remaining: 245
```

**Response When Exceeded:**
- Status Code: `429 Too Many Requests`
- Retry after: Wait 60 seconds

**Best Practices:**
1. **Monitor Headers:** Check `X-Ratelimit-Remaining` in responses
2. **Implement Backoff:** Exponential backoff when approaching limit
3. **Cache Responses:** Reduce redundant API calls
4. **Batch Operations:** Combine multiple operations when possible
5. **Use Webhooks:** For real-time updates instead of polling

**Example Rate Limit Handling:**
```python
def make_api_call_with_rate_limit(url, headers):
    response = requests.get(url, headers=headers)

    remaining = int(response.headers.get('X-Ratelimit-Remaining', 0))

    if remaining < 10:
        # Approaching limit, slow down
        time.sleep(2)

    if response.status_code == 429:
        # Rate limited, wait and retry
        time.sleep(60)
        return make_api_call_with_rate_limit(url, headers)

    return response
```

**Webhook Advantage:**
- Webhooks don't count against rate limit
- Real-time updates without polling
- More efficient than periodic API calls

---

## Test Mode vs Live Mode

### Two Operating Modes

| Aspect | Test Mode | Live Mode |
|--------|-----------|-----------|
| **API Key** | Test mode API key | Live mode API key |
| **Payments** | No real charges | Real credit card charges |
| **Data** | Test data (isolated) | Production data |
| **Purpose** | Development & testing | Production operations |
| **Webhooks** | Test webhooks | Production webhooks |

### Test Mode Features

**Purpose:** "Build and test a full API integration"

**Benefits:**
- ✅ Test full integration without real charges
- ✅ Separate data from production
- ✅ Test webhook events manually
- ✅ Simulate subscription lifecycles
- ✅ Test error scenarios safely

**Usage:**
1. Create test products with short billing intervals (daily)
2. Use test credit cards for checkout testing
3. Manually trigger webhook events from dashboard
4. Test subscription creation, updates, cancellations
5. Verify database updates and email notifications

**Switching to Production:**
1. Create live mode API key
2. Update environment variables
3. Set `LEMONSQUEEZY_SANDBOX_MODE=false`
4. Configure production webhook endpoints
5. Test with small real transaction first
6. Monitor closely for 24-48 hours

---

## Key API Endpoints

### Resource Endpoints

#### 1. Stores
```http
GET /v1/stores
GET /v1/stores/{id}
```

**Purpose:** Retrieve store information

**Use Case:** Validate store ID on startup

---

#### 2. Customers
```http
GET /v1/customers
GET /v1/customers/{id}
POST /v1/customers
PATCH /v1/customers/{id}
```

**Purpose:** Manage customer records

**Key Attributes:**
- `store_id`
- `name`
- `email`
- `status` (active, archived)
- `total_revenue_currency`
- `created_at`

**Use Cases:**
- Create customer on first subscription
- Update customer information
- Retrieve customer details

---

#### 3. Products
```http
GET /v1/products
GET /v1/products/{id}
```

**Purpose:** Retrieve product information

**Key Attributes:**
- `store_id`
- `name`
- `description`
- `status` (draft, published)
- `pricing_type` (one-time, subscription)
- `created_at`

**Use Case:** Fetch product details for display

---

#### 4. Variants
```http
GET /v1/variants
GET /v1/variants/{id}
```

**Purpose:** Product variants with different pricing/features

**Key Attributes:**
- `product_id`
- `name`
- `description`
- `price` (in cents)
- `interval` (day, week, month, year)
- `interval_count`
- `status`

**Use Case:** Store variant IDs in subscription_plans table

---

#### 5. Subscriptions
```http
GET /v1/subscriptions
GET /v1/subscriptions/{id}
POST /v1/subscriptions
PATCH /v1/subscriptions/{id}
DELETE /v1/subscriptions/{id}
```

**Purpose:** Manage subscription lifecycle

**Key Attributes:**
- `store_id`
- `customer_id`
- `order_id`
- `product_id`
- `variant_id`
- `status` (active, cancelled, expired, paused, past_due, unpaid)
- `card_brand`
- `card_last_four`
- `renews_at`
- `ends_at`
- `cancelled_at`
- `pause` (object with mode, resumes_at)
- `urls` (customer_portal, update_payment_method)

**Key Operations:**
- **Create:** Usually done via checkout, but can be done programmatically
- **Retrieve:** Get subscription details
- **Update:** Change plan (variant_id), pause, resume
- **Cancel:** Cancel subscription (immediately or at period end)

**Cancellation Parameters:**
```json
{
  "cancelled_at": "2024-10-17T12:00:00Z"
}
```

**Pause Parameters:**
```json
{
  "pause": {
    "mode": "void",  // or "free"
    "resumes_at": "2024-11-17T12:00:00Z"
  }
}
```

---

#### 6. Orders
```http
GET /v1/orders
GET /v1/orders/{id}
```

**Purpose:** Retrieve order information

**Key Attributes:**
- `store_id`
- `customer_id`
- `identifier` (order number)
- `order_number`
- `status` (pending, paid, failed, refunded)
- `total`
- `tax`
- `refunded`
- `created_at`

**Use Case:** Track one-time purchases and subscriptions

---

#### 7. Checkouts
```http
POST /v1/checkouts
GET /v1/checkouts/{id}
```

**Purpose:** Create checkout sessions

**Create Checkout Request:**
```json
{
  "data": {
    "type": "checkouts",
    "attributes": {
      "store_id": 12345,
      "variant_id": 67890,
      "custom_data": {
        "user_id": "abc123"
      },
      "checkout_options": {
        "embed": true,
        "media": false,
        "logo": true,
        "desc": true,
        "discount": true,
        "dark": false,
        "subscription_preview": true
      },
      "checkout_data": {
        "email": "user@example.com",
        "name": "John Doe",
        "billing_address": { ... },
        "tax_number": ""
      },
      "expires_at": "2024-10-18T12:00:00Z",
      "preview": false
    },
    "relationships": {
      "store": {
        "data": {
          "type": "stores",
          "id": "12345"
        }
      },
      "variant": {
        "data": {
          "type": "variants",
          "id": "67890"
        }
      }
    }
  }
}
```

**Checkout Response:**
```json
{
  "data": {
    "type": "checkouts",
    "id": "abc123",
    "attributes": {
      "url": "https://checkout.lemonsqueezy.com/buy/abc123",
      // ... other attributes
    }
  }
}
```

**Implementation:**
1. Create checkout session via API
2. Redirect user to `url` from response
3. User completes payment on LemonSqueezy
4. LemonSqueezy redirects to success URL
5. Webhook creates subscription in database

---

#### 8. Webhooks
```http
GET /v1/webhooks
GET /v1/webhooks/{id}
POST /v1/webhooks
PATCH /v1/webhooks/{id}
DELETE /v1/webhooks/{id}
```

**Purpose:** Manage webhook endpoints

**Create Webhook Request:**
```json
{
  "data": {
    "type": "webhooks",
    "attributes": {
      "url": "https://yourdomain.com/api/v1/subscriptions/webhooks/lemonsqueezy",
      "events": [
        "subscription_created",
        "subscription_updated",
        "subscription_cancelled",
        "subscription_resumed",
        "subscription_expired",
        "subscription_paused",
        "subscription_payment_success",
        "subscription_payment_failed",
        "subscription_payment_recovered",
        "order_created",
        "license_key_created"
      ],
      "secret": "your_webhook_signing_secret"
    }
  }
}
```

---

#### 9. License Keys
```http
GET /v1/license-keys
GET /v1/license-keys/{id}
POST /v1/license-keys
PATCH /v1/license-keys/{id}
DELETE /v1/license-keys/{id}
```

**Purpose:** Manage software license keys

**Key Attributes:**
- `store_id`
- `customer_id`
- `order_id`
- `product_id`
- `key` (the actual license key)
- `status` (active, inactive, expired, disabled)
- `activation_limit`
- `activation_usage`
- `expires_at`

**Use Cases:**
- Generate license keys for one-time purchases
- Validate license keys
- Track activations
- Manage expiration

---

## Subscription Management

### Subscription States

**Status Values:**
- `active` - Subscription is active and current
- `cancelled` - Subscription cancelled, access ends at period end
- `expired` - Subscription expired (no renewal)
- `paused` - Subscription paused (not billing)
- `past_due` - Payment failed, retry in progress
- `unpaid` - Payment failed after all retries

### Subscription Lifecycle

```
[Checkout Created]
        ↓
[Payment Success] → subscription_payment_success webhook
        ↓
   [Active] → subscription_created webhook
        ↓
   [Renewal] → subscription_payment_success webhook
        ↓
[Update Plan] → subscription_updated webhook
        ↓
    [Pause] → subscription_paused webhook
        ↓
   [Resume] → subscription_resumed webhook
        ↓
   [Cancel] → subscription_cancelled webhook
        ↓
   [Expire] → subscription_expired webhook
```

### Key Operations

#### Create Subscription
**Method:** Via checkout (recommended) or API

**Checkout Flow:**
1. Create checkout session with variant_id
2. User completes payment
3. `subscription_created` webhook fires
4. Store subscription in database

**Direct API Creation:**
```python
# Not recommended - use checkout instead
response = requests.post(
    "https://api.lemonsqueezy.com/v1/subscriptions",
    headers=headers,
    json={
        "data": {
            "type": "subscriptions",
            "attributes": {
                "store_id": 12345,
                "customer_id": 67890,
                "variant_id": 11111
            }
        }
    }
)
```

---

#### Retrieve Subscription
```python
response = requests.get(
    f"https://api.lemonsqueezy.com/v1/subscriptions/{subscription_id}",
    headers=headers
)

subscription = response.json()["data"]["attributes"]
status = subscription["status"]
renews_at = subscription["renews_at"]
```

---

#### Update Subscription (Change Plan)
```python
response = requests.patch(
    f"https://api.lemonsqueezy.com/v1/subscriptions/{subscription_id}",
    headers=headers,
    json={
        "data": {
            "type": "subscriptions",
            "id": subscription_id,
            "attributes": {
                "variant_id": new_variant_id
            }
        }
    }
)
```

**Proration:**
- LemonSqueezy handles proration automatically
- Upgrade: Prorated charge for remaining period
- Downgrade: Credit applied to next billing

---

#### Cancel Subscription
```python
# Cancel at end of period (recommended)
response = requests.delete(
    f"https://api.lemonsqueezy.com/v1/subscriptions/{subscription_id}",
    headers=headers
)

# Immediate cancellation (not recommended)
# User loses access immediately and may request refund
response = requests.delete(
    f"https://api.lemonsqueezy.com/v1/subscriptions/{subscription_id}?cancel_immediately=true",
    headers=headers
)
```

---

#### Pause Subscription
```python
response = requests.patch(
    f"https://api.lemonsqueezy.com/v1/subscriptions/{subscription_id}",
    headers=headers,
    json={
        "data": {
            "type": "subscriptions",
            "id": subscription_id,
            "attributes": {
                "pause": {
                    "mode": "void",  # Stop billing, no access
                    # "mode": "free",  # Stop billing, maintain access
                    "resumes_at": "2024-11-17T12:00:00Z"
                }
            }
        }
    }
)
```

---

#### Resume Subscription
```python
response = requests.patch(
    f"https://api.lemonsqueezy.com/v1/subscriptions/{subscription_id}",
    headers=headers,
    json={
        "data": {
            "type": "subscriptions",
            "id": subscription_id,
            "attributes": {
                "pause": None  # Remove pause
            }
        }
    }
)
```

---

### Customer Portal

**Purpose:** Allow customers to manage their subscriptions

**URL Structure:**
```
https://billing.lemonsqueezy.com/portal/{unique_portal_id}
```

**Features:**
- Update payment method
- View invoices
- Change subscription plan
- Cancel subscription
- Update billing information

**Implementation:**
1. Get customer portal URL from subscription attributes
2. Display "Manage Billing" button
3. Redirect user to portal URL

**Example:**
```python
subscription = get_subscription_from_api(subscription_id)
portal_url = subscription["urls"]["customer_portal"]

# Return to frontend
return {"portal_url": portal_url}
```

---

## Webhooks

### Overview

**Purpose:** Real-time notifications of subscription events

**Delivery:** HTTP POST to your endpoint

**Security:** HMAC signature verification required

**Retry:** Up to 4 attempts with exponential backoff

### Available Webhook Events

#### Subscription Events (9 total)

| Event | Description | When Triggered |
|-------|-------------|----------------|
| `subscription_created` | New subscription created | After successful checkout |
| `subscription_updated` | Subscription details changed | Plan change, payment method update |
| `subscription_cancelled` | Subscription cancelled | User or admin cancels |
| `subscription_resumed` | Subscription resumed | After being paused |
| `subscription_expired` | Subscription expired | After final period ends |
| `subscription_paused` | Subscription paused | Admin or user pauses |
| `subscription_payment_success` | Payment succeeded | Successful renewal or initial payment |
| `subscription_payment_failed` | Payment failed | Card declined or error |
| `subscription_payment_recovered` | Failed payment recovered | Retry successful after failure |

#### Other Events

| Event | Description | When Triggered |
|-------|-------------|----------------|
| `order_created` | New order created | One-time purchase or subscription |
| `order_refunded` | Order refunded | Full or partial refund |
| `license_key_created` | License key generated | For software products |

### Webhook Payload Structure

**Request Headers:**
```http
X-Signature: {hmac_sha256_signature}
Content-Type: application/json
```

**Payload Example:**
```json
{
  "meta": {
    "event_name": "subscription_created",
    "custom_data": {
      "user_id": "abc123"
    }
  },
  "data": {
    "type": "subscriptions",
    "id": "123456",
    "attributes": {
      "store_id": 12345,
      "customer_id": 67890,
      "order_id": 11111,
      "product_id": 22222,
      "variant_id": 33333,
      "product_name": "Pro Plan",
      "variant_name": "Monthly",
      "status": "active",
      "status_formatted": "Active",
      "card_brand": "visa",
      "card_last_four": "4242",
      "pause": null,
      "cancelled": false,
      "trial_ends_at": null,
      "billing_anchor": 1,
      "urls": {
        "update_payment_method": "https://...",
        "customer_portal": "https://..."
      },
      "renews_at": "2024-11-17T12:00:00.000000Z",
      "ends_at": null,
      "created_at": "2024-10-17T12:00:00.000000Z",
      "updated_at": "2024-10-17T12:00:00.000000Z",
      "test_mode": true
    },
    "relationships": {
      "store": { ... },
      "customer": { ... },
      "order": { ... },
      "product": { ... },
      "variant": { ... }
    }
  }
}
```

### Signature Verification

**Critical:** Always verify webhook signatures to prevent unauthorized requests

**Algorithm:** HMAC SHA-256

**Implementation:**
```python
import hmac
import hashlib

def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    Verify LemonSqueezy webhook signature

    Args:
        payload: Raw request body (bytes)
        signature: X-Signature header value
        secret: LEMONSQUEEZY_WEBHOOK_SECRET

    Returns:
        True if signature is valid, False otherwise
    """
    # Calculate expected signature
    calculated_signature = hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()

    # Timing-safe comparison (prevents timing attacks)
    return hmac.compare_digest(calculated_signature, signature)

# Usage in webhook endpoint
@router.post("/webhooks/lemonsqueezy")
async def handle_webhook(request: Request):
    # Get raw body (important: don't parse JSON yet)
    payload = await request.body()
    signature = request.headers.get("X-Signature")

    # Verify signature
    if not verify_webhook_signature(payload, signature, WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Now safe to parse JSON
    event = json.loads(payload)

    # Process event
    # ...

    return {"status": "success"}
```

### Idempotency

**Problem:** Webhooks may be delivered multiple times

**Solution:** Store event IDs and check for duplicates

**Implementation:**
```python
# Database model
class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id = Column(UUID, primary_key=True)
    event_id = Column(String, unique=True, nullable=False)  # From webhook
    event_type = Column(String, nullable=False)
    payload = Column(JSONB, nullable=False)
    processed = Column(Boolean, default=False)
    processed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

# Webhook handler
async def handle_webhook(event_data):
    event_id = event_data["data"]["id"]
    event_type = event_data["meta"]["event_name"]

    # Check if already processed
    existing = await db.query(WebhookEvent).filter(
        WebhookEvent.event_id == event_id
    ).first()

    if existing:
        # Already processed, return success (idempotent)
        return {"status": "already_processed"}

    # Store event
    webhook_event = WebhookEvent(
        event_id=event_id,
        event_type=event_type,
        payload=event_data,
        processed=False
    )
    await db.add(webhook_event)
    await db.commit()

    # Process event
    await process_subscription_event(event_data)

    # Mark as processed
    webhook_event.processed = True
    webhook_event.processed_at = datetime.utcnow()
    await db.commit()

    return {"status": "success"}
```

### Webhook Best Practices

1. **Quick Response**
   - Return HTTP 200 immediately
   - Process data asynchronously (background job)
   - Don't make the webhook wait for long operations

2. **Idempotency**
   - Store webhook event IDs
   - Check for duplicates before processing
   - Process events exactly once

3. **Error Handling**
   - Return 200 even if processing fails (store for retry)
   - Log all errors for debugging
   - Implement retry mechanism for failed processing

4. **Security**
   - Always verify signatures
   - Use HTTPS in production
   - Validate event data structure
   - Sanitize input before database operations

5. **Monitoring**
   - Log all webhook events
   - Track processing time
   - Alert on repeated failures
   - Monitor for missing events

6. **Testing**
   - Use test mode webhooks
   - Manually trigger events from dashboard
   - Test all event types
   - Verify signature verification works

### Webhook Endpoint Requirements

**URL:** Must be publicly accessible HTTPS endpoint (production)

**Method:** POST

**Response:** HTTP 200 for success

**Timeout:** Respond within 10 seconds

**Example Endpoint:**
```python
@router.post("/api/v1/subscriptions/webhooks/lemonsqueezy")
async def lemonsqueezy_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    # 1. Get payload and signature
    payload = await request.body()
    signature = request.headers.get("X-Signature")

    # 2. Verify signature
    if not verify_signature(payload, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # 3. Parse event
    event = json.loads(payload)
    event_type = event["meta"]["event_name"]

    # 4. Check idempotency
    if await is_duplicate_event(db, event["data"]["id"]):
        return {"status": "already_processed"}

    # 5. Store event
    await store_webhook_event(db, event)

    # 6. Route to handler (async)
    background_tasks.add_task(process_webhook, event_type, event)

    # 7. Return immediately
    return {"status": "received"}
```

---

## Checkout Implementation

### Checkout Overlay (Recommended)

**Purpose:** Seamless popup checkout without leaving your website

**Benefits:**
- ✅ User stays on your site
- ✅ Better conversion rates
- ✅ Consistent user experience
- ✅ Easy to implement

**Implementation Method 1: Automatic (lemon.js)**

```html
<!-- Add lemon.js to your page -->
<script src="https://assets.lemonsqueezy.com/lemon.js" defer></script>

<!-- Add checkout button with special class -->
<a
  href="https://checkout.lemonsqueezy.com/buy/{checkout_id}"
  class="lemonsqueezy-button"
>
  Subscribe Now
</a>

<!-- lemon.js automatically converts links to overlay -->
```

**Implementation Method 2: React/Vue/Modern Frameworks**

```typescript
// components/SubscribeButton.tsx
import { useEffect } from 'react';

export function SubscribeButton({ checkoutUrl }: { checkoutUrl: string }) {
  useEffect(() => {
    // Manually initialize lemon.js after component mount
    if (window.createLemonSqueezy) {
      window.createLemonSqueezy();
    }
  }, []);

  return (
    <a
      href={checkoutUrl}
      className="lemonsqueezy-button"
    >
      Subscribe Now
    </a>
  );
}

// Add to _document.tsx or index.html
<script src="https://assets.lemonsqueezy.com/lemon.js" defer></script>
```

**Implementation Method 3: Programmatic Checkout**

```typescript
// Full control over checkout process
async function handleCheckout() {
  try {
    // 1. Create checkout session via backend API
    const response = await apiClient.subscriptions.createCheckoutSession({
      plan_id: selectedPlanId,
      billing_period: billingPeriod,
      success_url: `${window.location.origin}/checkout/success`,
      cancel_url: `${window.location.origin}/checkout/cancel`
    });

    // 2. Get checkout URL from response
    const { checkout_url } = response;

    // 3. Open checkout (overlay or redirect)
    if (useOverlay) {
      // Use lemon.js overlay
      window.LemonSqueezy.Url.Open(checkout_url);
    } else {
      // Full redirect
      window.location.href = checkout_url;
    }
  } catch (error) {
    console.error('Checkout failed:', error);
    toast.error('Failed to start checkout');
  }
}
```

### Checkout Customization

**Available Options:**

```json
{
  "checkout_options": {
    "embed": true,           // Overlay vs redirect
    "media": false,          // Show/hide product media
    "logo": true,            // Show/hide store logo
    "desc": true,            // Show/hide product description
    "discount": true,        // Enable discount codes
    "dark": false,           // Dark mode
    "subscription_preview": true  // Show billing preview
  }
}
```

### Success and Cancel URLs

**Purpose:** Where to redirect after checkout

**Success URL:**
- User completes payment
- Redirected to success_url with query params
- Should show "Processing..." and poll for subscription

**Cancel URL:**
- User cancels checkout
- Redirected to cancel_url
- Should show "Checkout cancelled" message

**Example:**
```typescript
// Create checkout with URLs
const checkout = await createCheckout({
  variant_id: variantId,
  success_url: "https://wrext.com/checkout/success?session_id={checkout_id}",
  cancel_url: "https://wrext.com/checkout/cancel"
});

// LemonSqueezy replaces {checkout_id} with actual ID
```

**Success Page Implementation:**
```typescript
// app/checkout/success/page.tsx
export default function CheckoutSuccessPage() {
  const [status, setStatus] = useState<'processing' | 'success' | 'error'>('processing');
  const searchParams = useSearchParams();
  const sessionId = searchParams.get('session_id');

  useEffect(() => {
    const pollSubscription = async () => {
      let attempts = 0;
      const maxAttempts = 30;

      const interval = setInterval(async () => {
        attempts++;

        try {
          // Check if webhook processed
          const subscription = await apiClient.subscriptions.getCurrentPlan();

          if (subscription.status === 'active') {
            setStatus('success');
            clearInterval(interval);
            // Redirect to dashboard after 2 seconds
            setTimeout(() => router.push('/settings/subscription'), 2000);
          }
        } catch (error) {
          // Continue polling
        }

        if (attempts >= maxAttempts) {
          setStatus('error');
          clearInterval(interval);
        }
      }, 1000);
    };

    pollSubscription();
  }, []);

  return (
    <div>
      {status === 'processing' && <ProcessingMessage />}
      {status === 'success' && <SuccessMessage />}
      {status === 'error' && <TimeoutMessage />}
    </div>
  );
}
```

### Checkout Flow

```
1. User clicks "Subscribe" button
        ↓
2. Frontend creates checkout session (API call)
        ↓
3. Backend calls LemonSqueezy API
        ↓
4. LemonSqueezy returns checkout URL
        ↓
5. Frontend opens checkout (overlay or redirect)
        ↓
6. User enters payment information
        ↓
7. LemonSqueezy processes payment
        ↓
8. [SUCCESS] Redirect to success_url
        ↓
9. LemonSqueezy sends subscription_created webhook
        ↓
10. Backend processes webhook, creates subscription
        ↓
11. Success page polls for subscription
        ↓
12. Subscription found, redirect to dashboard
```

---

## Error Handling

### HTTP Status Codes

| Code | Meaning | Action |
|------|---------|--------|
| 200 | Success | Process response |
| 201 | Created | Resource created successfully |
| 204 | No Content | Request succeeded (no response body) |
| 400 | Bad Request | Fix request parameters |
| 401 | Unauthorized | Check API key |
| 403 | Forbidden | Check permissions |
| 404 | Not Found | Resource doesn't exist |
| 422 | Unprocessable Entity | Validation failed |
| 429 | Too Many Requests | Rate limited, wait 60s |
| 500 | Internal Server Error | Retry with exponential backoff |
| 503 | Service Unavailable | Retry with exponential backoff |

### Error Response Format

```json
{
  "errors": [
    {
      "status": "422",
      "detail": "The variant_id field is required.",
      "source": {
        "pointer": "/data/attributes/variant_id"
      }
    }
  ]
}
```

### Handling Errors

```python
def handle_api_call(url, headers, data=None):
    try:
        if data:
            response = requests.post(url, headers=headers, json=data)
        else:
            response = requests.get(url, headers=headers)

        # Check for errors
        if response.status_code == 400:
            errors = response.json().get("errors", [])
            raise ValueError(f"Bad request: {errors}")

        elif response.status_code == 401:
            raise AuthenticationError("Invalid API key")

        elif response.status_code == 404:
            raise NotFoundError("Resource not found")

        elif response.status_code == 422:
            errors = response.json().get("errors", [])
            raise ValidationError(f"Validation failed: {errors}")

        elif response.status_code == 429:
            # Rate limited
            time.sleep(60)
            return handle_api_call(url, headers, data)

        elif response.status_code >= 500:
            # Server error, retry with backoff
            raise ServerError("LemonSqueezy server error")

        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as e:
        logger.error(f"API call failed: {e}")
        raise
```

---

## Best Practices

### 1. Use Test Mode for Development

✅ **Always develop with test mode first**
- Create test store
- Use test API keys
- Test full integration
- Only switch to live when fully tested

❌ **Never develop directly in live mode**

---

### 2. Implement Proper Error Handling

✅ **Handle all error scenarios**
- Network failures
- API errors (400, 401, 404, 422, 429, 500)
- Webhook failures
- Database errors
- Timeout errors

✅ **Implement retry logic**
- Exponential backoff for transient errors
- Max retry attempts (3-5)
- Don't retry 4xx errors (except 429)

---

### 3. Webhook Security

✅ **Always verify signatures**
- Use timing-safe comparison
- Reject invalid signatures immediately
- Log suspicious requests

✅ **Process asynchronously**
- Return 200 immediately
- Process in background
- Implement retry for failed processing

✅ **Ensure idempotency**
- Store event IDs
- Check for duplicates
- Handle retry attempts gracefully

---

### 4. Rate Limit Management

✅ **Monitor rate limits**
- Check `X-Ratelimit-Remaining` header
- Slow down when approaching limit
- Use webhooks instead of polling

✅ **Cache responses**
- Cache product/variant data
- Cache customer data
- Reduce redundant API calls

---

### 5. Database Consistency

✅ **Use transactions**
- Atomic operations for subscription updates
- Rollback on failure
- Prevent partial updates

✅ **Handle webhook race conditions**
- Process events in order
- Lock records during updates
- Handle out-of-order events

---

### 6. Monitoring and Logging

✅ **Log all API calls**
- Request/response details
- Timing information
- Error details

✅ **Monitor webhooks**
- Track delivery rate
- Alert on failures
- Monitor processing time

✅ **Set up alerts**
- Failed payments
- Webhook failures
- API errors
- Rate limit warnings

---

### 7. User Experience

✅ **Use checkout overlay**
- Better conversion
- Seamless experience
- Keep user on your site

✅ **Show clear messaging**
- Processing states
- Success confirmation
- Error explanations

✅ **Handle edge cases**
- Webhook delays (polling)
- Payment failures
- Subscription expiration

---

## SDKs and Libraries

### Official SDKs

#### JavaScript/TypeScript
**Package:** `@lemonsqueezy/lemonsqueezy.js`

**Installation:**
```bash
npm install @lemonsqueezy/lemonsqueezy.js
```

**Usage:**
```typescript
import { lemonSqueezySetup, createCheckout } from '@lemonsqueezy/lemonsqueezy.js';

// Setup
lemonSqueezySetup({
  apiKey: process.env.LEMONSQUEEZY_API_KEY,
  onError: (error) => console.error('Error:', error),
});

// Create checkout
const checkout = await createCheckout({
  storeId: '12345',
  variantId: '67890',
});

console.log(checkout.data.attributes.url);
```

**Features:**
- Full TypeScript support
- Type-safe API calls
- Error handling built-in
- All endpoints covered

---

#### Laravel
**Package:** `@lemonsqueezy/laravel`

**Installation:**
```bash
composer require lemonsqueezy/laravel
```

**Usage:**
```php
use LemonSqueezy\Laravel\Checkout;

$checkout = Checkout::make()
    ->setStoreId(12345)
    ->setVariantId(67890)
    ->create();

return redirect($checkout['data']['attributes']['url']);
```

---

### Community SDKs

| Language | Package | Repository |
|----------|---------|------------|
| **Python** | `lemonsqueezy-py` | Community-maintained |
| **Go** | `lemonsqueezy-go` | Community-maintained |
| **Ruby** | `lemonsqueezy-ruby` | Community-maintained |
| **Rust** | `lemonsqueezy-rust` | Community-maintained |
| **Swift** | `LemonSqueezy-Swift` | Community-maintained |
| **PHP** | `lemonsqueezy-php` | Community-maintained |
| **Elixir** | `lemonsqueezy-elixir` | Community-maintained |
| **Java** | `lemonsqueezy-java` | Community-maintained |

**Note:** Community SDKs may have varying levels of maintenance and feature completeness.

---

### For WREXT Integration

**Recommendation:** Implement custom Python wrapper

**Reason:**
- No official Python SDK from LemonSqueezy
- Community SDKs may lack features or maintenance
- Custom implementation provides full control
- Can optimize for WREXT's specific needs

**Implementation:**
```python
# src/providers/payment/lemonsqueezy_provider.py
import requests
from typing import Dict, Optional

class LemonSqueezyProvider:
    BASE_URL = "https://api.lemonsqueezy.com/v1"

    def __init__(self, api_key: str, store_id: str):
        self.api_key = api_key
        self.store_id = store_id
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/vnd.api+json",
            "Content-Type": "application/vnd.api+json"
        }

    def create_checkout(
        self,
        variant_id: str,
        email: Optional[str] = None,
        custom_data: Optional[Dict] = None,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None
    ) -> Dict:
        """Create checkout session"""
        # Implementation
        pass

    def get_subscription(self, subscription_id: str) -> Dict:
        """Get subscription details"""
        # Implementation
        pass

    # ... more methods
```

---

## Implementation Checklist

### Phase 0: Discovery & Analysis ✅

- [x] Study LemonSqueezy API documentation
- [x] Study webhook documentation
- [x] Study checkout documentation
- [x] Create knowledge base document
- [x] Document key findings

### Phase 1: Backend Foundation

#### Database
- [ ] Create `webhook_events` table migration
- [ ] Create `licenses` table migration (optional)
- [ ] Add LemonSqueezy fields to `subscription_plans`
- [ ] Add LemonSqueezy fields to `user_subscriptions`
- [ ] Update subscription status enum

#### LemonSqueezy Provider
- [ ] Implement `LemonSqueezyProvider` class
- [ ] Implement `create_customer()`
- [ ] Implement `create_checkout_session()`
- [ ] Implement `get_subscription()`
- [ ] Implement `cancel_subscription()`
- [ ] Implement `update_subscription()`
- [ ] Implement `pause_subscription()`
- [ ] Implement `resume_subscription()`
- [ ] Implement `get_customer_portal_url()`
- [ ] Implement `verify_webhook_signature()`
- [ ] Add rate limit handling
- [ ] Add error handling

#### Webhook Handler
- [ ] Create webhook signature verification utility
- [ ] Create webhook routes
- [ ] Implement `subscription_created` handler
- [ ] Implement `subscription_updated` handler
- [ ] Implement `subscription_cancelled` handler
- [ ] Implement `subscription_expired` handler
- [ ] Implement `subscription_paused` handler
- [ ] Implement `subscription_resumed` handler
- [ ] Implement `subscription_payment_success` handler
- [ ] Implement `subscription_payment_failed` handler
- [ ] Implement `subscription_payment_recovered` handler
- [ ] Implement `order_created` handler
- [ ] Implement idempotency checking
- [ ] Add webhook event logging

#### API Endpoints
- [ ] Update checkout endpoint
- [ ] Add customer portal endpoint
- [ ] Update subscription status endpoint
- [ ] Update cancel endpoint
- [ ] Update upgrade/downgrade endpoints

### Phase 2: Frontend Implementation

#### Types
- [ ] Update subscription types
- [ ] Add LemonSqueezy-specific types
- [ ] Fix Stripe naming issues

#### API Client
- [ ] Add retry logic to API client
- [ ] Implement `createCheckoutSession()`
- [ ] Implement `getCustomerPortalUrl()`
- [ ] Add error handling

#### Components
- [ ] Create checkout success page
- [ ] Create checkout cancel page
- [ ] Create customer portal button
- [ ] Create payment method display
- [ ] Update pricing page
- [ ] Update subscription dashboard

#### State Management
- [ ] Add hierarchical query keys
- [ ] Implement cache invalidation helpers
- [ ] Add retry logic to React Query

### Phase 3: Testing

#### Backend Tests
- [ ] LemonSqueezy provider unit tests
- [ ] Webhook handler tests
- [ ] API route tests
- [ ] Integration tests

#### Frontend Tests
- [ ] Component tests
- [ ] API client tests
- [ ] E2E checkout flow test

### Phase 4: Deployment

#### Configuration
- [ ] Set production environment variables
- [ ] Configure production webhook endpoint
- [ ] Test with small real transaction
- [ ] Monitor for 48 hours

#### Documentation
- [ ] Update README
- [ ] Document deployment process
- [ ] Create troubleshooting guide

---

## Key Integration Points for WREXT

### 1. Checkout Flow
**Current:** Mock provider, instant activation
**New:** LemonSqueezy checkout → Webhook → Database update

### 2. Subscription Management
**Current:** Direct database updates
**New:** API calls to LemonSqueezy + Webhook sync

### 3. Customer Portal
**Current:** None
**New:** Redirect to LemonSqueezy portal

### 4. Payment Methods
**Current:** Not tracked
**New:** Stored from webhook data

### 5. Invoices
**Current:** Not available
**New:** Retrieved via API or portal

---

## Conclusion

This knowledge base covers all critical aspects of the LemonSqueezy integration:

✅ **API Architecture** - REST, JSON:API, rate limits
✅ **Authentication** - API keys, test/live modes
✅ **Subscription Management** - Full lifecycle support
✅ **Webhooks** - 9 events, signature verification, idempotency
✅ **Checkout** - Overlay implementation, customization
✅ **Best Practices** - Security, error handling, monitoring
✅ **Implementation Checklist** - Complete roadmap

**Next Steps:**
1. Complete Phase 0 by marking Task 0.3.4 complete
2. Begin Phase 1: Backend Foundation
3. Start with database migrations
4. Implement LemonSqueezy provider
5. Build webhook handlers

**Estimated Timeline:**
- Phase 1 (Backend): 3-4 weeks
- Phase 2 (Frontend): 2-3 weeks
- Phase 3 (Testing): 1-2 weeks
- Phase 4 (Deployment): 1 week

**Total: 7-10 weeks for complete integration**

---

**Document Status:** ✅ Complete
**Created:** 2025-10-17
**Last Updated:** 2025-10-17
**Next Task:** Begin Phase 1 - Database Migrations
