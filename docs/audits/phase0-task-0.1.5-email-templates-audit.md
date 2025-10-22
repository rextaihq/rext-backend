# Phase 0 - Task 0.1.5: Email Templates Audit

**Date:** 2025-10-17
**Task:** Review email templates
**Status:** ✅ Complete
**Author:** Claude Code

---

## Executive Summary

This audit analyzes all billing-related email templates in the WREXT backend to understand their structure, data requirements, and enhancement needs for LemonSqueezy integration.

### Key Findings

1. **Excellent Template System**: 11 billing email templates with clean, reusable component-based architecture
2. **Professional Design**: All templates use modern HTML email best practices with responsive design
3. **Already LemonSqueezy-Ready**: Most templates use provider-agnostic data fields
4. **Minor Enhancements Needed**: 3 templates need LemonSqueezy-specific data additions
5. **No New Templates Required**: All necessary email types already exist
6. **Missing Templates Identified**: 3 LemonSqueezy-specific templates to add for advanced features

---

## Template Inventory

### Billing Email Templates (11 existing)

| # | Template Name | File | Lines | Status |
|---|--------------|------|-------|--------|
| 1 | Subscription Created | `subscription_created.py` | 109 | ✅ Ready |
| 2 | Payment Succeeded | `payment_succeeded.py` | 125 | ⚠️ Needs enhancement |
| 3 | Payment Failed | `payment_failed.py` | 106 | ⚠️ Needs enhancement |
| 4 | Subscription Cancelled | `subscription_cancelled.py` | 102 | ✅ Ready |
| 5 | Trial Ending | `trial_ending.py` | 98 | ✅ Ready |
| 6 | Subscription Renewed | `subscription_renewed.py` | 102 | ⚠️ Needs enhancement |
| 7 | Subscription Expiring Soon | `subscription_expiring_soon.py` | 101 | ✅ Ready |
| 8 | Upgrade Successful | `upgrade_successful.py` | 104 | ✅ Ready |
| 9 | Downgrade Scheduled | `downgrade_scheduled.py` | 104 | ✅ Ready |
| 10 | Usage Limit Warning | `usage_limit_warning.py` | 107 | ✅ Ready |
| 11 | Usage Limit Exceeded | `usage_limit_exceeded.py` | 122 | ✅ Ready |

**Total:** 11 templates | 1,180 lines of email template code

---

## Detailed Template Analysis

### 1. Subscription Created (✅ Ready)

**File:** [emails/templates/billing/subscription_created.py](wrext-backend/emails/templates/billing/subscription_created.py:1-109)
**Purpose:** Sent when user successfully subscribes to a paid plan
**Trigger:** After checkout completion (webhook: `subscription_created`)

#### Current Parameters
```python
def render_subscription_created_email(
    user_name: str,
    plan_name: str,
    plan_price: str,
    billing_period: str,
    features: List[str],
    dashboard_url: str = "https://app.wrext.com/settings/billing",
    frontend_url: str = "https://app.wrext.com"
) -> str
```

#### Email Content
- **Header:** "Welcome to {plan_name}! 🎉"
- **Greeting:** Personalized with user_name
- **Subscription Details Box:** Plan name, price, billing period (gradient purple background)
- **Features List:** Top 5 features with checkmarks (green accent)
- **CTA Button:** "Go to Dashboard"
- **Footer Note:** Instructions for managing subscription

#### LemonSqueezy Changes Needed
✅ **None** - Template is provider-agnostic and ready to use

**Rationale:**
- All data fields are generic (plan_name, plan_price, billing_period)
- No provider-specific references
- Features list comes from plan configuration, not provider

---

### 2. Payment Succeeded (⚠️ Needs Enhancement)

**File:** [emails/templates/billing/payment_succeeded.py](wrext-backend/emails/templates/billing/payment_succeeded.py:1-125)
**Purpose:** Receipt email sent after successful payment
**Trigger:** After payment processing (webhook: `subscription_payment_success`)

#### Current Parameters
```python
def render_payment_succeeded_email(
    user_name: str,
    plan_name: str,
    amount: str,
    payment_date: str,
    next_billing_date: str,
    invoice_url: str = None,  # ✅ Already supports invoice URL!
    dashboard_url: str = "https://app.wrext.com/settings/billing",
    frontend_url: str = "https://app.wrext.com"
) -> str
```

#### Email Content
- **Header:** "Payment Received ✓"
- **Greeting:** Personalized with user_name
- **Receipt Box:** Payment date, plan, amount paid (green highlight), next billing date
- **Invoice Button:** Conditional "Download Invoice" button if invoice_url provided
- **CTA Button:** "View Billing Dashboard"
- **Footer Note:** Support contact information

#### LemonSqueezy Enhancements Needed
⚠️ **Add card information display**

**Current State:**
- ✅ Already supports `invoice_url` parameter
- ❌ Missing card brand and last 4 digits display

**Enhancement:**
```python
def render_payment_succeeded_email(
    user_name: str,
    plan_name: str,
    amount: str,
    payment_date: str,
    next_billing_date: str,
    invoice_url: str = None,
    card_brand: str = None,        # NEW: "Visa", "Mastercard", etc.
    card_last_four: str = None,    # NEW: "4242"
    dashboard_url: str = "https://app.wrext.com/settings/billing",
    frontend_url: str = "https://app.wrext.com"
) -> str
```

