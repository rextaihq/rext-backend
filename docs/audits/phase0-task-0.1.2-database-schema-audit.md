# Phase 0 - Task 0.1.2: Database Schema Audit

**Date:** 2025-10-17
**Task:** Audit database schema for payment/subscription data
**Status:** ✅ Complete
**Files Audited:**
- `src/api/models/subscription_models/subscriptions.py`
- `src/api/models/subscription_models/plans.py`
- `src/api/models/subscription_models/payment_methods.py`
- `src/api/models/user_models/users.py`

---

## Executive Summary

The existing subscription database schema provides a solid foundation for LemonSqueezy integration, with provider-agnostic fields already in place. However, several new fields and tables are required to support LemonSqueezy-specific features including webhook processing, license management, and enhanced subscription lifecycle tracking.

**Key Finding:** The architecture is well-designed with provider abstraction already implemented. We need to **extend** existing tables with LemonSqueezy-specific fields and **add** two new tables for webhook tracking and license management.

---

## 1. Current Schema Analysis

### 1.1 Existing Tables Overview

| Table | Status | Purpose | LemonSqueezy Ready? |
|-------|--------|---------|---------------------|
| `users` | ✅ Exists | User accounts with payment provider customer ID | Mostly Ready |
| `subscription_plans` | ✅ Exists | Available subscription tiers with pricing | Needs Fields |
| `user_subscriptions` | ✅ Exists | Active user subscriptions | Needs Fields |
| `payment_methods` | ✅ Exists | User payment methods | Ready (managed by LemonSqueezy) |
| `webhook_events` | ❌ Missing | Webhook event tracking for idempotency | **Must Create** |
| `licenses` | ❌ Missing | License keys for one-time purchases | **Must Create** |

### 1.2 Schema Strengths

✅ **Provider-agnostic design** - Fields like `provider_subscription_id`, `provider_customer_id` already exist
✅ **Enum-based status tracking** - Clean status management with `SubscriptionStatus` enum
✅ **Flexible metadata** - JSONB columns for extensibility
✅ **Proper relationships** - Foreign keys and relationships well-defined
✅ **Audit trails** - `created_at`, `updated_at` timestamps on all tables
✅ **Usage tracking** - Current API call tracking built-in

### 1.3 Schema Gaps

❌ **No webhook event tracking** - Idempotency not possible without event table
❌ **No license management** - Can't support one-time purchases
❌ **Missing LemonSqueezy-specific IDs** - Need variant IDs, product IDs
❌ **No cancellation metadata** - Can't track at_period_end vs immediate
❌ **Limited subscription metadata** - Need trial info, renewal dates
❌ **No webhook retry tracking** - Can't monitor webhook processing health

---

## 2. Table-by-Table Analysis

### 2.1 `users` Table

**File:** `src/api/models/user_models/users.py`
**Lines:** 16-62

#### Current Schema

```python
class Users(Base, SerializableMixin):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    username = Column(String(100), unique=True, nullable=False)
    # ... other user fields ...

    # Payment Provider Integration
    provider_customer_id = Column(String(255), unique=True, index=True)  # ✅ Already exists!

    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
```

#### Assessment

**Status:** ✅ **Ready for LemonSqueezy**

**What's Good:**
- `provider_customer_id` field already exists and is indexed
- Unique constraint ensures one customer ID per user
- Provider-agnostic naming (works for any payment provider)

**What's Missing:**
- Nothing critical! This table is ready.

**Optional Enhancements:**
```python
# Consider adding (low priority):
provider_type = Column(String(50))  # Track which provider (mock, lemonsqueezy, etc.)
billing_email = Column(String(255))  # If different from user email
```

#### Migration Required

**None** - Table is ready as-is.

---

### 2.2 `subscription_plans` Table

**File:** `src/api/models/subscription_models/plans.py`
**Lines:** 11-47

#### Current Schema

```python
class SubscriptionPlan(Base, SerializableMixin):
    __tablename__ = "subscription_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False)
    display_name = Column(String(150), nullable=False)
    description = Column(Text)

    # Pricing
    price_monthly = Column(Numeric(10, 2), default=0.00)
    price_yearly = Column(Numeric(10, 2), default=0.00)

    # Feature limits
    features = Column(JSONB, default=dict)
    max_workspaces = Column(Integer, default=1)
    max_members_per_workspace = Column(Integer, default=5)
    max_topics = Column(Integer, default=100)
    max_knowledge_items = Column(Integer, default=1000)
    max_api_calls_per_month = Column(Integer, default=10000)

    # Status
    is_active = Column(Boolean, default=True)
    is_public = Column(Boolean, default=True)

    # Payment Provider Integration
    provider_price_id_monthly = Column(String(255))  # ✅ Exists but needs companion
    provider_price_id_yearly = Column(String(255))   # ✅ Exists but needs companion

    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
```

#### Assessment

**Status:** ⚠️ **Needs Additional Fields**

**What's Good:**
- Provider price IDs already exist for monthly/yearly billing
- Feature limits well-defined
- Provider-agnostic design

**What's Missing:**
- LemonSqueezy product ID (parent of variants)
- LemonSqueezy variant IDs (LemonSqueezy uses product → variants structure)
- Store ID (for multi-store support)

**Rationale:**
LemonSqueezy has a hierarchy: Store → Product → Variant (Price)
- Product: e.g., "WREXT Pro Plan"
- Variants: e.g., "Pro Monthly" vs "Pro Yearly"
- Current `provider_price_id_*` fields can store variant IDs, but we need product ID too

