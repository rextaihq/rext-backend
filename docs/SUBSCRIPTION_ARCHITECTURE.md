# Subscription System Architecture

**Version:** 2.0
**Last Updated:** 2025-10-21
**Status:** Production Ready (LemonSqueezy Integrated)

---

## Overview

The WREXT subscription system is built using **LemonSqueezy** as the payment processor, with a clean abstraction layer that separates payment processing from core business logic.

### Key Design Principles

1. **Provider Abstraction** - All payment logic isolated behind a common interface
2. **Business Logic Independence** - Subscription management works independently of payment provider details
3. **Production-Ready Integration** - Complete LemonSqueezy integration with sandbox support
4. **Usage-Based Enforcement** - Real-time limit checking at the route level
5. **Data Consistency** - Single source of truth in WREXT database

---

## Architecture Components

### 1. Payment Provider Layer

**Location:** `src/providers/payment/`

```
src/providers/payment/
├── base_provider.py          # Abstract interface (PaymentProvider)
├── provider_factory.py       # Factory pattern for provider selection
└── providers/
    └── lemonsqueezy.py       # LemonSqueezy implementation (Production)
```

#### PaymentProvider Interface

```python
class PaymentProvider(ABC):
    """Abstract payment provider interface"""

    @abstractmethod
    async def create_customer(self, email, name, metadata) -> str:
        """Create customer, return customer_id"""

    @abstractmethod
    async def create_checkout_session(
        self, customer_id, price_id, success_url, cancel_url, metadata
    ) -> CheckoutSession:
        """Create checkout session"""

    @abstractmethod
    async def get_subscription(self, subscription_id) -> SubscriptionData:
        """Get subscription details"""

    @abstractmethod
    async def cancel_subscription(
        self, subscription_id, at_period_end=True
    ) -> SubscriptionData:
        """Cancel subscription"""

    @abstractmethod
    async def create_portal_session(
        self, customer_id, return_url
    ) -> str:
        """Create customer portal, return portal URL"""

    @abstractmethod
    async def verify_webhook_signature(
        self, payload, signature
    ) -> bool:
        """Verify webhook signature"""

    @abstractmethod
    async def parse_webhook_event(
        self, payload
    ) -> Dict[str, Any]:
        """Parse webhook event"""
```

**Benefits:**
- ✅ Production-ready payment processing with LemonSqueezy
- ✅ Sandbox mode for testing without real transactions
- ✅ Clean abstraction for future provider changes if needed
- ✅ Consistent error handling and webhook processing

---

### 2. Database Schema

#### Subscription Plans

```sql
CREATE TABLE subscription_plans (
    id UUID PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,  -- "free", "starter", "pro", "enterprise"
    display_name VARCHAR(200) NOT NULL,
    description TEXT,
    price_monthly DECIMAL(10,2) NOT NULL,
    price_yearly DECIMAL(10,2) NOT NULL,

    -- Provider-agnostic price IDs
    provider_price_id_monthly VARCHAR(255),  -- Maps to provider's monthly price
    provider_price_id_yearly VARCHAR(255),   -- Maps to provider's yearly price

    -- Resource limits
    max_workspaces INTEGER,                  -- -1 = unlimited
    max_members_per_workspace INTEGER,
    max_topics INTEGER,
    max_knowledge_items INTEGER,
    max_api_calls_per_month INTEGER,

    -- Features (JSONB for flexibility)
    features JSONB,

    -- Metadata
    is_active BOOLEAN DEFAULT TRUE,
    is_public BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

#### User Subscriptions

```sql
CREATE TABLE user_subscriptions (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    plan_id UUID REFERENCES subscription_plans(id),

    -- Provider data
    provider_subscription_id VARCHAR(255) UNIQUE,  -- Provider's subscription ID
    provider_customer_id VARCHAR(255),             -- Provider's customer ID

    -- Subscription details
    status VARCHAR(50),                -- active, trial, cancelled, expired, suspended
    billing_period VARCHAR(20),        -- monthly, yearly
    start_date TIMESTAMP,
    end_date TIMESTAMP,
    trial_end_date TIMESTAMP,
    cancelled_at TIMESTAMP,

    -- Usage tracking
    current_api_calls INTEGER DEFAULT 0,
    usage_reset_date TIMESTAMP,

    -- Metadata
    metadata JSONB,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,

    UNIQUE(user_id, status) WHERE status IN ('active', 'trial')
);
```

#### Users Table Addition

```sql
ALTER TABLE users ADD COLUMN provider_customer_id VARCHAR(255) UNIQUE;
CREATE INDEX idx_users_provider_customer_id ON users(provider_customer_id);
```

---

### 3. Core Services

#### SubscriptionService

**Location:** `src/services/subscription_service.py`

**Responsibilities:**
- Create/update/cancel subscriptions
- Sync with payment provider
- Manage subscription lifecycle
- Generate subscription + usage data

**Key Methods:**
```python
class SubscriptionService:
    async def create_subscription(...) -> UserSubscription
    async def get_user_subscription(user_id) -> Optional[UserSubscription]
    async def update_subscription_status(...) -> UserSubscription
    async def cancel_subscription(...) -> UserSubscription
    async def get_subscription_with_usage(user_id) -> Dict