**Add to receipt box (after "Amount Paid" row):**
```html
<tr>
    <td colspan="2" style="height: 1px; background-color: #e5e7eb;"></td>
</tr>
<tr>
    <td style="color: #6b7280; font-size: 14px; padding: 8px 0;">
        Payment Method
    </td>
    <td style="color: #111827; font-size: 14px; padding: 8px 0; text-align: right; font-weight: 600;">
        {card_brand} •••• {card_last_four}
    </td>
</tr>
```

**Estimated Effort:** 30 minutes

---

### 3. Payment Failed (⚠️ Needs Enhancement)

**File:** [emails/templates/billing/payment_failed.py](wrext-backend/emails/templates/billing/payment_failed.py:1-106)
**Purpose:** Alert user when payment processing fails
**Trigger:** After payment failure (webhook: `subscription_payment_failed`)

#### Current Parameters
```python
def render_payment_failed_email(
    user_name: str,
    plan_name: str,
    amount: str,
    retry_date: str,
    update_payment_url: str = "https://app.wrext.com/settings/billing",
    frontend_url: str = "https://app.wrext.com"
) -> str
```

#### Email Content
- **Header:** "Payment Failed ⚠️" (red color)
- **Greeting:** Personalized with user_name
- **Alert Box:** Explanation of what happens next, retry date (red/yellow background)
- **Failure Details Box:** Plan, amount due (red), retry date
- **CTA Button:** "Update Payment Method"
- **Troubleshooting Tips:** Common solutions (bullet list)
- **Footer Note:** Support contact

#### LemonSqueezy Enhancements Needed
⚠️ **Add customer portal URL option**

**Current State:**
- Uses `update_payment_url` which points to internal billing dashboard
- LemonSqueezy provides direct "update payment method" URLs via customer portal

**Enhancement:**
```python
def render_payment_failed_email(
    user_name: str,
    plan_name: str,
    amount: str,
    retry_date: str,
    update_payment_url: str = "https://app.wrext.com/settings/billing",
    customer_portal_url: str = None,  # NEW: LemonSqueezy customer portal URL
    frontend_url: str = "https://app.wrext.com"
) -> str
```

**Logic:**
```python
# Use customer portal URL if provided, otherwise use dashboard URL
payment_update_url = customer_portal_url or update_payment_url
primary_button("Update Payment Method", payment_update_url)
```

**Rationale:**
- LemonSqueezy customer portal provides direct payment method update
- Reduces friction for users (one-click instead of navigating through dashboard)
- Falls back to dashboard URL if portal URL not available

**Estimated Effort:** 15 minutes

---

### 4. Subscription Cancelled (✅ Ready)

**File:** [emails/templates/billing/subscription_cancelled.py](wrext-backend/emails/templates/billing/subscription_cancelled.py:1-102)
**Purpose:** Confirmation email when user cancels subscription
**Trigger:** After cancellation (webhook: `subscription_cancelled`)

#### Current Parameters
```python
def render_subscription_cancelled_email(
    user_name: str,
    plan_name: str,
    end_date: str,
    reactivate_url: str = "https://app.wrext.com/pricing",
    feedback_url: str = "https://app.wrext.com/feedback",
    frontend_url: str = "https://app.wrext.com"
) -> str
```

#### Email Content
- **Header:** "Subscription Cancelled"
- **Greeting:** Personalized with user_name
- **Timeline Box:** Explanation of access until end_date (yellow background)
- **Downgrade Info:** What they'll have on free plan (gray box)
- **Encouragement:** Option to reactivate before end_date
- **CTA Buttons:** "Reactivate Subscription" (primary), "Share Feedback" (secondary)
- **Footer Note:** Thank you message

#### LemonSqueezy Changes Needed
✅ **None** - Template is provider-agnostic and ready to use

**Rationale:**
- Generic cancellation flow
- No provider-specific data required
- end_date comes from subscription record, not provider

---

### 5. Trial Ending (✅ Ready)

**File:** [emails/templates/billing/trial_ending.py](wrext-backend/emails/templates/billing/trial_ending.py:1-98)
**Purpose:** Reminder sent 3 days before trial expires
**Trigger:** Scheduled job checking trial_end_date

#### Current Parameters
```python
def render_trial_ending_email(
    user_name: str,
    plan_name: str,
    trial_end_date: str,
    days_remaining: int,
    upgrade_url: str = "https://app.wrext.com/pricing",
    frontend_url: str = "https://app.wrext.com"
) -> str
```

#### Email Content
- **Header:** "Your Trial is Ending Soon ⏰"
- **Greeting:** Personalized with user_name
- **Alert Box:** Days remaining, trial end date (gradient purple background)
- **Benefits Box:** What they'll keep if they continue (gray background)
- **Warning Box:** What happens after trial ends (red background)
- **CTA Button:** "Continue with Premium"
- **Footer Note:** Support contact