#### Required Fields

```python
# Add these fields to SubscriptionPlan:
lemonsqueezy_product_id = Column(String(255))      # LemonSqueezy product ID
lemonsqueezy_variant_id_monthly = Column(String(255))  # Monthly variant ID
lemonsqueezy_variant_id_yearly = Column(String(255))   # Yearly variant ID
lemonsqueezy_store_id = Column(String(255))        # Store ID (for multi-store)
```

**Why both provider_price_id and lemonsqueezy_variant_id?**
- Keep `provider_price_id_*` for provider-agnostic code
- Add `lemonsqueezy_variant_id_*` for LemonSqueezy-specific operations
- Factory can map between them

#### Migration Required

**Yes** - Add 4 new nullable string columns.

**Migration Name:** `add_lemonsqueezy_fields_to_plans`

---

### 2.3 `user_subscriptions` Table

**File:** `src/api/models/subscription_models/subscriptions.py`
**Lines:** 28-73

#### Current Schema

```python
class UserSubscription(Base, SerializableMixin):
    __tablename__ = "user_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    plan_id = Column(UUID(as_uuid=True), ForeignKey("subscription_plans.id"))

    # Subscription details
    status = Column(SQLEnum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE)
    billing_period = Column(SQLEnum(BillingPeriod), default=BillingPeriod.MONTHLY)

    # Dates
    start_date = Column(TIMESTAMP, default=datetime.utcnow)
    end_date = Column(TIMESTAMP, nullable=True)
    trial_end_date = Column(TIMESTAMP, nullable=True)
    cancelled_at = Column(TIMESTAMP, nullable=True)

    # Payment Provider Integration
    provider_subscription_id = Column(String(255), unique=True)  # ✅ Exists!
    provider_customer_id = Column(String(255))  # ✅ Exists!

    # Usage tracking
    current_api_calls = Column(Integer, default=0)
    usage_reset_date = Column(TIMESTAMP, default=datetime.utcnow)

    # Metadata
    subscription_metadata = Column(JSONB, default=dict)

    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
```

#### Assessment

**Status:** ⚠️ **Needs Additional Fields**

**What's Good:**
- Provider subscription ID and customer ID already exist
- Trial tracking with `trial_end_date`
- Flexible metadata via JSONB
- Proper cascading delete on user deletion

**What's Missing:**
1. **Order ID** - For initial purchase transaction
2. **Variant ID** - Which price variant was purchased
3. **Cancellation details** - At period end vs immediate
4. **Renewal tracking** - When next billing occurs
5. **Payment failure tracking** - Grace period management
6. **Card details** - Last 4 digits, brand (for UI display)

#### SubscriptionStatus Enum Analysis

```python
class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    TRIAL = "trial"
    SUSPENDED = "suspended"
```

**Assessment:** ⚠️ **Missing statuses for LemonSqueezy**

**LemonSqueezy Statuses:**
- `on_trial` - Currently in trial period
- `active` - ✅ Exists
- `paused` - Payment failed, in grace period
- `past_due` - Payment failed, grace period over
- `cancelled` - ✅ Exists (user cancelled)
- `expired` - ✅ Exists

**Recommended Enum Updates:**
```python
class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    TRIAL = "trial"  # Rename from TRIAL
    PAUSED = "paused"  # NEW - Payment recovery in progress
    PAST_DUE = "past_due"  # NEW - Payment failed
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    SUSPENDED = "suspended"  # Admin action
```

#### Required Fields

```python
# Add these fields to UserSubscription:
provider_order_id = Column(String(255))  # Initial order/transaction ID
provider_variant_id = Column(String(255))  # Variant/price ID purchased
cancel_at_period_end = Column(Boolean, default=False)  # Cancellation behavior
renews_at = Column(TIMESTAMP, nullable=True)  # Next billing date
paused_at = Column(TIMESTAMP, nullable=True)  # When payment recovery started
card_brand = Column(String(50), nullable=True)  # visa, mastercard, etc.
card_last_four = Column(String(4), nullable=True)  # Last 4 digits
urls = Column(JSONB, default=dict)  # update_payment_method, customer_portal, etc.
```

**Why `urls` JSONB?**
- LemonSqueezy provides subscription-specific URLs (update payment, invoices, etc.)
- Flexible storage for provider-specific URLs
- Example: `{"update_payment_method": "https://...", "customer_portal": "https://..."}`

#### Migration Required

**Yes** - Add 8 new fields, update enum.

**Migration Name:** `add_lemonsqueezy_subscription_fields`

---

### 2.4 `payment_methods` Table

**File:** `src/api/models/subscription_models/payment_methods.py`
**Lines:** 11-49

#### Current Schema

```python
class PaymentMethod(Base, SerializableMixin):
    __tablename__ = "payment_methods"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))

    # Payment provider integration
    provider_payment_method_id = Column(String(255), unique=True)
    provider_customer_id = Column(String(255))

    # Payment method details
    type = Column(String(50))  # card, bank_account, etc.
    is_default = Column(Boolean, default=False)
    status = Column(String(50), default="active")

    # Card-specific fields
    card_brand = Column(String(50))
    card_last4 = Column(String(4))
    card_exp_month = Column(Integer())
    card_exp_year = Column(Integer())

    # Billing details
    billing_email = Column(String(255))
    payment_metadata = Column(JSONB, default=dict)

    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
```