```

#### UsageTrackingService

**Location:** `src/services/usage_tracking_service.py`

**Responsibilities:**
- Track resource usage (workspaces, members, topics, knowledge items, API calls)
- Check limits before resource creation
- Calculate usage percentages
- Reset monthly counters

**Key Methods:**
```python
class UsageTrackingService:
    async def get_usage_metrics(user_id) -> Dict
    async def check_limit(user_id, limit_type) -> Tuple[bool, int, int]
    async def increment_api_calls(user_id) -> None
    async def reset_monthly_usage(user_id) -> None
```

---

### 4. Usage Limit Enforcement

#### Middleware

**Location:** `src/api/middleware/usage_limiter.py`

**Checker Classes:**
- `WorkspaceLimitChecker` - Enforces `max_workspaces`
- `MemberLimitChecker` - Enforces `max_members_per_workspace`
- `TopicLimitChecker` - Enforces `max_topics`
- `KnowledgeItemLimitChecker` - Enforces `max_knowledge_items`
- `APICallLimiter` - Enforces `max_api_calls_per_month` with auto-increment

**Usage in Routes:**
```python
from src.api.middleware.usage_limiter import check_workspace_limit

@router.post("/workspaces")
async def create_workspace(
    data: WorkspaceSchema,
    _: None = Depends(check_workspace_limit()),  # ← Limit check
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # Create workspace logic
    pass
```

**Error Response (HTTP 429):**
```json
{
    "detail": "Workspace limit reached (5/5). Upgrade your plan to create more workspaces."
}
```

**Protected Routes:**
- `POST /workspace/create` → `check_workspace_limit()`
- `POST /{workspace_id}/invitations` → `check_member_limit()`
- `POST /{workspace_id}/invitations/bulk` → `check_member_limit()`
- `POST /topic/generate-topic` → `check_api_limit()`
- `POST /topic/save-topic` → `check_topic_limit()`
- `POST /{workspace_id}/knowledge/web` → `check_knowledge_item_limit()`
- `POST /{workspace_id}/knowledge/files` → `check_knowledge_item_limit()`
- `POST /{workspace_id}/knowledge/text` → `check_knowledge_item_limit()`

---

### 5. API Endpoints

#### Subscription Management

**Base Path:** `/api/v1/subscriptions`

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/checkout` | Create checkout session | ✅ |
| GET | `/portal` | Access billing portal | ✅ |
| GET | `/status` | Get subscription + usage | ✅ |
| GET | `/usage` | Get usage metrics only | ✅ |
| DELETE | `/cancel` | Cancel subscription | ✅ |
| GET | `/plans` | List public plans | ❌ |
| POST | `/webhooks/payment` | Handle provider webhooks | ❌ (signature verified) |

#### Example Responses

**GET /subscriptions/status:**
```json
{
    "success": true,
    "data": {
        "subscription": {
            "id": "uuid",
            "status": "active",
            "billing_period": "monthly",
            "start_date": "2025-10-01T00:00:00Z",
            "end_date": "2025-11-01T00:00:00Z"
        },
        "plan": {
            "name": "pro",
            "display_name": "Pro Plan",
            "price_monthly": 29.99,
            "max_workspaces": 10,
            "max_api_calls_per_month": 10000
        },
        "usage": {
            "workspaces": {
                "used": 3,
                "limit": 10,
                "percentage": 30,
                "unlimited": false
            },
            "api_calls": {
                "used": 1250,
                "limit": 10000,
                "percentage": 12,
                "unlimited": false,
                "reset_date": "2025-11-01T00:00:00Z"
            }
        }
    }
}
```

---

### 6. Frontend Integration

#### Pricing Page

**Location:** `wrext-admin/app/pricing/page.tsx`

**Features:**
- Monthly/yearly toggle
- Plan cards with features
- Real-time pricing calculation
- Checkout integration
- Mobile responsive

#### Billing Dashboard

**Location:** `wrext-admin/app/settings/billing/page.tsx`

**Features:**
- Current subscription details
- Usage metrics with progress bars
- Upgrade/cancel actions
- Billing portal access
- Usage alerts (approaching limits)

---

## Data Flow Diagrams

### Checkout Flow

```
User clicks "Subscribe" on Pricing Page
    ↓
Frontend: POST /api/v1/subscriptions/checkout
    {plan_id, billing_period}
    ↓
Backend: Check user, get plan
    ↓
Backend: Create/get provider customer
    ↓
Backend: Create checkout session with provider
    ↓
Provider returns: {session_id, checkout_url}
    ↓
Frontend: Redirect to checkout_url
    ↓
User completes payment on provider's page
    ↓
Provider: Sends webhook to /webhooks/payment
    ↓
Backend: Verify signature, parse event
    ↓
Backend: Create subscription in database
    ↓
Backend: Send welcome email
    ↓
User redirected to success_url
```

### Usage Limit Check Flow

```
User attempts to create resource (e.g., workspace)
    ↓
Route dependency: check_workspace_limit()
    ↓
Query user's subscription from database
    ↓
Get plan limits (max_workspaces)
    ↓
Count current workspaces for user
    ↓
IF count < limit:
    ✅ Allow request to proceed
ELSE:
    ❌ Return HTTP 429 with error message
```

---

## Configuration

### Environment Variables

```env
# Payment Provider (only lemonsqueezy supported)
PAYMENT_PROVIDER=lemonsqueezy

# Generic Settings
PAYMENT_CURRENCY=USD
PAYMENT_SUCCESS_URL=http://localhost:3000/checkout/success
PAYMENT_CANCEL_URL=http://localhost:3000/pricing

# LemonSqueezy Configuration
LEMONSQUEEZY_API_KEY=your_api_key
LEMONSQUEEZY_STORE_ID=your_store_id
LEMONSQUEEZY_WEBHOOK_SECRET=your_webhook_secret
LEMONSQUEEZY_SANDBOX_MODE=true  # Set to false for production
```

### Provider Configuration

**Location:** `src/config/payment_config.py`

```python
from pydantic_settings import BaseSettings
from typing import Literal

PaymentProviderType = Literal["lemonsqueezy"]

class PaymentSettings(BaseSettings):
    payment_provider: PaymentProviderType = "lemonsqueezy"

    lemonsqueezy_api_key: str = ""
    lemonsqueezy_store_id: str = ""
    lemonsqueezy_webhook_secret: str = ""

    class Config:
        env_file = ".env"
```

---

## Testing Strategy

### Unit Tests

**Location:** `tests/unit/providers/payment/test_lemonsqueezy_provider.py`

- Customer creation and management
- Checkout session creation
- Subscription lifecycle management
- Webhook signature verification
- Error handling

**Coverage:** Comprehensive coverage of LemonSqueezy integration

### Integration Tests

**Location:** `tests/integration/`

- Complete checkout flows with LemonSqueezy sandbox
- Webhook processing and subscription activation
- Usage tracking and limit enforcement
- Subscription upgrades and cancellations

### Manual Testing

Use LemonSqueezy sandbox mode for testing:

```bash
# Set sandbox mode
export LEMONSQUEEZY_SANDBOX_MODE=true
export PAYMENT_PROVIDER=lemonsqueezy

# Start backend
uvicorn src.api.server:app --reload

# Test checkout (returns LemonSqueezy checkout URL)
curl -X POST http://localhost:2024/api/v1/subscriptions/checkout \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"plan_id": "uuid", "billing_period": "monthly"}'
```

---

## LemonSqueezy Integration Details

### Supported Features

1. **Checkout Sessions** - Create hosted checkout pages
2. **Customer Management** - Automatic customer creation and updates
3. **Subscription Lifecycle** - Full subscription management (create, update, cancel, resume)
4. **Webhook Events** - 12 event types supported
5. **Customer Portal** - Managed billing portal for customers
6. **License Management** - Support for lifetime deals (LTD)
7. **Sandbox Mode** - Testing without real transactions

### Webhook Events

Supported webhook events:
- `subscription_created` - New recurring subscription
- `subscription_updated` - Subscription plan/status change
- `subscription_cancelled` - Subscription cancelled
- `subscription_resumed` - Paused subscription resumed
- `subscription_expired` - Subscription expired
- `subscription_paused` - Subscription paused
- `subscription_payment_success` - Payment successful
- `subscription_payment_failed` - Payment failed
- `subscription_payment_recovered` - Payment recovered after failure
- `order_created` - One-time purchase (LTD)
- `order_refunded` - Order refunded
- `license_key_created` - License key generated

---

## Security Considerations

1. **Webhook Signature Verification**
   - All webhooks must verify signature before processing
   - Prevents unauthorized subscription modifications

2. **Idempotency**
   - Webhook handlers check for duplicate events
   - Prevents double-processing of payments

3. **Customer Data**
   - Provider customer IDs stored securely
   - No payment card data stored in WREXT

4. **Access Control**
   - Only subscription owner can cancel
   - Admin endpoints require super_admin role

---

## Monitoring & Alerts

### Key Metrics

- Subscription creation rate
- Cancellation rate
- Failed payment rate
- Usage limit hit rate
- API call usage trends

### Logging

All subscription events logged with context:
- Subscription created/updated/cancelled
- Usage limit exceeded
- Webhook received
- Provider API errors

---

## Troubleshooting

### Common Issues

**Issue:** "Workspace limit reached" but user hasn't created any workspaces
- **Solution:** Check if subscription is active (`status = 'active'`)
- **SQL:** `SELECT * FROM user_subscriptions WHERE user_id = '<uuid>'`

**Issue:** API calls not incrementing
- **Solution:** Ensure route has `Depends(check_api_limit())`
- **Check:** `SELECT current_api_calls FROM user_subscriptions WHERE user_id = '<uuid>'`

**Issue:** Webhook not processing
- **Solution:** Check signature verification
- **Logs:** Search for "webhook" in application logs
- **Test:** Use provider's webhook testing tool

---

## Future Enhancements

- [ ] Coupon/promo code support
- [ ] Usage-based billing
- [ ] Tiered pricing within plans
- [ ] Enhanced subscription analytics dashboard
- [ ] Automated dunning management
- [ ] Multi-currency support
- [ ] Team/workspace-level subscriptions

---

## References

- [Payment Provider Base Interface](../src/providers/payment/base_provider.py)
- [LemonSqueezy Provider Implementation](../src/providers/payment/providers/lemonsqueezy.py)
- [Usage Limiter Middleware](../src/api/middleware/usage_limiter.py)
- [Subscription Service](../src/services/subscription_service.py)
- [Usage Tracking Service](../src/services/usage_tracking_service.py)
- [LemonSqueezy Integration Documentation](./LEMONSQUEEZY_PROVIDER_USAGE.md)

---

**Document Version:** 2.0
**Last Review:** 2025-10-21
**Next Review:** Quarterly