#### LemonSqueezy Changes Needed
✅ **None** - Template is provider-agnostic and ready to use

**Rationale:**
- Trial logic handled by subscription service
- No provider-specific references
- Upgrade URL points to pricing page (checkout created separately)

---

### 6. Subscription Renewed (⚠️ Needs Enhancement)

**File:** [emails/templates/billing/subscription_renewed.py](wrext-backend/emails/templates/billing/subscription_renewed.py:1-102)
**Purpose:** Confirmation email when subscription successfully renews
**Trigger:** After successful renewal (webhook: `subscription_payment_success` for renewal)

#### Current Parameters
```python
def render_subscription_renewed_email(
    user_name: str,
    plan_name: str,
    amount: str,
    renewal_date: str,
    next_billing_date: str,
    dashboard_url: str = "https://app.wrext.com/settings/billing",
    frontend_url: str = "https://app.wrext.com"
) -> str
```

#### Email Content
- **Header:** "Subscription Renewed 🎉"
- **Greeting:** Personalized with user_name
- **Renewal Details Box:** Renewal date, amount charged, next billing date (green gradient)
- **Confirmation Box:** Features are active (green background)
- **CTA Button:** "View Billing Details"
- **Footer Note:** Thank you message

#### LemonSqueezy Enhancements Needed
⚠️ **Add invoice URL parameter**

**Current State:**
- No invoice link provided
- Users must navigate to dashboard to download invoice

**Enhancement:**
```python
def render_subscription_renewed_email(
    user_name: str,
    plan_name: str,
    amount: str,
    renewal_date: str,
    next_billing_date: str,
    invoice_url: str = None,       # NEW: Invoice download URL
    dashboard_url: str = "https://app.wrext.com/settings/billing",
    frontend_url: str = "https://app.wrext.com"
) -> str
```

**Add after confirmation box:**
```python
invoice_button = ""
if invoice_url:
    invoice_button = f"""
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="margin: 16px 0;">
        <tr>
            <td align="center">
                <a href="{invoice_url}" style="display: inline-block; padding: 12px 24px; background-color: #ffffff; color: #10b981; text-decoration: none; border-radius: 6px; font-weight: 600; border: 2px solid #10b981;">
                    Download Invoice
                </a>
            </td>
        </tr>
    </table>
    """
```

**Estimated Effort:** 20 minutes

---

### 7. Subscription Expiring Soon (✅ Ready)

**File:** [emails/templates/billing/subscription_expiring_soon.py](wrext-backend/emails/templates/billing/subscription_expiring_soon.py:1-101)
**Purpose:** Reminder when subscription is about to expire (7 days before)
**Trigger:** Scheduled job checking end_date

#### Current Parameters
```python
def render_subscription_expiring_soon_email(
    user_name: str,
    plan_name: str,
    expiry_date: str,
    days_remaining: int,
    renew_url: str = "https://app.wrext.com/billing",
    pricing_url: str = "https://app.wrext.com/pricing",
    frontend_url: str = "https://app.wrext.com"
) -> str
```

#### Email Content
- **Header:** "Your Subscription Expires Soon"
- **Greeting:** Personalized with user_name
- **Expiration Alert Box:** Days remaining, expiry date (red background)
- **Features Box:** What they'll lose access to (gray background)
- **Encouragement:** Renew to keep features
- **CTA Buttons:** "Renew Subscription" (primary), "View Pricing" (secondary)
- **Footer Note:** Support contact

#### LemonSqueezy Changes Needed
✅ **None** - Template is provider-agnostic and ready to use

**Rationale:**
- Generic expiration reminder
- No provider-specific data needed
- Applies to cancelled or expiring subscriptions

---

### 8. Upgrade Successful (✅ Ready)

**File:** [emails/templates/billing/upgrade_successful.py](wrext-backend/emails/templates/billing/upgrade_successful.py:1-104)
**Purpose:** Confirmation email when user upgrades to higher-tier plan
**Trigger:** After successful upgrade (API route: `POST /subscriptions/upgrade`)

#### Current Parameters
```python
def render_upgrade_successful_email(
    user_name: str,
    old_plan_name: str,
    new_plan_name: str,
    new_features: list[str],
    effective_date: str,
    manage_url: str = "https://app.wrext.com/billing",
    docs_url: str = "https://docs.wrext.com",
    frontend_url: str = "https://app.wrext.com"
) -> str
```

#### Email Content
- **Header:** "🎉 Upgrade Successful!"
- **Greeting:** Personalized with user_name
- **Upgrade Confirmation Box:** Old plan → new plan, effective date (green background)
- **New Features Box:** List of new features with checkmarks (gray background)
- **Encouragement:** Check documentation for new features
- **CTA Buttons:** "Explore New Features" (primary), "Manage Subscription" (secondary)
- **Footer Note:** Thank you message

#### LemonSqueezy Changes Needed
✅ **None** - Template is provider-agnostic and ready to use

**Rationale:**
- Upgrade flow handled by subscription service
- new_features comes from plan configuration
- No provider-specific data required

---

### 9. Downgrade Scheduled (✅ Ready)