#### Assessment

**Status:** ✅ **Ready for LemonSqueezy**

**What's Good:**
- Comprehensive payment method tracking
- Card details for UI display
- Provider-agnostic design
- Proper user relationship with cascade delete

**What's Missing:**
- Nothing critical!

**Note:** LemonSqueezy manages payment methods through their customer portal. This table can be used for caching/display, but LemonSqueezy is the source of truth.

**Recommendation:** Keep table as-is. Optionally sync from LemonSqueezy API when user accesses payment methods page.

#### Migration Required

**None** - Table is ready as-is.

---

## 3. Missing Tables Analysis

### 3.1 NEW TABLE: `webhook_events`

**Purpose:** Track all webhook events from LemonSqueezy for idempotency, debugging, and audit trails.

**Priority:** 🔴 **CRITICAL** - Required for production

**Rationale:**
- Webhooks can be delivered multiple times (network issues, retries)
- Must prevent duplicate processing (e.g., creating same subscription twice)
- Need audit trail for debugging webhook issues
- LemonSqueezy provides unique event ID per webhook

#### Proposed Schema

```python
class WebhookEvent(Base, SerializableMixin):
    """Webhook event tracking for idempotency and audit."""
    __tablename__ = "webhook_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # LemonSqueezy event identification
    provider_event_id = Column(String(255), unique=True, nullable=False, index=True)
    event_name = Column(String(100), nullable=False, index=True)  # subscription_created, etc.

    # Processing status
    status = Column(String(50), default="pending", nullable=False, index=True)
    # Status values: pending, processing, processed, failed, skipped

    # Event data
    payload = Column(JSONB, nullable=False)  # Full webhook payload
    headers = Column(JSONB)  # Request headers (for debugging)

    # Processing details
    processed_at = Column(TIMESTAMP, nullable=True)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)

    # Relationships (optional - link to affected resources)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("user_subscriptions.id"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Audit
    received_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False, index=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
```

#### Indexes

**Critical for performance:**

```python
# Unique constraint for idempotency
CREATE UNIQUE INDEX idx_webhook_events_provider_event_id
ON webhook_events(provider_event_id);

# Fast status lookups
CREATE INDEX idx_webhook_events_status
ON webhook_events(status) WHERE status != 'processed';

# Event type filtering
CREATE INDEX idx_webhook_events_event_name
ON webhook_events(event_name);

# Time-based queries (cleanup old events)
CREATE INDEX idx_webhook_events_received_at
ON webhook_events(received_at DESC);

# Failed event monitoring
CREATE INDEX idx_webhook_events_failed
ON webhook_events(status, retry_count) WHERE status = 'failed';
```

#### Webhook Processing Flow

```python
async def process_webhook(event_id: str, event_name: str, payload: dict):
    # 1. Check if event already processed (idempotency)
    existing = await db.query(WebhookEvent).filter_by(
        provider_event_id=event_id
    ).first()

    if existing and existing.status == "processed":
        logger.info(f"Webhook {event_id} already processed, skipping")
        return

    # 2. Create or update event record
    webhook_event = existing or WebhookEvent(
        provider_event_id=event_id,
        event_name=event_name,
        payload=payload,
        status="processing"
    )

    # 3. Process event
    try:
        await handle_event(event_name, payload)
        webhook_event.status = "processed"
        webhook_event.processed_at = datetime.utcnow()
    except Exception as e:
        webhook_event.status = "failed"
        webhook_event.error_message = str(e)
        webhook_event.retry_count += 1
        raise
    finally:
        await db.commit()
```

#### Migration Required

**Yes** - Create new table with indexes.

**Migration Name:** `create_webhook_events_table`

---

### 3.2 NEW TABLE: `licenses`

**Purpose:** Store and manage license keys for one-time purchases (TLDs, etc.).

**Priority:** 🟡 **HIGH** - Required for one-time purchase feature

**Rationale:**
- LemonSqueezy supports one-time purchases with license keys
- Need to track which user owns which license
- Support license activation limits (e.g., max 5 domains)
- Track license status (active, inactive, expired, revoked)

#### Proposed Schema

```python
class License(Base, SerializableMixin):
    """License keys for one-time purchases."""
    __tablename__ = "licenses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # LemonSqueezy integration
    provider_license_id = Column(String(255), unique=True, nullable=False, index=True)
    provider_license_key = Column(String(500), unique=True, nullable=False, index=True)
    provider_order_id = Column(String(255), nullable=False)
    provider_product_id = Column(String(255), nullable=False)

    # License details
    status = Column(String(50), default="active", nullable=False, index=True)
    # Status values: active, inactive, expired, revoked

    # Activation tracking
    activation_limit = Column(Integer, nullable=True)  # Max activations (null = unlimited)
    activation_count = Column(Integer, default=0)
    activations = Column(JSONB, default=list)  # List of activation records
    # Example: [{"domain": "example.com", "activated_at": "2025-01-01T00:00:00Z"}]

    # Dates
    expires_at = Column(TIMESTAMP, nullable=True)  # Null for lifetime licenses
    disabled_at = Column(TIMESTAMP, nullable=True)

    # Metadata
    license_metadata = Column(JSONB, default=dict)

    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("Users", backref="licenses")
```

#### Indexes

