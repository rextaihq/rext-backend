# Payment & Billing Privacy Policy

**Effective Date:** 2025-10-20
**Last Updated:** 2025-10-20
**Version:** 1.0

---

## Introduction

This Payment & Billing Privacy Policy supplements WREXT's main Privacy Policy and provides specific details about how we collect, use, store, and protect your payment and billing information.

**WREXT** ("we," "our," or "us") is committed to protecting your privacy and ensuring the security of your payment data. This document explains our practices regarding payment information in clear, transparent terms.

---

## Table of Contents

1. [Information We Collect](#information-we-collect)
2. [How We Use Your Information](#how-we-use-your-information)
3. [Information We Do NOT Collect](#information-we-do-not-collect)
4. [Data Sharing & Third Parties](#data-sharing--third-parties)
5. [Data Storage & Security](#data-storage--security)
6. [Data Retention](#data-retention)
7. [Your Rights & Choices](#your-rights--choices)
8. [International Data Transfers](#international-data-transfers)
9. [Children's Privacy](#childrens-privacy)
10. [Changes to This Policy](#changes-to-this-policy)
11. [Contact Us](#contact-us)

---

## Information We Collect

When you subscribe to WREXT or make a payment, we collect the following information:

### 1. Subscription Information (Stored by WREXT)

We store the following subscription-related data in our database:

- **Subscription ID:** Unique identifier for your subscription (reference only)
- **Customer ID:** LemonSqueezy customer reference (no payment details)
- **Plan Information:** Plan name (e.g., "Pro", "Enterprise"), features, and pricing
- **Subscription Status:** Current state (active, cancelled, expired, suspended, trial)
- **Billing Cycle Dates:** Current period start/end, next billing date, trial end date
- **Transaction Metadata:**
  - Transaction amounts and currency
  - Transaction timestamps
  - Payment success/failure status
  - Refund information (if applicable)
- **Usage Data:** Feature usage and limit tracking (for plan enforcement)

### 2. Billing Information (Stored by LemonSqueezy)

The following payment details are collected and stored **exclusively by LemonSqueezy** (our payment processor), **NOT by WREXT**:

- **Payment Card Details:** Card number, CVV, expiration date (encrypted by LemonSqueezy)
- **Billing Address:** Street address, city, state/province, postal code, country
- **Cardholder Name:** Name as it appears on payment card
- **Payment Method:** Card type (Visa, Mastercard, etc.), last 4 digits
- **Invoices & Receipts:** Transaction history, billing statements

**Important:** WREXT does **NOT** have access to your full payment card details. All payment information is securely stored in LemonSqueezy's PCI DSS Level 1 compliant systems.

### 3. Account Information (General)

- **Email Address:** Used for receipts, subscription notifications, and account communications
- **Name:** Your first and last name (if provided)
- **User ID:** Internal WREXT user identifier (linked to subscription)

### 4. Automatically Collected Information

- **IP Address:** Logged for fraud prevention and security monitoring
- **Browser/Device Information:** User agent, device type, operating system
- **Access Logs:** Timestamps of payment-related actions (checkout, cancellation, portal access)

---

## How We Use Your Information

We use your payment and billing information for the following purposes:

### 1. **Process Payments & Subscriptions**
- Create and manage your subscription
- Process payments through LemonSqueezy
- Send you invoices and receipts
- Handle refunds and billing disputes

### 2. **Service Delivery**
- Grant access to paid features based on your plan
- Enforce usage limits according to your subscription tier
- Notify you about subscription changes (upgrades, downgrades, cancellations)
- Send renewal reminders and payment failure notifications

### 3. **Fraud Prevention & Security**
- Detect and prevent fraudulent transactions
- Monitor for suspicious payment activity
- Verify webhook signatures from payment processor
- Log payment operations for audit trail (compliance)

### 4. **Customer Support**
- Respond to billing inquiries and support requests
- Troubleshoot payment issues
- Process refund requests
- Assist with subscription changes

### 5. **Legal Compliance**
- Comply with tax laws and financial regulations
- Maintain records for accounting and auditing purposes
- Respond to legal requests (subpoenas, court orders)
- Meet PCI DSS, GDPR, and CCPA requirements

### 6. **Analytics & Improvements** (Aggregated Data Only)
- Analyze subscription trends and churn rates
- Improve payment flow user experience
- Monitor payment system performance
- Identify and fix payment errors

**Note:** We do NOT use your payment information for marketing purposes without your explicit consent.

---

## Information We Do NOT Collect

WREXT does **NOT** collect, store, or process the following payment data:

- ❌ **Full credit/debit card numbers**
- ❌ **CVV/CVC security codes**
- ❌ **Card expiration dates**
- ❌ **Card PINs or passwords**
- ❌ **Bank account numbers** (except if provided for bank transfer, stored by LemonSqueezy only)
- ❌ **Cryptocurrency wallet private keys**

All sensitive payment data is handled exclusively by **LemonSqueezy**, our PCI DSS Level 1 certified payment processor.

---

## Data Sharing & Third Parties

### Who We Share Data With

#### 1. **LemonSqueezy (Payment Processor)** - REQUIRED

**Role:** Payment processing and merchant of record
**Data Shared:**
- Email address
- Name (if provided)
- Selected plan and pricing
- User ID and metadata (for subscription tracking)

**Purpose:** Process payments, manage subscriptions, handle refunds, provide invoices

**Legal Basis:**
- **Contract Performance:** Necessary to fulfill subscription agreement
- **GDPR Article 6(1)(b):** Processing necessary for contract
- **Data Processing Agreement (DPA):** https://www.lemonsqueezy.com/dpa

**LemonSqueezy's Certifications:**
- ✅ PCI DSS Level 1 Service Provider
- ✅ SOC 2 Type II Certified
- ✅ GDPR Compliant
- ✅ ISO 27001 Certified

**Privacy Policy:** https://www.lemonsqueezy.com/privacy
**Security:** https://www.lemonsqueezy.com/security

#### 2. **Cloud Hosting Provider** - REQUIRED

**Role:** Infrastructure hosting (database, application servers)
**Data Shared:** Subscription metadata (reference IDs, status, dates)
**Purpose:** Host WREXT application and database
**Security:** Database encryption at rest, access controls, regular backups

**Note:** No payment card data stored on our servers (only reference IDs).

#### 3. **Error Monitoring (Sentry)** - REQUIRED

**Role:** Application error tracking and alerting
**Data Shared:** Payment errors, correlation IDs, subscription IDs (sanitized)
**Purpose:** Detect and resolve payment system issues
**Security:** Payment card data NEVER sent to Sentry (sanitized before logging)

**Privacy Policy:** https://sentry.io/privacy/

#### 4. **Email Service Provider** - REQUIRED

**Role:** Transactional emails (receipts, notifications)
**Data Shared:** Email address, subscription status, transaction details
**Purpose:** Send subscription confirmations, payment receipts, renewal reminders
**Security:** HTTPS/TLS encryption, DKIM/SPF authentication

### Who We Do NOT Share Data With

- ❌ **Marketing companies or advertisers** (unless you explicitly opt-in)
- ❌ **Data brokers or aggregators**
- ❌ **Social media platforms** (for advertising purposes)
- ❌ **Third-party analytics** (beyond aggregated, anonymized data)

**We do NOT sell your payment information to anyone.**

### Legal Disclosures

We may disclose payment information if required by law:
- Court orders, subpoenas, or legal processes
- Government investigations or regulatory requests
- Protection of our legal rights or prevention of fraud
- Compliance with tax authorities and financial regulators

**We will notify you of legal requests unless prohibited by law.**

---

## Data Storage & Security

### Where Your Data is Stored

- **WREXT Database:** Subscription metadata (reference IDs, status, dates) stored in PostgreSQL database
- **LemonSqueezy Systems:** Payment card data stored in PCI DSS Level 1 compliant vaults
- **Geographic Location:** Servers located in [Your Hosting Region - e.g., United States, EU]

### Security Measures

We implement industry-standard security practices to protect your payment data:

#### 1. **Encryption**
- **In Transit:** HTTPS/TLS 1.2+ for all connections (API, webhooks, web traffic)
- **At Rest:** PostgreSQL database encryption (managed by hosting provider)
- **API Keys:** Stored in environment variables or secrets manager (never hardcoded)

#### 2. **Access Control**
- **Authentication:** JWT tokens with 24-hour expiration
- **Authorization:** Role-based access control (RBAC) - admin, user, super_admin
- **Database Access:** Restricted to authorized personnel only
- **Audit Logging:** All payment operations logged with user ID and timestamp

#### 3. **Payment Security**
- **PCI DSS SAQ-A Compliance:** WREXT qualifies for lowest-scope compliance (no cardholder data)
- **Webhook Signature Verification:** HMAC-SHA256 validation prevents unauthorized events
- **Rate Limiting:** Payment endpoints limited (5-10 requests/min per user)
- **API Key Rotation:** 90-day rotation policy for LemonSqueezy API keys

#### 4. **Monitoring & Alerts**
- **Error Monitoring:** Sentry tracks payment errors in real-time
- **Security Alerts:** Automatic alerts for webhook signature failures, API errors
- **Health Checks:** `/health/payment` endpoint monitors system status
- **Incident Response:** 24-hour response time for critical security issues

#### 5. **Fraud Prevention**
- **IP Address Logging:** Detects suspicious payment patterns
- **Idempotency Tracking:** Prevents duplicate webhook processing
- **Payment Velocity Checks:** Rate limiting prevents abuse

See [COMPLIANCE.md](COMPLIANCE.md) for detailed security architecture.

### Data Breach Response

In the unlikely event of a data breach affecting payment data:

1. **Immediate Response (0-24 hours):**
   - Contain the breach and secure systems
   - Assess scope and impact
   - Notify leadership and legal counsel

2. **Investigation (24-72 hours):**
   - Determine root cause
   - Identify affected users
   - Prepare notification plan

3. **User Notification (within 72 hours):**
   - Email notification to affected users
   - Explanation of what data was compromised
   - Steps being taken to address the issue
   - Recommended actions for users

4. **Regulatory Notification:**
   - Notify relevant authorities (ICO, FTC, state attorneys general)
   - File required breach reports (GDPR, CCPA)

**Emergency Contact:** security@wrext.com

---

## Data Retention

We retain payment and subscription data as follows:

### Active Subscriptions

| Data Type | Retention Period | Reason |
|-----------|-----------------|--------|
| Subscription records | Indefinite (while active) | Service delivery |
| Transaction history | Indefinite (while active) | Account management, support |
| Webhook events | 90 days | Debugging, audit trail |
| Audit logs | 1 year | Security, compliance |

### Cancelled/Expired Subscriptions

| Data Type | Retention Period | Reason |
|-----------|-----------------|--------|
| Subscription records | 7 years after cancellation | Tax compliance, financial records |
| Transaction history | 7 years after cancellation | Financial regulations (IRS, HMRC) |
| Webhook events | 90 days | Debugging (deleted after) |
| Audit logs | 1 year | Security (deleted after) |

### User Account Deletion

When you delete your WREXT account:

1. **Immediate (Day 1):**
   - Account deactivated and login disabled
   - Active subscription cancelled (if applicable)
   - 7-day grace period to reverse deletion

2. **After Grace Period (Day 8):**
   - Personal data deleted (name, email, profile information)
   - Subscription data anonymized (user_id set to null)
   - Access logs and session data deleted

3. **Long-Term Retention (7 years):**
   - Anonymized financial records (for tax compliance)
   - Aggregated analytics data (no personal identifiers)

**Note:** Financial records must be retained for 7 years per tax regulations (IRS, EU VAT). These records are anonymized (no link to your identity).

### LemonSqueezy Data Retention

LemonSqueezy retains payment data according to their own retention policies:
- See: https://www.lemonsqueezy.com/privacy
- To request deletion of payment data: contact LemonSqueezy support

---

## Your Rights & Choices

Under GDPR, CCPA, and other privacy laws, you have the following rights:

### 1. **Right to Access**

**What it means:** You can request a copy of all payment data we hold about you.

**How to exercise:**
- Log in to your account and visit the **Billing Dashboard**
- Download your subscription history via **CSV Export**
- For full data export, email: privacy@wrext.com

**Response time:** Within 30 days (GDPR requirement)

### 2. **Right to Rectification**

**What it means:** You can update or correct inaccurate payment information.

**How to exercise:**
- Update email address in **Account Settings**
- Update billing information via **LemonSqueezy Customer Portal** (button in Billing Dashboard)
- For other corrections: contact support@wrext.com

### 3. **Right to Erasure ("Right to be Forgotten")**

**What it means:** You can request deletion of your payment data (with exceptions).

**How to exercise:**
1. Log in and go to **Account Settings**
2. Click **Delete My Account**
3. Confirm deletion request
4. 7-day grace period (can cancel deletion)
5. Account and personal data deleted after grace period

**Exceptions:**
- Financial records retained for 7 years (anonymized, for tax compliance)
- Legal obligations (e.g., court orders, tax audits)
- Fraud prevention (flagged accounts)

**Email:** privacy@wrext.com (if you need assistance)

### 4. **Right to Data Portability**

**What it means:** You can export your subscription data in a machine-readable format.

**How to exercise:**
- Visit **Billing Dashboard** → **Usage & Analytics**
- Click **Export to CSV** (includes subscription history, invoices, usage data)
- Format: CSV (compatible with Excel, Google Sheets)

### 5. **Right to Restriction**

**What it means:** You can limit how we use your payment data.

**How to exercise:**
- **Pause subscription:** Not currently supported (cancel and re-subscribe instead)
- **Cancel subscription:** Visit **Billing Dashboard** → **Cancel Subscription**
- **Opt-out of emails:** Unsubscribe link in all emails (except transactional)

### 6. **Right to Object**

**What it means:** You can object to certain uses of your data.

**How to exercise:**
- **Marketing emails:** Click "Unsubscribe" in any marketing email
- **Analytics:** Aggregated data only (no personal identifiers)
- **Profiling:** We do not use payment data for automated decision-making

### 7. **Right to Non-Discrimination (CCPA)**

**What it means:** You will receive equal service regardless of privacy choices.

**WREXT's commitment:** We will NOT:
- Deny service if you exercise privacy rights
- Charge different prices based on privacy choices
- Provide lower quality service if you opt-out

### How to Exercise Your Rights

**Email:** privacy@wrext.com
**Subject Line:** "Privacy Request - [Right Name]"
**Include:**
- Your full name
- Email address associated with account
- Specific request and action desired

**Response Time:**
- GDPR: Within 30 days
- CCPA: Within 45 days (may extend to 90 days if complex)

**Verification:**
- We may ask for additional information to verify your identity
- This protects your data from unauthorized access

---

## International Data Transfers

### For Users in the European Union (EU/EEA)

Your payment data may be transferred to and processed in countries outside the EU/EEA:

**LemonSqueezy:**
- **Primary Location:** United States
- **Safeguards:** Standard Contractual Clauses (SCCs), EU-U.S. Data Privacy Framework
- **DPA:** https://www.lemonsqueezy.com/dpa

**WREXT Servers:**
- **Primary Location:** [Your Hosting Region - e.g., United States]
- **Safeguards:** Database encryption, access controls, GDPR compliance

**Legal Basis for Transfers:**
- GDPR Article 46 (Standard Contractual Clauses)
- GDPR Article 49 (Necessary for contract performance)

### For Users in the United Kingdom (UK)

Post-Brexit data transfers are governed by the UK GDPR and Data Protection Act 2018:
- LemonSqueezy uses UK-approved Standard Contractual Clauses (SCCs)
- Transfers are necessary for contract performance (subscription service)

### For Users in California (CCPA)

WREXT does **NOT** sell personal information to third parties. Data shared with LemonSqueezy is for service provision only (exempt from "sale" definition under CCPA).

---

## Children's Privacy

WREXT is **NOT intended for children under 16 years old**.

- We do not knowingly collect payment information from children
- If you are under 16, do not create an account or subscribe
- If we discover a child's account, we will delete it immediately

**Parental Notice:** If you believe your child has provided payment information, contact: privacy@wrext.com

---

## Changes to This Policy

We may update this Payment & Billing Privacy Policy from time to time.

**Notice of Changes:**
- **Effective Date:** Displayed at the top of this document
- **Material Changes:** Email notification to all users (30 days before effective date)
- **Minor Changes:** Updated "Last Updated" date, no email notification

**Version History:**

| Version | Date | Summary of Changes |
|---------|------|-------------------|
| 1.0 | 2025-10-20 | Initial policy - LemonSqueezy integration, GDPR/CCPA compliance |

**Your Options:**
- If you disagree with changes, you may cancel your subscription before the effective date
- Continued use after the effective date constitutes acceptance of the new policy

---

## Contact Us

### Privacy Inquiries

**Email:** privacy@wrext.com
**Response Time:** 2 business days (general inquiries), 30 days (data subject requests)

**Mailing Address:**
WREXT Privacy Team
[Your Company Address]
[City, State, ZIP]
[Country]

### Data Protection Officer (DPO)

**Email:** dpo@wrext.com (if required by GDPR)
**Role:** Oversees GDPR compliance and data protection

### Security Issues

**Email:** security@wrext.com
**Response Time:** 24 hours for critical issues

### Payment Processor (LemonSqueezy)

**Privacy Policy:** https://www.lemonsqueezy.com/privacy
**Support:** https://www.lemonsqueezy.com/help
**DPA:** https://www.lemonsqueezy.com/dpa

### Regulatory Authorities

If you are not satisfied with our response to a privacy request, you may file a complaint with:

**EU/EEA Users:**
- Your local Data Protection Authority (DPA)
- List: https://edpb.europa.eu/about-edpb/board/members_en

**UK Users:**
- Information Commissioner's Office (ICO)
- Website: https://ico.org.uk
- Phone: +44 303 123 1113

**California Users:**
- California Attorney General's Office
- Website: https://oag.ca.gov/privacy/ccpa
- Phone: 1-800-952-5225

---

## Related Policies & Documents

- [Main Privacy Policy](PRIVACY_POLICY.md) - General privacy practices (all data)
- [Compliance Documentation](COMPLIANCE.md) - PCI DSS, GDPR, CCPA compliance
- [Terms of Service](SUBSCRIPTION_TERMS.md) - Subscription terms and conditions
- [Refund Policy](REFUND_POLICY.md) - Refund and cancellation policies
- [Security Architecture](COMPLIANCE.md#security-architecture) - Technical security measures

---

**Thank you for trusting WREXT with your subscription. We are committed to protecting your privacy and securing your payment data.**

**Questions?** Email us at privacy@wrext.com

---

**Effective Date:** 2025-10-20
**Version:** 1.0