**File:** [emails/templates/billing/downgrade_scheduled.py](wrext-backend/emails/templates/billing/downgrade_scheduled.py:1-104)
**Purpose:** Confirmation when user downgrades (takes effect at end of period)
**Trigger:** After downgrade request (API route: `POST /subscriptions/upgrade` with lower-tier plan)

#### Current Parameters
```python
def render_downgrade_scheduled_email(
    user_name: str,
    current_plan_name: str,
    new_plan_name: str,
    effective_date: str,
    features_losing: list[str],
    cancel_downgrade_url: str = "https://app.wrext.com/billing",
    pricing_url: str = "https://app.wrext.com/pricing",
    frontend_url: str = "https://app.wrext.com"
) -> str
```

#### Email Content
- **Header:** "Downgrade Scheduled"
- **Greeting:** Personalized with user_name
- **Timeline Box:** Current plan until effective_date, then new plan (yellow background)
- **Features Losing Box:** List of features with X marks (red background)
- **Option to Cancel:** Can undo downgrade before effective_date
- **CTA Buttons:** "Cancel Downgrade" (primary), "View All Plans" (secondary)
- **Footer Note:** Support contact

#### LemonSqueezy Changes Needed
✅ **None** - Template is provider-agnostic and ready to use

**Rationale:**
- Downgrade handled by subscription service
- features_losing comes from plan comparison
- No provider-specific data required

---

### 10. Usage Limit Warning (✅ Ready)

**File:** [emails/templates/billing/usage_limit_warning.py](wrext-backend/emails/templates/billing/usage_limit_warning.py:1-107)
**Purpose:** Alert when approaching plan usage limits (80% threshold)
**Trigger:** Usage tracking service detects 80%+ usage

#### Current Parameters
```python
def render_usage_limit_warning_email(
    user_name: str,
    resource_type: str,
    current_usage: int,
    usage_limit: int,
    percentage_used: int,
    plan_name: str,
    upgrade_url: str = "https://app.wrext.com/pricing",
    usage_url: str = "https://app.wrext.com/usage",
    frontend_url: str = "https://app.wrext.com"
) -> str
```

#### Email Content
- **Header:** "⚠️ Usage Limit Warning"
- **Greeting:** Personalized with user_name
- **Usage Alert Box:** Current usage / limit (percentage), progress bar (yellow/orange)
- **Explanation:** What happens when limit reached
- **Upgrade Benefits Box:** Higher limits, advanced features, priority support
- **CTA Buttons:** "Upgrade Now" (primary), "View Detailed Usage" (secondary)
- **Footer Note:** Support contact

#### LemonSqueezy Changes Needed
✅ **None** - Template is provider-agnostic and ready to use

**Rationale:**
- Usage tracking independent of payment provider
- No provider-specific data required
- Generic resource limits (workspaces, topics, API calls)

---

### 11. Usage Limit Exceeded (✅ Ready)

**File:** [emails/templates/billing/usage_limit_exceeded.py](wrext-backend/emails/templates/billing/usage_limit_exceeded.py:1-122)
**Purpose:** Alert when user exceeds plan usage limits
**Trigger:** Usage tracking service detects 100%+ usage

#### Current Parameters
```python
def render_usage_limit_exceeded_email(
    user_name: str,
    resource_type: str,
    current_usage: int,
    usage_limit: int,
    plan_name: str,
    restrictions: list[str],
    upgrade_url: str = "https://app.wrext.com/pricing",
    usage_url: str = "https://app.wrext.com/usage",
    frontend_url: str = "https://app.wrext.com"
) -> str
```

#### Email Content
- **Header:** "🚨 Usage Limit Exceeded"
- **Greeting:** Personalized with user_name
- **Limit Exceeded Box:** Current usage > limit, full progress bar (red)
- **Restrictions Box:** List of currently restricted features
- **Explanation:** Upgrade to restore access
- **Upgrade Benefits Box:** Immediate restoration, higher limits
- **CTA Buttons:** "Upgrade Now" (primary), "View Detailed Usage" (secondary)
- **Footer Note:** Support contact

#### LemonSqueezy Changes Needed
✅ **None** - Template is provider-agnostic and ready to use

**Rationale:**
- Usage enforcement independent of payment provider
- restrictions comes from plan limits enforcement
- No provider-specific data required

---

## Template Architecture Analysis

### Component System

All templates use a reusable component-based architecture:

**Base Components:**
- `simple_header()` - WREXT logo and branding
- `simple_footer()` - Unsubscribe link, copyright, social links
- `primary_button(text, url)` - Main CTA button (purple background)
- `secondary_button(text, url)` - Alternative action (outlined button)
- `compose_email([components])` - Assembles full HTML email with wrapper

**File Locations:**
- [emails/components/header.py](wrext-backend/emails/components/header.py)
- [emails/components/footer.py](wrext-backend/emails/components/footer.py)
- [emails/components/button.py](wrext-backend/emails/components/button.py)
- [emails/components/base.py](wrext-backend/emails/components/base.py)
- [emails/utils/renderer.py](wrext-backend/emails/utils/renderer.py)

**Benefits:**
- ✅ Consistent branding across all emails
- ✅ Easy to update styles globally
- ✅ Reduces code duplication
- ✅ Professional HTML email structure