```python
# Fast license key lookup
CREATE UNIQUE INDEX idx_licenses_provider_license_key
ON licenses(provider_license_key);

# User's licenses
CREATE INDEX idx_licenses_user_id
ON licenses(user_id);

# Status filtering
CREATE INDEX idx_licenses_status
ON licenses(status) WHERE status = 'active';

# Expiring licenses (for cleanup/notifications)
CREATE INDEX idx_licenses_expires_at
ON licenses(expires_at) WHERE expires_at IS NOT NULL;
```

#### License Validation Flow

```python
async def validate_license(license_key: str, domain: str = None):
    # 1. Find license
    license = await db.query(License).filter_by(
        provider_license_key=license_key,
        status="active"
    ).first()

    if not license:
        raise InvalidLicenseError("License not found or inactive")

    # 2. Check expiration
    if license.expires_at and license.expires_at < datetime.utcnow():
        license.status = "expired"
        await db.commit()
        raise ExpiredLicenseError("License has expired")

    # 3. Check activation limit
    if license.activation_limit:
        if license.activation_count >= license.activation_limit:
            # Check if domain already activated
            if domain and domain not in [a["domain"] for a in license.activations]:
                raise ActivationLimitError("Activation limit reached")

    # 4. Record activation (if new domain)
    if domain and domain not in [a["domain"] for a in license.activations]:
        license.activations.append({
            "domain": domain,
            "activated_at": datetime.utcnow().isoformat()
        })
        license.activation_count += 1
        await db.commit()

    return license
```

#### Migration Required

**Yes** - Create new table with indexes.

**Migration Name:** `create_licenses_table`

---

## 4. Migration Strategy

### 4.1 Migration Order

**Must be executed in this order to respect dependencies:**

1. **Migration 1:** `add_lemonsqueezy_fields_to_plans`
   - Add 4 fields to `subscription_plans`
   - No dependencies

2. **Migration 2:** `update_subscription_status_enum`
   - Add new enum values to `SubscriptionStatus`
   - No dependencies

3. **Migration 3:** `add_lemonsqueezy_subscription_fields`
   - Add 8 fields to `user_subscriptions`
   - Depends on: Migration 2 (for enum updates)

4. **Migration 4:** `create_webhook_events_table`
   - Create new `webhook_events` table
   - Depends on: Migration 3 (for FK to user_subscriptions)

5. **Migration 5:** `create_licenses_table`
   - Create new `licenses` table
   - No dependencies (can run anytime)

### 4.2 Migration Files Structure

```
alembic/versions/
├── XXXXXX_add_lemonsqueezy_fields_to_plans.py
├── YYYYYY_update_subscription_status_enum.py
├── ZZZZZZ_add_lemonsqueezy_subscription_fields.py
├── AAAAAA_create_webhook_events_table.py
└── BBBBBB_create_licenses_table.py
```

### 4.3 Data Migration Considerations

**No data migration needed!**

Rationale:
- All new fields are nullable or have defaults
- Existing subscriptions continue working
- LemonSqueezy fields populated on next subscription event
- Mock provider subscriptions unaffected (fields remain null)

**Edge Case:** Existing active subscriptions won't have LemonSqueezy IDs

Solution:
```python
# Add this to webhook handlers:
if subscription.provider_subscription_id is None:
    # First LemonSqueezy event for this subscription
    # Populate all LemonSqueezy fields
    subscription.provider_subscription_id = event_data["subscription_id"]
    subscription.provider_variant_id = event_data["variant_id"]
    # ... etc
```

### 4.4 Rollback Strategy

Each migration includes proper `downgrade()` function:

```python
def upgrade():
    # Add fields/tables
    pass

def downgrade():
    # Remove fields/tables in reverse order
    pass
```

**Testing rollback:**
```bash
# Upgrade
alembic upgrade head

# Test rollback
alembic downgrade -1

# Verify schema
psql -d wrext -c "\d user_subscriptions"

# Re-upgrade
alembic upgrade head
```

---

## 5. Detailed Migration Specifications

### 5.1 Migration 1: Add LemonSqueezy Fields to Plans

**File:** `alembic/versions/XXXXXX_add_lemonsqueezy_fields_to_plans.py`

```python
"""add_lemonsqueezy_fields_to_plans

Revision ID: XXXXXX
Revises: <latest_revision>
Create Date: 2025-10-17
"""

def upgrade() -> None:
    # Add LemonSqueezy-specific fields to subscription_plans
    op.add_column('subscription_plans',
        sa.Column('lemonsqueezy_product_id', sa.String(255), nullable=True))
    op.add_column('subscription_plans',
        sa.Column('lemonsqueezy_variant_id_monthly', sa.String(255), nullable=True))
    op.add_column('subscription_plans',
        sa.Column('lemonsqueezy_variant_id_yearly', sa.String(255), nullable=True))
    op.add_column('subscription_plans',
        sa.Column('lemonsqueezy_store_id', sa.String(255), nullable=True))

    # Create indexes for faster lookups
    op.create_index('ix_subscription_plans_lemonsqueezy_product_id',
        'subscription_plans', ['lemonsqueezy_product_id'])

def downgrade() -> None:
    op.drop_index('ix_subscription_plans_lemonsqueezy_product_id')
    op.drop_column('subscription_plans', 'lemonsqueezy_store_id')
    op.drop_column('subscription_plans', 'lemonsqueezy_variant_id_yearly')
    op.drop_column('subscription_plans', 'lemonsqueezy_variant_id_monthly')
    op.drop_column('subscription_plans', 'lemonsqueezy_product_id')
```