---

## Email Service Integration

### Email Service Layer

**File:** [src/services/email_service.py](wrext-backend/src/services/email_service.py:1-150)

The email service provides:
- **Provider Abstraction:** Uses Resend via factory pattern
- **Database Logging:** All emails logged to `email_log` table
- **Retry Logic:** Automatic retry with exponential backoff (tenacity)
- **Fallback Provider:** Secondary email provider for failures
- **Error Handling:** Comprehensive error tracking with Sentry integration

**Key Method:**
```python
async def send_email(
    self,
    to: str,
    subject: str,
    html: str,
    from_email: Optional[str] = None,
    from_name: Optional[str] = None,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
    reply_to: Optional[str] = None,
    workspace_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
    template_type: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    retry_on_failure: bool = True,
    auto_commit: bool = True
) -> EmailLog
```

---

## Email Trigger Mapping

### LemonSqueezy Webhook → Email Template Mapping

| Webhook Event | Template(s) to Send | Priority |
|--------------|-------------------|----------|
| `subscription_created` | 1. Subscription Created | High |
| `subscription_payment_success` (first payment) | 2. Payment Succeeded | High |
| `subscription_payment_success` (renewal) | 2. Payment Succeeded<br>6. Subscription Renewed | High |
| `subscription_payment_failed` | 3. Payment Failed | High |
| `subscription_cancelled` | 4. Subscription Cancelled | High |
| `subscription_expired` | (No email - silent) | Low |
| `subscription_paused` | (Use Payment Failed template) | Medium |
| `subscription_unpaused` | (Use Subscription Renewed template) | Medium |
| `subscription_resumed` | (Use Subscription Created template) | Medium |
| `subscription_updated` (upgrade) | 8. Upgrade Successful | Medium |
| `subscription_updated` (downgrade) | 9. Downgrade Scheduled | Medium |

### Scheduled Job → Email Template Mapping

| Job Trigger | Template | Frequency |
|------------|----------|-----------|
| Trial ending in 3 days | 5. Trial Ending | Daily check |
| Subscription expiring in 7 days | 7. Subscription Expiring Soon | Daily check |
| Usage ≥ 80% of limit | 10. Usage Limit Warning | Real-time on limit check |
| Usage > 100% of limit | 11. Usage Limit Exceeded | Real-time on limit check |

---

## Enhancement Summary

### Templates Requiring Changes

| Template | Enhancement | Effort | Priority |
|----------|-------------|--------|----------|
| Payment Succeeded | Add card_brand, card_last_four | 30 min | Medium |
| Payment Failed | Add customer_portal_url option | 15 min | Low |
| Subscription Renewed | Add invoice_url parameter | 20 min | Medium |

**Total Enhancement Effort:** 1 hour 5 minutes

### Templates Ready As-Is

**8 templates** require no changes:
1. Subscription Created
2. Subscription Cancelled
3. Trial Ending
4. Subscription Expiring Soon
5. Upgrade Successful
6. Downgrade Scheduled
7. Usage Limit Warning
8. Usage Limit Exceeded

---

## Missing LemonSqueezy-Specific Templates

While the existing 11 templates cover core subscription flows, there are 3 LemonSqueezy-specific scenarios that could benefit from dedicated templates:

### 1. Subscription Paused Email (NEW)

**Purpose:** Sent when subscription is paused due to payment issues
**Trigger:** Webhook: `subscription_paused`

**Recommended Parameters:**
```python
def render_subscription_paused_email(
    user_name: str,
    plan_name: str,
    pause_reason: str,  # "payment_failed", "user_requested"
    paused_date: str,
    update_payment_url: str,
    customer_portal_url: str = None,
    frontend_url: str = "https://app.wrext.com"
) -> str
```

**Note:** Can reuse `payment_failed.py` template for now with minor wording changes

**Estimated Effort:** 1-2 hours (if creating new template)
**Priority:** Low (can reuse existing template)

---

### 2. Subscription Unpaused Email (NEW)

**Purpose:** Sent when paused subscription is resumed
**Trigger:** Webhook: `subscription_unpaused`

**Recommended Parameters:**
```python
def render_subscription_unpaused_email(
    user_name: str,
    plan_name: str,
    resumed_date: str,
    next_billing_date: str,
    dashboard_url: str = "https://app.wrext.com/settings/billing",
    frontend_url: str = "https://app.wrext.com"
) -> str
```

**Note:** Can reuse `subscription_renewed.py` template for now

**Estimated Effort:** 1-2 hours (if creating new template)
**Priority:** Low (can reuse existing template)

---

### 3. License Key Created Email (NEW)

**Purpose:** Sent when one-time purchase completes and license key is generated
**Trigger:** Webhook: `license_key_created`

**Recommended Parameters:**
```python
def render_license_key_created_email(
    user_name: str,
    product_name: str,
    license_key: str,
    activation_limit: int,
    expires_at: str = None,  # null for lifetime licenses
    download_url: str = None,  # If applicable
    docs_url: str = "https://docs.wrext.com",
    frontend_url: str = "https://app.wrext.com"
) -> str
```

**Email Content:**
- **Header:** "Your License Key 🎉"
- **Product Info:** Product name, purchase date
- **License Key Box:** Large, copyable license key (monospace font)
- **Activation Details:** Activation limit, expiration (if applicable)
- **Instructions:** How to activate license
- **CTA Buttons:** "View Documentation" (primary), "Download Software" (secondary)

**Estimated Effort:** 2-3 hours (new template creation)
**Priority:** Medium (only needed if selling one-time products/licenses)

---

## Email Template Enhancement Plan

### Phase 1: Minimal Enhancements (1-2 hours)

**Goal:** Get LemonSqueezy integration working with existing templates

**Tasks:**
1. ✅ Audit complete (this document)
2. Add `card_brand` and `card_last_four` to `payment_succeeded.py`
3. Add `customer_portal_url` to `payment_failed.py`
4. Add `invoice_url` to `subscription_renewed.py`
5. Update email service calls in webhook handlers to pass new parameters

**Testing:**
- Send test emails with LemonSqueezy data from sandbox
- Verify card info displays correctly
- Verify invoice URLs are clickable
- Verify customer portal URLs work

---

### Phase 2: New Templates (3-7 hours) - OPTIONAL

**Goal:** Create LemonSqueezy-specific templates for advanced features

**Priority Order:**
1. **License Key Created** (2-3 hours) - If selling one-time products
2. **Subscription Paused** (1-2 hours) - If using pause feature
3. **Subscription Unpaused** (1-2 hours) - If using pause feature

**Note:** Can defer to Phase 3 or later if not needed immediately

---

### Phase 3: Testing & Refinement (2-3 hours)

**Tasks:**
1. Create email preview routes for all billing templates
2. Test all templates with real LemonSqueezy data
3. Test responsive design on mobile devices
4. Test in multiple email clients (Gmail, Outlook, Apple Mail)
5. Verify all links work correctly
6. Check spam score with mail-tester.com

---

## Template Data Source Mapping

### Where Template Data Comes From

| Template Parameter | Data Source | LemonSqueezy Webhook Field |
|-------------------|-------------|---------------------------|
| `user_name` | Database: `users.display_name` or `users.email` | - |
| `plan_name` | Database: `subscription_plans.display_name` | `data.attributes.product_name` |
| `plan_price` | Database: `subscription_plans.price_monthly/yearly` | - |
| `amount` | Webhook: Payment amount | `data.attributes.total` |
| `payment_date` | Webhook: Payment date | `data.attributes.created_at` |
| `next_billing_date` | Webhook: Next billing date | `data.attributes.renews_at` |
| `invoice_url` | Webhook: Invoice URL | `data.attributes.urls.invoice` |
| `card_brand` | Webhook: Card brand | `data.attributes.card_brand` |
| `card_last_four` | Webhook: Card last 4 | `data.attributes.card_last_four` |
| `customer_portal_url` | Webhook: Customer portal | `data.attributes.urls.customer_portal` |
| `renewal_date` | Webhook: Renewal date | `data.attributes.renews_at` |
| `end_date` | Database: `user_subscriptions.end_date` | - |
| `trial_end_date` | Database: `user_subscriptions.trial_end_date` | `data.attributes.trial_ends_at` |
| `features` | Database: `subscription_plans.features` (JSON) | - |

**Key Insight:** Most template data is already stored in database. LemonSqueezy webhooks provide additional display data (card info, URLs) that enhance the user experience.

---

## Testing Strategy

### Unit Tests

**Test Each Template Rendering:**
```python
def test_subscription_created_email_renders():
    html = render_subscription_created_email(
        user_name="John Doe",
        plan_name="Pro Plan",
        plan_price="$29.99",
        billing_period="monthly",
        features=["Feature 1", "Feature 2"],
        dashboard_url="https://example.com/dashboard"
    )
    assert "Welcome to Pro Plan!" in html
    assert "John Doe" in html
    assert "$29.99" in html
    assert "Feature 1" in html
```

**Test Component Rendering:**
- Test `simple_header()` returns valid HTML
- Test `primary_button()` with URL escaping
- Test `secondary_button()` styling
- Test `compose_email()` wrapper structure

**Estimated Effort:** 2 hours

---

### Integration Tests

**Test Email Service Integration:**
```python
async def test_send_subscription_created_email():
    email_service = EmailService(db)

    html = render_subscription_created_email(...)

    result = await email_service.send_email(
        to="test@example.com",
        subject="Welcome to Pro Plan!",
        html=html,
        template_type="subscription_created",
        user_id=user.id
    )

    assert result.status == "sent"
    assert result.template_type == "subscription_created"
```

**Test Webhook → Email Flow:**
- Mock LemonSqueezy webhook event
- Verify correct template is selected
- Verify template data is populated from webhook
- Verify email is sent via email service
- Verify email is logged to database

**Estimated Effort:** 3 hours

---

### Manual Testing

**Visual Testing:**
1. Generate all 11 templates with sample data
2. View in browser (HTML preview)
3. Send test emails to multiple providers:
   - Gmail
   - Outlook.com
   - Apple Mail (macOS/iOS)
   - Yahoo Mail