**SQL Preview:**
```sql
-- Upgrade
ALTER TABLE subscription_plans ADD COLUMN lemonsqueezy_product_id VARCHAR(255);
ALTER TABLE subscription_plans ADD COLUMN lemonsqueezy_variant_id_monthly VARCHAR(255);
ALTER TABLE subscription_plans ADD COLUMN lemonsqueezy_variant_id_yearly VARCHAR(255);
ALTER TABLE subscription_plans ADD COLUMN lemonsqueezy_store_id VARCHAR(255);
CREATE INDEX ix_subscription_plans_lemonsqueezy_product_id ON subscription_plans(lemonsqueezy_product_id);

-- Downgrade
DROP INDEX ix_subscription_plans_lemonsqueezy_product_id;
ALTER TABLE subscription_plans DROP COLUMN lemonsqueezy_store_id;
ALTER TABLE subscription_plans DROP COLUMN lemonsqueezy_variant_id_yearly;
ALTER TABLE subscription_plans DROP COLUMN lemonsqueezy_variant_id_monthly;
ALTER TABLE subscription_plans DROP COLUMN lemonsqueezy_product_id;
```

---

### 5.2 Migration 2: Update Subscription Status Enum

**File:** `alembic/versions/YYYYYY_update_subscription_status_enum.py`

```python
"""update_subscription_status_enum

Revision ID: YYYYYY
Revises: XXXXXX
Create Date: 2025-10-17
"""

def upgrade() -> None:
    # Add new enum values for LemonSqueezy subscription statuses
    op.execute("ALTER TYPE subscriptionstatus ADD VALUE 'paused'")
    op.execute("ALTER TYPE subscriptionstatus ADD VALUE 'past_due'")

def downgrade() -> None:
    # Note: PostgreSQL doesn't support removing enum values
    # Instead, we'd need to recreate the enum type
    # For safety, we'll just log a warning
    op.execute("-- Cannot remove enum values in PostgreSQL without recreating type")
    op.execute("-- Manual intervention required if rollback needed")
```

**Important:** PostgreSQL doesn't allow removing enum values. If rollback is critical, we need to:
1. Create new enum type with old values
2. Alter column to use new type
3. Drop old type
4. Rename new type to old name

**Alternative:** Use string column instead of enum (more flexible, slightly less type-safe)

---

### 5.3 Migration 3: Add LemonSqueezy Subscription Fields

**File:** `alembic/versions/ZZZZZZ_add_lemonsqueezy_subscription_fields.py`

```python
"""add_lemonsqueezy_subscription_fields

Revision ID: ZZZZZZ
Revises: YYYYYY
Create Date: 2025-10-17
"""

def upgrade() -> None:
    # Add LemonSqueezy-specific fields to user_subscriptions
    op.add_column('user_subscriptions',
        sa.Column('provider_order_id', sa.String(255), nullable=True))
    op.add_column('user_subscriptions',
        sa.Column('provider_variant_id', sa.String(255), nullable=True))
    op.add_column('user_subscriptions',
        sa.Column('cancel_at_period_end', sa.Boolean(), default=False, nullable=False))
    op.add_column('user_subscriptions',
        sa.Column('renews_at', sa.TIMESTAMP(), nullable=True))
    op.add_column('user_subscriptions',
        sa.Column('paused_at', sa.TIMESTAMP(), nullable=True))
    op.add_column('user_subscriptions',
        sa.Column('card_brand', sa.String(50), nullable=True))
    op.add_column('user_subscriptions',
        sa.Column('card_last_four', sa.String(4), nullable=True))
    op.add_column('user_subscriptions',
        sa.Column('urls', sa.JSON(), default=dict, nullable=False))

    # Create indexes
    op.create_index('ix_user_subscriptions_provider_order_id',
        'user_subscriptions', ['provider_order_id'])
    op.create_index('ix_user_subscriptions_provider_variant_id',
        'user_subscriptions', ['provider_variant_id'])
    op.create_index('ix_user_subscriptions_renews_at',
        'user_subscriptions', ['renews_at'])

def downgrade() -> None:
    op.drop_index('ix_user_subscriptions_renews_at')
    op.drop_index('ix_user_subscriptions_provider_variant_id')
    op.drop_index('ix_user_subscriptions_provider_order_id')
    op.drop_column('user_subscriptions', 'urls')
    op.drop_column('user_subscriptions', 'card_last_four')
    op.drop_column('user_subscriptions', 'card_brand')
    op.drop_column('user_subscriptions', 'paused_at')
    op.drop_column('user_subscriptions', 'renews_at')
    op.drop_column('user_subscriptions', 'cancel_at_period_end')
    op.drop_column('user_subscriptions', 'provider_variant_id')
    op.drop_column('user_subscriptions', 'provider_order_id')
```

---

### 5.4 Migration 4: Create Webhook Events Table

**File:** `alembic/versions/AAAAAA_create_webhook_events_table.py`

```python
"""create_webhook_events_table

Revision ID: AAAAAA
Revises: ZZZZZZ
Create Date: 2025-10-17
"""

def upgrade() -> None:
    op.create_table(
        'webhook_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('provider_event_id', sa.String(255), nullable=False),
        sa.Column('event_name', sa.String(100), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('headers', sa.JSON(), nullable=True),
        sa.Column('processed_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('subscription_id', sa.UUID(), nullable=True),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('received_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('now()')),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['subscription_id'], ['user_subscriptions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('provider_event_id')
    )

    # Create indexes
    op.create_index('ix_webhook_events_provider_event_id', 'webhook_events', ['provider_event_id'], unique=True)
    op.create_index('ix_webhook_events_event_name', 'webhook_events', ['event_name'])
    op.create_index('ix_webhook_events_status', 'webhook_events', ['status'])
    op.create_index('ix_webhook_events_received_at', 'webhook_events', ['received_at'])
    op.create_index('ix_webhook_events_user_id', 'webhook_events', ['user_id'])

def downgrade() -> None:
    op.drop_index('ix_webhook_events_user_id')
    op.drop_index('ix_webhook_events_received_at')
    op.drop_index('ix_webhook_events_status')
    op.drop_index('ix_webhook_events_event_name')
    op.drop_index('ix_webhook_events_provider_event_id')
    op.drop_table('webhook_events')
```

---

### 5.5 Migration 5: Create Licenses Table

**File:** `alembic/versions/BBBBBB_create_licenses_table.py`

```python
"""create_licenses_table

Revision ID: BBBBBB
Revises: AAAAAA
Create Date: 2025-10-17
"""

def upgrade() -> None:
    op.create_table(
        'licenses',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('provider_license_id', sa.String(255), nullable=False),
        sa.Column('provider_license_key', sa.String(500), nullable=False),
        sa.Column('provider_order_id', sa.String(255), nullable=False),
        sa.Column('provider_product_id', sa.String(255), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='active'),
        sa.Column('activation_limit', sa.Integer(), nullable=True),
        sa.Column('activation_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('activations', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('expires_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('disabled_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('license_metadata', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('provider_license_id'),
        sa.UniqueConstraint('provider_license_key')
    )

    # Create indexes
    op.create_index('ix_licenses_provider_license_key', 'licenses', ['provider_license_key'], unique=True)
    op.create_index('ix_licenses_user_id', 'licenses', ['user_id'])
    op.create_index('ix_licenses_status', 'licenses', ['status'])
    op.create_index('ix_licenses_expires_at', 'licenses', ['expires_at'])

def downgrade() -> None:
    op.drop_index('ix_licenses_expires_at')
    op.drop_index('ix_licenses_status')
    op.drop_index('ix_licenses_user_id')
    op.drop_index('ix_licenses_provider_license_key')
    op.drop_table('licenses')
```

---

## 6. Schema Validation Checklist

Before Phase 1 implementation, verify:

- [ ] **Migration 1** runs successfully (subscription_plans fields)
- [ ] **Migration 2** runs successfully (enum updates)
- [ ] **Migration 3** runs successfully (user_subscriptions fields)
- [ ] **Migration 4** runs successfully (webhook_events table)
- [ ] **Migration 5** runs successfully (licenses table)
- [ ] All indexes created correctly
- [ ] Foreign key constraints working
- [ ] Rollback tested for each migration
- [ ] No performance degradation on existing queries
- [ ] Existing data preserved after migrations

---

## 7. Model Updates Required

### 7.1 Update Existing Models

**Files to modify:**

1. **`src/api/models/subscription_models/subscriptions.py`**
   ```python
   # Add new fields to UserSubscription class
   provider_order_id = Column(String(255))
   provider_variant_id = Column(String(255))
   cancel_at_period_end = Column(Boolean, default=False)
   renews_at = Column(TIMESTAMP, nullable=True)
   paused_at = Column(TIMESTAMP, nullable=True)
   card_brand = Column(String(50), nullable=True)
   card_last_four = Column(String(4), nullable=True)
   urls = Column(JSONB, default=dict)

   # Update SubscriptionStatus enum
   class SubscriptionStatus(str, enum.Enum):
       ACTIVE = "active"
       TRIAL = "trial"
       PAUSED = "paused"  # NEW
       PAST_DUE = "past_due"  # NEW
       CANCELLED = "cancelled"
       EXPIRED = "expired"
       SUSPENDED = "suspended"
   ```

2. **`src/api/models/subscription_models/plans.py`**
   ```python
   # Add new fields to SubscriptionPlan class
   lemonsqueezy_product_id = Column(String(255))
   lemonsqueezy_variant_id_monthly = Column(String(255))
   lemonsqueezy_variant_id_yearly = Column(String(255))
   lemonsqueezy_store_id = Column(String(255))
   ```

### 7.2 Create New Models

**Files to create:**

1. **`src/api/models/subscription_models/webhook_events.py`**
   - Full WebhookEvent model (see Section 3.1)

2. **`src/api/models/subscription_models/licenses.py`**
   - Full License model (see Section 3.2)

3. **Update `src/api/models/subscription_models/__init__.py`**
   ```python
   from .subscriptions import UserSubscription, SubscriptionStatus, BillingPeriod
   from .plans import SubscriptionPlan
   from .payment_methods import PaymentMethod
   from .webhook_events import WebhookEvent  # NEW
   from .licenses import License  # NEW

   __all__ = [
       "UserSubscription",
       "SubscriptionStatus",
       "BillingPeriod",
       "SubscriptionPlan",
       "PaymentMethod",
       "WebhookEvent",  # NEW
       "License",  # NEW
   ]
   ```

---

## 8. Testing Strategy