4. Check mobile rendering (responsive design)
5. Verify all links are clickable
6. Check spam score (mail-tester.com)

**Estimated Effort:** 2-3 hours

---

## Email Analytics & Tracking

### Current Email Logging

**Table:** `email_log`
**Fields:**
- `id` - UUID primary key
- `to_email` - Recipient
- `subject` - Email subject
- `status` - sent, failed, pending
- `template_type` - Template identifier
- `user_id` - Associated user
- `workspace_id` - Associated workspace
- `provider_message_id` - Resend message ID
- `sent_at` - Timestamp
- `opened_at` - Email open timestamp (if tracked)
- `clicked_at` - Link click timestamp (if tracked)
- `error_message` - Error details if failed

**Analytics Available:**
- Email send success rate
- Template usage statistics
- Open rates (if tracking enabled)
- Click-through rates (if tracking enabled)
- Failure reasons

---

## Security & Best Practices

### Current Implementation

**✅ Security Features:**
1. **No Sensitive Data in Templates:** Never include passwords, API keys, or tokens
2. **URL Validation:** All URLs are validated before rendering
3. **HTML Escaping:** Template parameters are escaped to prevent XSS
4. **Rate Limiting:** Email service has built-in rate limiting
5. **Unsubscribe Links:** All emails include unsubscribe option
6. **SPF/DKIM/DMARC:** Resend provider handles email authentication

**✅ Best Practices:**
1. **Responsive Design:** All templates mobile-friendly
2. **Plain Text Fallback:** HTML emails with text alternative
3. **Accessibility:** Proper semantic HTML, alt text for images
4. **Brand Consistency:** Reusable components ensure consistent styling
5. **Testing:** Preview functionality available before sending

---

## Recommendations

### Immediate Actions (Phase 0 - Current)

1. ✅ **Complete this audit** - Document all templates and requirements
2. ⏭️ **Proceed to Task 0.1.6** - Review existing tests

### Phase 1 Actions (Before LemonSqueezy Implementation)

1. **Enhance 3 templates** (1-2 hours):
   - Add card info to `payment_succeeded.py`
   - Add customer portal URL to `payment_failed.py`
   - Add invoice URL to `subscription_renewed.py`

2. **Create email preview routes** (Optional, 1 hour):
   - Preview all billing templates with sample data
   - Helps with testing and validation

3. **Document webhook → email mapping** (30 minutes):
   - Create flow diagram showing which webhook triggers which email
   - Add to webhook handler implementation guide

---

### Phase 2 Actions (During LemonSqueezy Implementation)

1. **Update webhook handlers** to populate new parameters:
   ```python
   # In subscription_payment_success handler
   html = render_payment_succeeded_email(
       user_name=user.display_name,
       plan_name=plan.display_name,
       amount=f"${webhook_data['data']['attributes']['total']}",
       payment_date=format_date(webhook_data['data']['attributes']['created_at']),
       next_billing_date=format_date(webhook_data['data']['attributes']['renews_at']),
       invoice_url=webhook_data['data']['attributes']['urls']['invoice'],  # NEW
       card_brand=webhook_data['data']['attributes']['card_brand'],         # NEW
       card_last_four=webhook_data['data']['attributes']['card_last_four'], # NEW
       dashboard_url=f"{frontend_url}/settings/billing"
   )
   ```

2. **Test emails with LemonSqueezy sandbox** data:
   - Trigger test webhooks
   - Verify emails render correctly
   - Check all links work

3. **Monitor email deliverability**:
   - Check spam scores
   - Monitor bounce rates
   - Track open/click rates

---

### Phase 3 Actions (Optional - Future Enhancements)

1. **Create license key template** (if selling one-time products)
2. **Create pause/unpause templates** (if using pause feature)
3. **Add email personalization** (user preferences, localization)
4. **A/B test email copy** (subject lines, CTAs, content)
5. **Add email preview in dashboard** (show sent emails to users)

---

## Success Criteria

This audit is considered complete when:

1. ✅ All billing email templates documented
2. ✅ Template parameters and data sources mapped
3. ✅ LemonSqueezy enhancement requirements identified
4. ✅ Implementation effort estimated
5. ✅ Testing strategy defined
6. ✅ Webhook → email mapping documented

---

## Conclusion

The email template system is **exceptionally well-designed** and **production-ready**:

1. **✅ Professional Architecture**: Component-based design with reusable elements
2. **✅ Mostly LemonSqueezy-Ready**: 8 of 11 templates require zero changes
3. **✅ Minor Enhancements Needed**: Only 3 templates need 1-2 hour total effort
4. **✅ Clean Separation**: Templates are provider-agnostic, using generic data
5. **✅ Comprehensive Coverage**: All necessary email types already exist

**Overall Assessment:** The email template system is in excellent shape. LemonSqueezy integration requires minimal changes (adding card info and invoice URLs to 3 templates). The component-based architecture makes updates easy and ensures consistent branding.

**Total Implementation Effort:**
- Required enhancements: 1 hour
- Optional new templates: 3-7 hours
- Testing: 4-7 hours
- **Total: 8-15 hours** (with optional features)