### 8.1 Migration Testing

```bash
# 1. Backup database
pg_dump wrext > backup_before_migrations.sql

# 2. Run migrations
cd wrext-backend
source .venv/bin/activate
alembic upgrade head

# 3. Verify schema
psql -d wrext -c "\d subscription_plans"
psql -d wrext -c "\d user_subscriptions"
psql -d wrext -c "\d webhook_events"
psql -d wrext -c "\d licenses"

# 4. Test rollback
alembic downgrade -5  # Rollback all 5 migrations
alembic upgrade head  # Re-run migrations

# 5. Verify data integrity
psql -d wrext -c "SELECT COUNT(*) FROM user_subscriptions;"
psql -d wrext -c "SELECT COUNT(*) FROM subscription_plans;"
```

### 8.2 Model Testing

**Unit tests to create:**

```python
# tests/unit/models/test_subscription_models.py
def test_user_subscription_new_fields():
    """Test new LemonSqueezy fields on UserSubscription"""
    subscription = UserSubscription(
        user_id=uuid.uuid4(),
        plan_id=uuid.uuid4(),
        provider_order_id="order_123",
        provider_variant_id="variant_456",
        cancel_at_period_end=True,
        card_brand="visa",
        card_last_four="4242"
    )
    assert subscription.provider_order_id == "order_123"
    assert subscription.cancel_at_period_end is True

def test_subscription_status_enum_new_values():
    """Test new enum values"""
    assert SubscriptionStatus.PAUSED == "paused"
    assert SubscriptionStatus.PAST_DUE == "past_due"

def test_webhook_event_creation():
    """Test WebhookEvent model"""
    event = WebhookEvent(
        provider_event_id="evt_123",
        event_name="subscription_created",
        payload={"test": "data"},
        status="pending"
    )
    assert event.status == "pending"

def test_license_creation():
    """Test License model"""
    license = License(
        user_id=uuid.uuid4(),
        provider_license_id="lic_123",
        provider_license_key="WREXT-XXXX-XXXX-XXXX",
        provider_order_id="order_456",
        provider_product_id="prod_789",
        activation_limit=5
    )
    assert license.activation_count == 0
```

---

## 9. Performance Considerations

### 9.1 Index Strategy

**Query patterns to optimize:**

1. **Webhook idempotency check** (high frequency)
   ```sql
   SELECT * FROM webhook_events WHERE provider_event_id = 'evt_123';
   ```
   Index: ✅ `ix_webhook_events_provider_event_id` (unique)

2. **User subscription lookup** (very high frequency)
   ```sql
   SELECT * FROM user_subscriptions WHERE user_id = '...' AND status = 'active';
   ```
   Existing index: ✅ Already indexed on user_id

3. **License validation** (medium frequency)
   ```sql
   SELECT * FROM licenses WHERE provider_license_key = 'WREXT-...' AND status = 'active';
   ```
   Index: ✅ `ix_licenses_provider_license_key` (unique)

4. **Failed webhook monitoring** (low frequency, background job)
   ```sql
   SELECT * FROM webhook_events WHERE status = 'failed' AND retry_count < 5;
   ```
   Index: ⚠️ Consider composite index on (status, retry_count)

### 9.2 Table Size Estimates

**Projected growth over 1 year:**

| Table | Rows per Month | 1 Year Total | Storage Estimate |
|-------|----------------|--------------|------------------|
| webhook_events | 10,000 | 120,000 | ~50 MB |
| licenses | 100 | 1,200 | ~1 MB |
| user_subscriptions | 500 | 6,000 | ~2 MB |

**Cleanup strategy:**
- Archive `webhook_events` older than 90 days
- Keep failed webhooks for 1 year (debugging)
- Never delete licenses (legal requirement)

---

## 10. Security Considerations

### 10.1 Sensitive Data

**Fields containing sensitive data:**

| Field | Table | Sensitivity | Protection |
|-------|-------|-------------|------------|
| `provider_customer_id` | users | Medium | Don't log, exclude from API |
| `provider_license_key` | licenses | High | Encrypt at rest, rate-limit validation |
| `payload` | webhook_events | Medium | May contain PII, encrypt if needed |
| `card_last_four` | user_subscriptions | Low | Safe to display |

### 10.2 Access Control

**Database permissions:**
```sql
-- Application user (read/write most tables)
GRANT SELECT, INSERT, UPDATE ON user_subscriptions TO wrext_app;
GRANT SELECT, INSERT, UPDATE ON webhook_events TO wrext_app;
GRANT SELECT, INSERT, UPDATE ON licenses TO wrext_app;

-- Read-only analytics user
GRANT SELECT ON user_subscriptions TO wrext_analytics;
GRANT SELECT ON webhook_events TO wrext_analytics;

-- Never grant DELETE on licenses (legal compliance)
REVOKE DELETE ON licenses FROM wrext_app;
```

---

## 11. Comparison with Task 0.1.1 Findings

### 11.1 Cross-Validation

From **Task 0.1.1** (Mock Provider Audit), we identified:

| Requirement from 0.1.1 | Schema Support | Status |
|------------------------|----------------|--------|
| Customer ID storage | `users.provider_customer_id` | ✅ Ready |
| Subscription ID storage | `user_subscriptions.provider_subscription_id` | ✅ Ready |
| Variant/Price ID storage | `user_subscriptions.provider_variant_id` | ✅ Adding |
| Order ID storage | `user_subscriptions.provider_order_id` | ✅ Adding |
| Webhook event tracking | `webhook_events` table | ✅ Creating |
| License management | `licenses` table | ✅ Creating |
| Cancellation behavior | `cancel_at_period_end` field | ✅ Adding |
| Trial tracking | `trial_end_date` field | ✅ Already exists |
| Payment method display | `card_brand`, `card_last_four` | ✅ Adding |

### 11.2 Missing Items from 0.1.1

From the mock provider audit, these were identified as needed:

✅ **Invoices** - Will be fetched from LemonSqueezy API (no table needed)
✅ **Refunds** - Tracked in webhook_events, no separate table needed
✅ **Pause/Resume** - Supported via status enum (`paused`, `past_due`)

**All requirements from Task 0.1.1 are covered by this schema design.**

---

## 12. Recommendations

### 12.1 High Priority (Must Do)

1. ✅ **Create all 5 migrations** in specified order
2. ✅ **Test migrations** on development database
3. ✅ **Update model files** with new fields
4. ✅ **Create new model files** (WebhookEvent, License)
5. ✅ **Verify indexes** are created correctly
6. ✅ **Test rollback** for each migration

### 12.2 Medium Priority (Should Do)

1. ⚠️ **Add composite indexes** for common query patterns
2. ⚠️ **Set up archival strategy** for webhook_events
3. ⚠️ **Implement cleanup job** for old webhook events
4. ⚠️ **Add database constraints** for data validation
5. ⚠️ **Create monitoring queries** for webhook health

### 12.3 Low Priority (Nice to Have)

1. 💡 **Partitioning** for webhook_events table (if high volume)
2. 💡 **Materialized views** for subscription analytics
3. 💡 **Database triggers** for automatic audit logging
4. 💡 **Check constraints** for enum validation

### 12.4 Technical Debt to Address

1. **Enum immutability** - Consider migrating from enum to string column for flexibility
2. **Metadata columns** - Standardize JSONB schema for better querying
3. **Timezone handling** - Ensure all TIMESTAMP columns use UTC consistently
4. **Soft deletes** - Consider adding `deleted_at` to subscriptions for audit trail

---

## 13. Next Steps for Phase 1

After this audit is approved:

1. **✅ Create migration files** (Task 1.1.1-1.1.5)
2. **✅ Update model classes** with new fields
3. **✅ Create new model files** (WebhookEvent, License)
4. **✅ Run migrations** on development database
5. **✅ Write model tests** to verify schema
6. **▶️ Proceed to Task 1.2.1** (Install LemonSqueezy SDK)

---

## 14. Estimated Effort

| Task | Estimated Time | Complexity |
|------|----------------|------------|
| Create Migration 1 (plans) | 30 min | Low |
| Create Migration 2 (enum) | 30 min | Medium |
| Create Migration 3 (subscriptions) | 1 hour | Medium |
| Create Migration 4 (webhook_events) | 1 hour | Medium |
| Create Migration 5 (licenses) | 1 hour | Medium |
| Update model files | 1 hour | Low |
| Create new model files | 2 hours | Medium |
| Write model tests | 2 hours | Medium |
| Test migrations + rollback | 1 hour | Low |
| **Total** | **10 hours** | **~1.5 days** |

---

## 15. Conclusion

### 15.1 Summary

The existing database schema is well-architected with provider abstraction already in place. The required changes are:

**Existing Tables:**
- `users` - ✅ Ready (no changes needed)
- `subscription_plans` - ⚠️ Add 4 LemonSqueezy-specific fields
- `user_subscriptions` - ⚠️ Add 8 new fields, update enum
- `payment_methods` - ✅ Ready (no changes needed)

**New Tables:**
- `webhook_events` - Must create (critical for idempotency)
- `licenses` - Must create (for one-time purchases)

### 15.2 Critical Success Factors

1. ✅ **Migrations must be reversible** - Proper downgrade() functions
2. ✅ **No data loss** - All new fields nullable or have defaults
3. ✅ **Proper indexing** - Performance optimized for common queries
4. ✅ **Idempotency** - webhook_events table ensures no duplicate processing
5. ✅ **Extensibility** - JSONB columns allow future flexibility

### 15.3 Risk Assessment

**Low Risk:**
- All changes are additive (no data deletion)
- Existing code continues working (backward compatible)
- Mock provider unaffected by schema changes

**Medium Risk:**
- Enum updates in PostgreSQL (can't easily rollback)
- Large webhook_events table if not archived regularly

**High Risk:**
- None identified

### 15.4 Ready for Implementation

All requirements documented. Schema design validated against:
- ✅ Task 0.1.1 findings (mock provider requirements)
- ✅ LemonSqueezy API capabilities
- ✅ Subscription lifecycle requirements
- ✅ Webhook processing requirements
- ✅ License management requirements

**Status: READY FOR PHASE 1 IMPLEMENTATION** 🚀

---

**Audit Completed By:** Claude (AI Assistant)
**Review Status:** Pending human review
**Confidence Level:** High (based on code analysis and LemonSqueezy docs)

**Files to Review:**
- [ ] `src/api/models/subscription_models/subscriptions.py`
- [ ] `src/api/models/subscription_models/plans.py`
- [ ] `src/api/models/subscription_models/payment_methods.py`
- [ ] `src/api/models/user_models/users.py`
- [ ] Migration specifications in this document