**Next Steps:**
- ✅ Mark Task 0.1.5 as complete
- ⏭️ Proceed to Task 0.1.6: Review existing tests

---

## Appendix A: Complete Template File List

```
wrext-backend/
└── emails/
    ├── components/
    │   ├── __init__.py
    │   ├── base.py                     (Email wrapper structure)
    │   ├── button.py                   (Primary/secondary button components)
    │   ├── header.py                   (WREXT logo + branding header)
    │   └── footer.py                   (Unsubscribe + copyright footer)
    ├── utils/
    │   ├── __init__.py
    │   └── renderer.py                 (compose_email function)
    └── templates/
        └── billing/
            ├── __init__.py
            ├── subscription_created.py         (109 lines) ✅
            ├── payment_succeeded.py            (125 lines) ⚠️ Add card info
            ├── payment_failed.py               (106 lines) ⚠️ Add portal URL
            ├── subscription_cancelled.py       (102 lines) ✅
            ├── trial_ending.py                 (98 lines) ✅
            ├── subscription_renewed.py         (102 lines) ⚠️ Add invoice URL
            ├── subscription_expiring_soon.py   (101 lines) ✅
            ├── upgrade_successful.py           (104 lines) ✅
            ├── downgrade_scheduled.py          (104 lines) ✅
            ├── usage_limit_warning.py          (107 lines) ✅
            └── usage_limit_exceeded.py         (122 lines) ✅
```

---

## Appendix B: Template Parameter Reference

### Common Parameters (All Templates)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `user_name` | str | Yes | - | User's display name or email |
| `frontend_url` | str | No | "https://app.wrext.com" | Base frontend URL for branding |

### Subscription Lifecycle Templates

**Subscription Created:**
- `plan_name: str` - Plan display name
- `plan_price: str` - Formatted price with currency
- `billing_period: str` - "monthly" or "yearly"
- `features: List[str]` - Top 5 plan features
- `dashboard_url: str` - Billing dashboard URL

**Trial Ending:**
- `plan_name: str` - Plan display name
- `trial_end_date: str` - Formatted date
- `days_remaining: int` - Days until trial expires
- `upgrade_url: str` - Upgrade/pricing page URL

**Subscription Expiring Soon:**
- `plan_name: str` - Plan display name
- `expiry_date: str` - Formatted date
- `days_remaining: int` - Days until expiration
- `renew_url: str` - Renewal URL
- `pricing_url: str` - Pricing page URL

**Subscription Cancelled:**
- `plan_name: str` - Plan display name
- `end_date: str` - Access end date
- `reactivate_url: str` - Reactivation URL
- `feedback_url: str` - Feedback form URL

### Payment Templates

**Payment Succeeded:**
- `plan_name: str` - Plan display name
- `amount: str` - Payment amount (formatted)
- `payment_date: str` - Payment date
- `next_billing_date: str` - Next charge date
- `invoice_url: str` - Invoice download URL (optional)
- `card_brand: str` - Card brand (NEW)
- `card_last_four: str` - Last 4 digits (NEW)
- `dashboard_url: str` - Billing dashboard URL

**Payment Failed:**
- `plan_name: str` - Plan display name
- `amount: str` - Failed amount
- `retry_date: str` - Next retry date
- `update_payment_url: str` - Payment method update URL
- `customer_portal_url: str` - Direct portal URL (NEW)

**Subscription Renewed:**
- `plan_name: str` - Plan display name
- `amount: str` - Renewal amount
- `renewal_date: str` - Renewal date
- `next_billing_date: str` - Next charge date
- `invoice_url: str` - Invoice download URL (NEW)
- `dashboard_url: str` - Billing dashboard URL

### Plan Change Templates

**Upgrade Successful:**
- `old_plan_name: str` - Previous plan
- `new_plan_name: str` - New plan
- `new_features: list[str]` - New features unlocked
- `effective_date: str` - Upgrade date
- `manage_url: str` - Subscription management URL
- `docs_url: str` - Documentation URL

**Downgrade Scheduled:**
- `current_plan_name: str` - Current plan
- `new_plan_name: str` - Future plan
- `effective_date: str` - Downgrade date
- `features_losing: list[str]` - Features being removed
- `cancel_downgrade_url: str` - Cancel downgrade URL
- `pricing_url: str` - Pricing page URL

### Usage Templates

**Usage Limit Warning:**
- `resource_type: str` - Resource name (e.g., "API calls")
- `current_usage: int` - Current count
- `usage_limit: int` - Maximum allowed
- `percentage_used: int` - Percentage (e.g., 80)
- `plan_name: str` - Plan display name
- `upgrade_url: str` - Upgrade URL
- `usage_url: str` - Detailed usage page URL

**Usage Limit Exceeded:**
- `resource_type: str` - Resource name
- `current_usage: int` - Current count (over limit)
- `usage_limit: int` - Maximum allowed
- `plan_name: str` - Plan display name
- `restrictions: list[str]` - Restricted features
- `upgrade_url: str` - Upgrade URL
- `usage_url: str` - Detailed usage page URL

---

**Document Version:** 1.0
**Last Updated:** 2025-10-17
**Status:** ✅ Complete
