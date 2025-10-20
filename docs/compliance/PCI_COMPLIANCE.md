# PCI DSS Compliance Documentation

**Document Version:** 1.0
**Last Updated:** 2025-10-20
**Review Schedule:** Annual (October)
**Owner:** Engineering Team
**Status:** Active

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [LemonSqueezy PCI Compliance](#lemonsqueezy-pci-compliance)
3. [Our PCI Compliance Scope](#our-pci-compliance-scope)
4. [Data Storage Analysis](#data-storage-analysis)
5. [Data We DO NOT Store](#data-we-do-not-store)
6. [Payment Data Flow](#payment-data-flow)
7. [Security Controls](#security-controls)
8. [PCI DSS Compliance Checklist](#pci-dss-compliance-checklist)
9. [Incident Response](#incident-response)
10. [Annual Review Process](#annual-review-process)
11. [References](#references)

---

## Executive Summary

### Compliance Posture

**WREXT operates under PCI DSS SAQ A compliance requirements** because:

- ✅ We use LemonSqueezy's fully hosted payment solution
- ✅ We **DO NOT** store, process, or transmit cardholder data
- ✅ All payment processing occurs on LemonSqueezy's PCI DSS Level 1 certified infrastructure
- ✅ Payment forms are embedded via iframe/overlay (hosted by LemonSqueezy)
- ✅ Our servers never touch credit card data

### Key Compliance Statements

1. **No Cardholder Data Storage**: We do not store primary account numbers (PANs), CVV/CVC codes, or full magnetic stripe data
2. **Hosted Payment Solution**: All payment collection occurs via LemonSqueezy's hosted checkout
3. **Reference IDs Only**: We only store non-sensitive reference IDs (subscription IDs, customer IDs)
4. **Reduced Scope**: This architecture significantly reduces our PCI DSS compliance scope to SAQ A
5. **Third-Party Certified**: LemonSqueezy maintains PCI DSS Level 1 Service Provider certification

### Compliance Level

**Self-Assessment Questionnaire (SAQ) Type:** SAQ A
**Merchant Level:** Level 4 (processing fewer than 1 million transactions annually)
**Validation Requirements:**
- Annual SAQ A completion
- Quarterly network vulnerability scans (if applicable)
- Annual review of policies and procedures

---

## LemonSqueezy PCI Compliance

### LemonSqueezy's Certifications

LemonSqueezy maintains the following security certifications and compliance standards:

#### PCI DSS Level 1 Service Provider
- **Certification Type:** PCI DSS Level 1 Service Provider (highest level)
- **Scope:** All payment processing infrastructure
- **Validation:** Annual on-site audit by Qualified Security Assessor (QSA)
- **Certificate Validity:** Renewed annually
- **Verification:** [LemonSqueezy Security Page](https://www.lemonsqueezy.com/security)

#### Additional Security Standards
- **TLS 1.2+:** All communications encrypted with modern TLS
- **Data Encryption:** Cardholder data encrypted at rest using AES-256
- **Secure Infrastructure:** Hosted on AWS with industry-standard security controls
- **Regular Security Audits:** Penetration testing and vulnerability assessments
- **GDPR Compliance:** European data protection regulations
- **SOC 2 Type II:** Service Organization Control (in progress)

### LemonSqueezy's Responsibilities

As our payment service provider, LemonSqueezy is responsible for:

1. **Secure Payment Processing**
   - Collecting payment information via PCI-compliant forms
   - Tokenizing cardholder data
   - Processing payments with card networks
   - Managing payment method storage

2. **Cardholder Data Security**
   - Encrypting cardholder data at rest and in transit
   - Maintaining secure payment card industry infrastructure
   - Implementing access controls and logging
   - Conducting regular security assessments

3. **Compliance Maintenance**
   - Annual PCI DSS validation
   - Quarterly vulnerability scans
   - Security incident response
   - Compliance documentation

4. **Customer Portal**
   - Secure customer authentication
   - Payment method updates (hosted)
   - Invoice access and billing history

### LemonSqueezy Documentation

- **Security Overview:** https://docs.lemonsqueezy.com/guides/developer-guide/security
- **Webhooks Security:** https://docs.lemonsqueezy.com/guides/developer-guide/webhooks#signing-requests
- **Checkout Security:** https://docs.lemonsqueezy.com/guides/developer-guide/checkout
- **Attestation of Compliance (AOC):** Available upon request from LemonSqueezy support

---

## Our PCI Compliance Scope

### What We Are Responsible For

Even though LemonSqueezy handles all cardholder data, we maintain responsibility for:

1. **Secure Integration**
   - ✅ Using HTTPS for all communications with LemonSqueezy API
   - ✅ Verifying webhook signatures to prevent spoofing
   - ✅ Implementing proper authentication for our application
   - ✅ Rate limiting to prevent abuse

2. **Reference Data Protection**
   - ✅ Securely storing LemonSqueezy reference IDs (subscription IDs, customer IDs)
   - ✅ Implementing access controls for subscription data
   - ✅ Audit logging for payment-related operations
   - ✅ Data retention policies for non-cardholder data

3. **Application Security**
   - ✅ Secure authentication (JWT tokens)
   - ✅ Authorization and role-based access control (RBAC)
   - ✅ Protection against common vulnerabilities (SQL injection, XSS, CSRF)
   - ✅ Regular security updates and dependency management

4. **Monitoring & Incident Response**
   - ✅ Error monitoring (Sentry integration)
   - ✅ Audit logging for compliance
   - ✅ Security incident response procedures
   - ✅ Alerting for suspicious activity

### SAQ A Requirements

As an SAQ A merchant, we must:

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| **1. Firewall Configuration** | ✅ Compliant | Cloud provider (AWS/GCP/Azure) managed firewalls |
| **2. Vendor Default Passwords** | ✅ Compliant | All defaults changed, strong passwords enforced |
| **3. Cardholder Data Protection** | ✅ Compliant | No cardholder data stored |
| **4. Encrypted Transmission** | ✅ Compliant | HTTPS/TLS 1.2+ for all communications |
| **5. Anti-Virus Software** | ✅ Compliant | Cloud provider security, container scanning |
| **6. Secure Systems** | ✅ Compliant | Regular dependency updates, security patches |
| **7. Access Control** | ✅ Compliant | RBAC, JWT authentication, principle of least privilege |
| **8. Unique IDs** | ✅ Compliant | All users have unique IDs, no shared accounts |
| **9. Physical Access** | ✅ Compliant | Cloud-hosted, provider physical security |
| **10. Logging & Monitoring** | ✅ Compliant | Audit logs, Sentry monitoring, structured logging |
| **11. Security Testing** | ✅ Compliant | Regular vulnerability scans, dependency audits |
| **12. Security Policy** | ✅ Compliant | Documented security policies (this document) |

---

## Data Storage Analysis

### What Payment-Related Data We Store

Our database stores **only non-sensitive reference data**:

#### Subscription Data (`user_subscriptions` table)
```sql
-- Reference IDs (NON-SENSITIVE)
lemonsqueezy_subscription_id    VARCHAR(255)  -- e.g., "sub_123abc"
lemonsqueezy_customer_id        VARCHAR(255)  -- e.g., "cus_456def"
lemonsqueezy_order_id           VARCHAR(255)  -- e.g., "ord_789ghi"
lemonsqueezy_product_id         VARCHAR(255)  -- e.g., "prod_101jkl"
lemonsqueezy_variant_id         VARCHAR(255)  -- e.g., "var_202mno"

-- Subscription metadata (NON-SENSITIVE)
status                          ENUM          -- active, cancelled, expired, etc.
billing_period                  ENUM          -- monthly, yearly
start_date                      TIMESTAMP
end_date                        TIMESTAMP
renews_at                       TIMESTAMP
cancelled_at                    TIMESTAMP
trial_end_date                  TIMESTAMP

-- Usage tracking (NON-SENSITIVE)
current_api_calls               INTEGER
usage_reset_date                TIMESTAMP

-- Provider metadata (NON-SENSITIVE)
subscription_metadata           JSONB         -- Discount codes, affiliate IDs
```

**PCI Compliance Note:** These fields contain only reference identifiers. No cardholder data.

#### Payment Method Data (`payment_methods` table)
```sql
-- Reference IDs (NON-SENSITIVE)
provider_payment_method_id      VARCHAR(255)  -- LemonSqueezy payment method ID
provider_customer_id            VARCHAR(255)  -- LemonSqueezy customer ID

-- Card display data (SAFE TO STORE per PCI DSS)
card_brand                      VARCHAR(50)   -- "visa", "mastercard", "amex"
card_last4                      VARCHAR(4)    -- Last 4 digits only (e.g., "4242")
card_exp_month                  INTEGER       -- Expiration month
card_exp_year                   INTEGER       -- Expiration year

-- Metadata (NON-SENSITIVE)
type                            VARCHAR(50)   -- "card", "bank_account"
is_default                      BOOLEAN
status                          VARCHAR(50)   -- "active", "expired"
billing_email                   VARCHAR(255)  -- Email for receipts
```

**PCI Compliance Note:** Storing card brand, last 4 digits, and expiration date is **explicitly allowed** by PCI DSS for customer service and reporting purposes, as long as they are not stored with the full PAN.

#### Invoice/Payment Records (`invoices` table - if exists)
```sql
-- Reference IDs (NON-SENSITIVE)
lemonsqueezy_invoice_id         VARCHAR(255)  -- LemonSqueezy invoice ID
amount                          DECIMAL       -- Invoice amount
currency                        VARCHAR(3)    -- "USD", "EUR", etc.
status                          VARCHAR(50)   -- "paid", "pending", "failed"
invoice_url                     TEXT          -- Link to LemonSqueezy-hosted invoice
```

**PCI Compliance Note:** Invoice amounts and status are not cardholder data.

#### Webhook Events (`webhook_events` table)
```sql
-- Event tracking (NON-SENSITIVE)
event_id                        VARCHAR(255)  -- LemonSqueezy event ID
event_type                      VARCHAR(100)  -- "subscription_created", etc.
payload                         JSONB         -- Full webhook payload (verified signature)
processed_at                    TIMESTAMP
status                          VARCHAR(50)   -- "processed", "failed"
```

**PCI Compliance Note:** Webhook payloads from LemonSqueezy do not contain cardholder data, only reference IDs and subscription metadata.

---

## Data We DO NOT Store

### Prohibited Data (Never Stored)

Per PCI DSS requirements, we **never** store the following sensitive authentication data:

#### 1. Full Primary Account Number (PAN)
- ❌ Full credit/debit card numbers (e.g., "4242 4242 4242 4242")
- ❌ Even if encrypted or hashed
- ✅ Only store last 4 digits (e.g., "4242") for display purposes

#### 2. Card Verification Code/Value (CVV/CVC/CVV2/CVC2)
- ❌ 3 or 4-digit security codes on cards
- ❌ Never stored, even temporarily
- ❌ Not in logs, not in databases, not in memory dumps

#### 3. Full Magnetic Stripe Data
- ❌ Track 1, Track 2 data
- ❌ CAV/CVC/CVV magnetic stripe data
- ❌ Magnetic stripe equivalent data from chip cards

#### 4. PIN/PIN Blocks
- ❌ Personal Identification Numbers
- ❌ Encrypted or hashed PINs
- ❌ Not applicable to our integration (no PIN entry)

### Implementation Enforcement

**How we ensure prohibited data is never stored:**

1. **No Direct Card Input**
   - All payment forms are hosted by LemonSqueezy (iframe/overlay)
   - Our application never receives cardholder data from forms
   - No card input fields in our codebase

2. **Webhook Payload Verification**
   - LemonSqueezy webhooks do not include cardholder data
   - We verify webhook signatures before processing
   - Payloads contain only reference IDs and subscription metadata

3. **API Responses**
   - LemonSqueezy API responses do not include cardholder data
   - Customer and subscription objects contain only safe reference data
   - Card details are never returned in API responses

4. **Logging Controls**
   - Structured logging with sanitization
   - No cardholder data in application logs
   - Sensitive fields (if any) are automatically redacted

5. **Database Constraints**
   - No database columns for storing PANs or CVVs
   - Schema design enforces PCI compliance by design
   - Regular database audits verify compliance

---

## Payment Data Flow

### Checkout Flow (New Subscription)

```
┌─────────────┐
│   User      │
│  (Browser)  │
└──────┬──────┘
       │ 1. Click "Subscribe"
       ▼
┌─────────────────────┐
│  WREXT Frontend     │
│  (Next.js App)      │
└──────┬──────────────┘
       │ 2. POST /api/subscriptions/checkout
       │    { plan_id, billing_period }
       ▼
┌─────────────────────┐
│  WREXT Backend      │
│  (FastAPI)          │
│                     │
│  - Authenticate     │
│  - Validate plan    │
│  - Create checkout  │
└──────┬──────────────┘
       │ 3. API call: Create Checkout
       │    POST /v1/checkouts
       ▼
┌─────────────────────┐
│  LemonSqueezy API   │
│                     │
│  - Create checkout  │
│  - Generate URL     │
└──────┬──────────────┘
       │ 4. Return checkout_url
       │    { url: "https://lemonsqueezy.com/checkout/..." }
       ▼
┌─────────────────────┐
│  WREXT Backend      │
│  - Log checkout     │
│  - Return URL       │
└──────┬──────────────┘
       │ 5. Return checkout URL
       ▼
┌─────────────────────┐
│  WREXT Frontend     │
│  - Open overlay     │
└──────┬──────────────┘
       │ 6. Load checkout in iframe
       ▼
┌─────────────────────┐
│  LemonSqueezy       │
│  Checkout (Hosted)  │
│                     │
│  🔒 CARDHOLDER DATA │
│     ENTERED HERE    │
│                     │
│  - PCI DSS Level 1  │
│  - Encrypted forms  │
│  - Secure storage   │
└──────┬──────────────┘
       │ 7. Payment processed
       │    (Card networks: Visa, Mastercard, etc.)
       │
       │ 8. Webhook sent
       │    POST /api/webhooks/lemonsqueezy
       │    Event: subscription_created
       ▼
┌─────────────────────┐
│  WREXT Backend      │
│  (Webhook Handler)  │
│                     │
│  - Verify signature │
│  - Parse event      │
│  - Create sub       │
│  - Send email       │
└──────┬──────────────┘
       │ 9. Subscription active
       ▼
┌─────────────────────┐
│  Database           │
│  - subscription_id  │
│  - customer_id      │
│  - status: active   │
│  - NO CARD DATA     │
└─────────────────────┘
```

**Key Security Points:**

1. **Step 6:** Cardholder data is entered directly on LemonSqueezy's hosted checkout page
2. **Step 8:** Webhook payload contains only reference IDs (no cardholder data)
3. **Step 9:** Database stores only subscription metadata (no cardholder data)

### Subscription Update Flow (Change Plan)

```
User → WREXT Frontend → WREXT Backend → LemonSqueezy API
                                              ↓
                        Webhook ← Update subscription
                                              ↓
                        Database (update metadata)
```

**No cardholder data touches our systems** - LemonSqueezy handles billing changes automatically.

### Payment Method Update Flow

```
User → WREXT Frontend → Generate portal URL → Redirect to LemonSqueezy Portal
                                                        ↓
                                              🔒 User updates payment method
                                                 (Hosted by LemonSqueezy)
                                                        ↓
                                              Webhook → WREXT Backend
                                                        ↓
                                              Update payment_method metadata
                                              (last4, brand, expiry only)
```

**No cardholder data touches our systems** - all updates happen on LemonSqueezy's PCI-compliant portal.

---

## Security Controls

### 1. Transport Security

| Control | Implementation | Status |
|---------|----------------|--------|
| **HTTPS Enforcement** | All API endpoints require HTTPS/TLS 1.2+ | ✅ Active |
| **HSTS Headers** | Strict-Transport-Security header enabled | ✅ Active |
| **TLS Configuration** | TLS 1.2+ only, strong cipher suites | ✅ Active |
| **Certificate Validation** | Valid SSL certificates, auto-renewal | ✅ Active |

**Configuration:**
- Enforced at load balancer/reverse proxy level
- TLS 1.0/1.1 disabled (deprecated protocols)
- Forward secrecy enabled (ECDHE cipher suites)

### 2. Authentication & Authorization

| Control | Implementation | Status |
|---------|----------------|--------|
| **User Authentication** | JWT tokens with expiration | ✅ Active |
| **Password Security** | Bcrypt hashing (12 rounds) | ✅ Active |
| **Role-Based Access Control** | User/Admin/Super Admin roles | ✅ Active |
| **Session Management** | Secure token storage, auto-logout | ✅ Active |
| **Multi-Factor Authentication** | Planned (Phase 6) | 🔄 Planned |

**Files:**
- `src/api/middleware/auth.py` - JWT authentication
- `src/api/middleware/rbac.py` - Role-based access control

### 3. Webhook Security

| Control | Implementation | Status |
|---------|----------------|--------|
| **Signature Verification** | HMAC-SHA256 webhook signatures | ✅ Active |
| **Replay Protection** | Event ID idempotency checks | ✅ Active |
| **IP Whitelisting** | Optional LemonSqueezy IP filtering | 🔄 Optional |
| **Attack Detection** | Security monitoring (5 failures → alert) | ✅ Active |

**Implementation:**
- `src/utils/lemonsqueezy_webhook.py` - Signature verification
- `src/services/webhook_security_monitor.py` - Attack detection
- Production validation enforces webhook secret presence

**Documentation:**
- [Webhook Security Production Guide](../security/WEBHOOK_SECURITY_PRODUCTION.md)

### 4. Rate Limiting

| Endpoint | Limit | Window | Status |
|----------|-------|--------|--------|
| **Checkout** | 5 requests | 1 minute | ✅ Active |
| **Subscription Update** | 10 requests | 1 minute | ✅ Active |
| **Subscription Cancel** | 3 requests | 1 minute | ✅ Active |
| **Customer Portal** | 10 requests | 1 minute | ✅ Active |
| **Webhooks** | 100 requests | 1 minute | ✅ Active |

**Implementation:**
- `src/api/middleware/rate_limiter.py` - Payment-specific rate limiters
- Sliding window algorithm with Redis backing
- Per-user and per-IP rate limiting

### 5. Audit Logging

| Event Type | Log Level | Retention | Status |
|------------|-----------|-----------|--------|
| **Subscription Created** | INFO | 90 days | ✅ Active |
| **Payment Success** | INFO | 90 days | ✅ Active |
| **Payment Failed** | WARNING | 90 days | ✅ Active |
| **Subscription Cancelled** | INFO | 90 days | ✅ Active |
| **Webhook Signature Failure** | ERROR | 90 days | ✅ Active |
| **Admin Actions** | INFO | 365 days | ✅ Active |

**Implementation:**
- `src/services/audit_logger.py` - Centralized audit logging (701 lines, 30+ event types)
- Structured JSON logging with consistent schema
- Standard fields: event_type, timestamp, user_id, resource_id, changes, IP address

**Documentation:**
- [Audit Logging Guide](../AUDIT_LOGGING.md)

### 6. Error Monitoring

| System | Purpose | Status |
|--------|---------|--------|
| **Sentry** | Payment error tracking & alerting | ✅ Active |
| **Structured Logging** | Payment operation logging | ✅ Active |
| **Health Checks** | Payment system monitoring | ✅ Active |
| **Alerting** | Critical failure notifications | ✅ Active |

**Implementation:**
- `src/api/lib/sentry_config.py` - Payment-specific error tracking
- `src/api/lib/logging_config.py` - Structured payment logging
- `src/api/routes/health.py` - Health check endpoints

**Alert Configuration:**
- `docs/monitoring/SENTRY_ALERT_CONFIGURATION.md` - Alert rules (6 types)
- `docs/monitoring/PAYMENT_ALERT_RUNBOOKS.md` - Incident response procedures

### 7. API Key Security

| Control | Implementation | Status |
|---------|----------------|--------|
| **Secure Storage** | Environment variables, secrets manager | ✅ Active |
| **Rotation Policy** | 90-day rotation schedule | ✅ Active |
| **Validation** | Startup validation, format checks | ✅ Active |
| **Rotation Tools** | CLI validator, schedule checker | ✅ Active |
| **Git Protection** | Pre-commit hooks prevent key commits | ✅ Active |

**Implementation:**
- `scripts/validate_lemonsqueezy_keys.py` - Key validation CLI
- `scripts/check_key_rotation_schedule.py` - Rotation reminder system
- `.git-hooks/pre-commit` - Prevent accidental key commits

**Documentation:**
- [API Key Rotation Guide](../security/API_KEY_ROTATION.md)

### 8. Database Security

| Control | Implementation | Status |
|---------|----------------|--------|
| **Access Control** | Principle of least privilege | ✅ Active |
| **Connection Security** | SSL/TLS for database connections | ✅ Active |
| **Encryption at Rest** | Provider-managed encryption (recommended) | 🔄 Recommended |
| **SQL Injection Prevention** | SQLAlchemy ORM, parameterized queries | ✅ Active |
| **Backup Encryption** | Encrypted database backups | 🔄 Recommended |

**Configuration:**
- All queries use SQLAlchemy ORM (no raw SQL with user input)
- Database credentials stored in environment variables
- Regular automated backups with retention policies

### 9. Application Security

| Vulnerability | Protection | Status |
|---------------|------------|--------|
| **SQL Injection** | SQLAlchemy ORM, parameterized queries | ✅ Protected |
| **XSS** | React auto-escaping, Content Security Policy | ✅ Protected |
| **CSRF** | Not applicable (JWT-based API) | ✅ N/A |
| **Clickjacking** | X-Frame-Options headers | ✅ Protected |
| **Dependency Vulnerabilities** | Regular `npm audit`, `pip check` | ✅ Active |

**Frontend Security:**
- React 19 with automatic XSS prevention
- CSP headers configured
- No `dangerouslySetInnerHTML` usage in payment flows

**Backend Security:**
- FastAPI with automatic input validation (Pydantic)
- CORS configured with origin whitelisting
- Security headers middleware

---

## PCI DSS Compliance Checklist

### Annual SAQ A Completion

Use this checklist when completing your annual Self-Assessment Questionnaire (SAQ A):

#### Part 1: Prerequisites

- [ ] Confirm all payment processing uses LemonSqueezy hosted checkout
- [ ] Verify no payment forms on our website (only redirects/overlays to LemonSqueezy)
- [ ] Confirm no cardholder data flows through our systems
- [ ] Verify LemonSqueezy's current PCI DSS AOC (Attestation of Compliance)

#### Part 2: SAQ A Requirements (12 Requirements)

**Requirement 1: Firewall Configuration**
- [ ] Cloud provider managed firewalls configured
- [ ] Network segmentation in place
- [ ] Unnecessary ports closed

**Requirement 2: Vendor Defaults**
- [ ] All vendor default passwords changed
- [ ] Strong password policies enforced
- [ ] No default accounts active

**Requirement 3: Cardholder Data Protection**
- [ ] Confirmed: No cardholder data stored
- [ ] Database audit completed (no PAN, CVV, track data)
- [ ] Backup audit completed (no cardholder data)

**Requirement 4: Encrypted Transmission**
- [ ] HTTPS/TLS 1.2+ enforced on all endpoints
- [ ] TLS 1.0/1.1 disabled
- [ ] Strong cipher suites configured
- [ ] Valid SSL certificates

**Requirement 5: Anti-Virus Software**
- [ ] Cloud provider security controls active
- [ ] Container image scanning enabled
- [ ] Regular security updates applied

**Requirement 6: Secure Systems**
- [ ] Dependency updates applied monthly
- [ ] Security patches applied within 30 days of release
- [ ] Vulnerability scanning performed quarterly
- [ ] Code review process includes security checks

**Requirement 7: Access Control**
- [ ] RBAC implemented (User/Admin/Super Admin roles)
- [ ] Principle of least privilege enforced
- [ ] Access reviews conducted annually
- [ ] Inactive accounts disabled after 90 days

**Requirement 8: Unique IDs**
- [ ] All users have unique user IDs
- [ ] No shared accounts for system access
- [ ] Strong authentication enforced (JWT)
- [ ] Password complexity requirements met

**Requirement 9: Physical Access**
- [ ] Cloud-hosted (provider physical security)
- [ ] Data center security certification verified (AWS/GCP/Azure)
- [ ] No local cardholder data storage

**Requirement 10: Logging & Monitoring**
- [ ] Audit logging active for payment operations
- [ ] Logs retained for 90 days minimum
- [ ] Log review process documented
- [ ] Security monitoring active (Sentry)

**Requirement 11: Security Testing**
- [ ] Quarterly vulnerability scans completed
- [ ] Penetration testing (annual or after major changes)
- [ ] Dependency vulnerability audits (monthly)
- [ ] Intrusion detection/prevention active

**Requirement 12: Security Policy**
- [ ] Information security policy documented (this document)
- [ ] Incident response plan documented
- [ ] Security awareness training for developers
- [ ] Annual policy review completed

#### Part 3: Documentation

- [ ] SAQ A completed and signed
- [ ] Attestation of Compliance (AOC) retained
- [ ] LemonSqueezy AOC obtained and verified
- [ ] Policy documents updated
- [ ] All evidence collected and archived

### Quarterly Vulnerability Scans

**Schedule:** Every 3 months (January, April, July, October)

#### Scan Checklist

- [ ] Schedule scan with Approved Scanning Vendor (ASV) or internal tools
- [ ] Scan all public-facing systems
- [ ] Review scan results
- [ ] Remediate high/critical vulnerabilities within 30 days
- [ ] Re-scan after remediation
- [ ] Document scan results and remediation
- [ ] Archive passing scan reports

**Tools:**
- External: Qualys, Nessus, or ASV service
- Internal: `npm audit`, `pip-audit`, Snyk, Dependabot

### Security Incident Response

If a payment-related security incident occurs:

1. **Immediate Actions** (within 1 hour)
   - [ ] Isolate affected systems
   - [ ] Notify security team
   - [ ] Begin incident log

2. **Assessment** (within 4 hours)
   - [ ] Determine scope of incident
   - [ ] Identify if cardholder data compromised
   - [ ] Assess impact to users

3. **Notification** (within 24 hours if cardholder data compromised)
   - [ ] Notify LemonSqueezy
   - [ ] Notify affected users
   - [ ] Notify card brands (if applicable)
   - [ ] Notify regulatory authorities (if required)

4. **Remediation**
   - [ ] Apply security fixes
   - [ ] Verify systems secure
   - [ ] Monitor for additional issues

5. **Post-Incident**
   - [ ] Complete incident report
   - [ ] Update security policies
   - [ ] Conduct lessons learned review
   - [ ] Update incident response plan

---

## Incident Response

### Payment Security Incident Response Plan

#### Incident Classification

**Severity Levels:**

| Level | Description | Response Time | Examples |
|-------|-------------|---------------|----------|
| **P0 - Critical** | Active compromise, data breach | Immediate (< 1 hour) | Webhook signature bypass, unauthorized access to payment data |
| **P1 - High** | Security vulnerability, potential breach | 4 hours | API key exposure, authentication bypass |
| **P2 - Medium** | Suspicious activity, degraded security | 24 hours | Repeated webhook failures, unusual error rates |
| **P3 - Low** | Security concern, no immediate risk | 1 week | Outdated dependencies, minor configuration issues |

#### Incident Response Workflow

##### Phase 1: Detection & Triage (0-1 hour)

**Detection Sources:**
- Sentry alerts (payment errors, security exceptions)
- Webhook security monitor alerts
- Health check failures
- User reports
- Security scan findings

**Immediate Actions:**
1. **Acknowledge Alert**
   - Assign incident commander
   - Start incident log
   - Open incident channel (Slack, Teams)

2. **Assess Severity**
   - Determine incident classification (P0-P3)
   - Identify affected systems
   - Estimate impact (users, transactions)

3. **Initial Containment** (P0/P1 only)
   - Isolate affected systems if necessary
   - Block suspicious IP addresses
   - Disable compromised accounts
   - Enable emergency rate limiting

##### Phase 2: Investigation (1-4 hours)

**Data Collection:**
- [ ] Review audit logs (`src/services/audit_logger.py` output)
- [ ] Check Sentry error timeline
- [ ] Review webhook event logs
- [ ] Analyze application logs (structured logging)
- [ ] Check database for anomalies

**Key Questions:**
- Was cardholder data accessed or compromised?
- Were webhook signatures properly verified?
- Are API keys compromised?
- How many users affected?
- What is the timeline of the incident?

**LemonSqueezy Communication:**
- If cardholder data potentially compromised → **immediately contact LemonSqueezy support**
- If webhook issues → verify LemonSqueezy service status
- Request incident correlation from LemonSqueezy side

##### Phase 3: Containment & Eradication (4-24 hours)

**Containment Actions:**
- [ ] Apply security patches
- [ ] Rotate compromised API keys (see [API Key Rotation Guide](../security/API_KEY_ROTATION.md))
- [ ] Update webhook secrets if compromised
- [ ] Block malicious IPs/users
- [ ] Temporarily disable affected features if necessary

**Eradication Actions:**
- [ ] Fix root cause vulnerability
- [ ] Deploy security updates
- [ ] Verify webhook signature verification working
- [ ] Clear any malicious data

**Verification:**
- [ ] Re-run security scans
- [ ] Test affected functionality
- [ ] Verify monitoring and alerting functional
- [ ] Confirm no ongoing suspicious activity

##### Phase 4: Notification (As Required)

**Internal Notification:**
- [ ] Notify engineering leadership
- [ ] Notify product/business teams
- [ ] Update incident status regularly

**External Notification (if cardholder data compromised):**

⚠️ **CRITICAL:** If cardholder data was accessed or stolen, we are legally required to notify:

1. **LemonSqueezy** (immediately)
   - Contact: support@lemonsqueezy.com
   - Phone: [Emergency security hotline from LemonSqueezy dashboard]
   - Information needed: Incident timeline, scope, affected data

2. **Payment Card Brands** (within 72 hours)
   - LemonSqueezy will coordinate this as PCI DSS Level 1 provider
   - May require forensic investigation (PFI)

3. **Affected Users** (as required by law)
   - Timeline varies by jurisdiction (GDPR: 72 hours, US state laws vary)
   - Method: Email notification with details and remediation steps
   - Template: [User Breach Notification Template]

4. **Regulatory Authorities** (as required)
   - GDPR: Data Protection Authority (72 hours)
   - US: State attorneys general (varies by state)
   - Other jurisdictions as applicable

**User Notification Template:**

```
Subject: Important Security Notice - [Service Name]

Dear [User],

We are writing to inform you of a security incident that may have affected your account.

What Happened:
[Brief description of incident]

What Information Was Involved:
[Specific data types - be transparent]

What We're Doing:
- [Actions taken to secure systems]
- [Ongoing investigation]
- [Enhanced security measures]

What You Should Do:
- [Specific user actions, e.g., change password, monitor account]
- [Contact information for questions]

We take the security of your information very seriously and sincerely apologize for this incident.

Sincerely,
[Your Company] Security Team
```

##### Phase 5: Recovery (24-72 hours)

**System Recovery:**
- [ ] Restore normal operations
- [ ] Re-enable disabled features
- [ ] Monitor systems closely for 72 hours
- [ ] Conduct additional security scans

**Enhanced Monitoring:**
- [ ] Increase logging verbosity temporarily
- [ ] Set up additional alerts
- [ ] Manual log reviews daily for 1 week

##### Phase 6: Post-Incident Review (1 week after)

**Incident Report:**
- [ ] Complete timeline of events
- [ ] Root cause analysis
- [ ] Impact assessment (users, revenue, reputation)
- [ ] Lessons learned

**Process Improvements:**
- [ ] Update security policies
- [ ] Enhance monitoring/alerting
- [ ] Security training for team
- [ ] Update incident response plan
- [ ] Implement preventive measures

**Compliance:**
- [ ] Update SAQ A if needed
- [ ] Document for next audit
- [ ] Share findings with LemonSqueezy
- [ ] Retain incident documentation (7 years)

---

### Emergency Contacts

**Internal:**
- Security Lead: [security@wrext.com]
- Engineering Lead: [engineering@wrext.com]
- On-Call: [PagerDuty/on-call system]

**External:**
- LemonSqueezy Support: support@lemonsqueezy.com
- LemonSqueezy Security: security@lemonsqueezy.com
- Cloud Provider Security: [AWS/GCP/Azure security contact]

**Regulatory:**
- Data Protection Authority: [jurisdiction-specific]
- Payment Card Brands: [Coordinated through LemonSqueezy]

---

## Annual Review Process

### Review Schedule

**When:** October (annually)
**Owner:** Engineering Lead + Security Team
**Duration:** 1-2 weeks

### Review Checklist

#### 1. Documentation Review

- [ ] Review this PCI compliance document
- [ ] Update any changed processes or systems
- [ ] Verify all links and references current
- [ ] Update contact information
- [ ] Review and update incident response procedures

#### 2. LemonSqueezy Compliance Verification

- [ ] Obtain current LemonSqueezy AOC (Attestation of Compliance)
- [ ] Verify LemonSqueezy PCI DSS Level 1 status current
- [ ] Review LemonSqueezy security documentation for updates
- [ ] Confirm no changes to data handling practices

#### 3. System Audit

- [ ] Database audit - confirm no cardholder data stored
- [ ] Code review - verify no payment forms in codebase
- [ ] API integration audit - confirm hosted checkout still used
- [ ] Webhook payload audit - verify no cardholder data received
- [ ] Log audit - confirm no cardholder data in logs
- [ ] Backup audit - confirm no cardholder data in backups

#### 4. Security Controls Review

- [ ] Verify HTTPS/TLS configuration current
- [ ] Review authentication mechanisms
- [ ] Audit access controls and RBAC
- [ ] Review rate limiting effectiveness
- [ ] Verify webhook signature verification working
- [ ] Review audit logging coverage
- [ ] Test monitoring and alerting

#### 5. Vulnerability Assessment

- [ ] Run comprehensive vulnerability scan
- [ ] Review dependency vulnerabilities (`npm audit`, `pip-audit`)
- [ ] Review and remediate findings
- [ ] Document remediation plan for any issues

#### 6. Policy & Training

- [ ] Update information security policy
- [ ] Conduct security awareness training for developers
- [ ] Review incident response plan
- [ ] Test incident response procedures (tabletop exercise)

#### 7. SAQ A Completion

- [ ] Complete SAQ A questionnaire
- [ ] Collect supporting evidence
- [ ] Executive sign-off
- [ ] Archive completed SAQ A and evidence

#### 8. Compliance Documentation

- [ ] Compile annual compliance package
- [ ] Update compliance dashboard/tracker
- [ ] Schedule next year's review
- [ ] Distribute updated documentation to team

---

## References

### Internal Documentation

- [API Key Rotation Guide](../security/API_KEY_ROTATION.md)
- [Webhook Security Production](../security/WEBHOOK_SECURITY_PRODUCTION.md)
- [CSRF Protection Decision](../security/CSRF_PROTECTION_DECISION.md)
- [Field Encryption Decision](../security/FIELD_ENCRYPTION_DECISION.md)
- [Audit Logging Guide](../AUDIT_LOGGING.md)
- [Sentry Payment Monitoring](../monitoring/SENTRY_PAYMENT_MONITORING.md)
- [Sentry Alert Configuration](../monitoring/SENTRY_ALERT_CONFIGURATION.md)
- [Payment Alert Runbooks](../monitoring/PAYMENT_ALERT_RUNBOOKS.md)
- [Payment Logging Guide](../logging/PAYMENT_LOGGING.md)

### External Documentation

#### LemonSqueezy
- **Security Overview:** https://www.lemonsqueezy.com/security
- **Developer Docs:** https://docs.lemonsqueezy.com/
- **Webhook Security:** https://docs.lemonsqueezy.com/guides/developer-guide/webhooks#signing-requests
- **Checkout Security:** https://docs.lemonsqueezy.com/guides/developer-guide/checkout

#### PCI DSS
- **PCI SSC Website:** https://www.pcisecuritystandards.org/
- **SAQ A Questionnaire:** https://www.pcisecuritystandards.org/document_library
- **Quick Reference Guide:** https://www.pcisecuritystandards.org/pci_security/
- **ROC Reporting:** https://www.pcisecuritystandards.org/assessors_and_solutions/

#### Standards & Best Practices
- **OWASP Top 10:** https://owasp.org/www-project-top-ten/
- **NIST Cybersecurity Framework:** https://www.nist.gov/cyberframework
- **GDPR Compliance:** https://gdpr.eu/
- **AWS Security Best Practices:** https://aws.amazon.com/security/best-practices/
- **GCP Security Best Practices:** https://cloud.google.com/security/best-practices

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-10-20 | Engineering Team | Initial comprehensive PCI compliance documentation |

---

## Approval

**This document has been reviewed and approved for accuracy regarding WREXT's PCI DSS compliance posture.**

**Approved By:**
Engineering Lead: _________________ Date: _________
Security Lead: ___________________ Date: _________

**Next Review Date:** October 2026

---

**Document Classification:** Internal - Confidential
**Distribution:** Engineering, Security, Compliance, Leadership

---

## Questions or Concerns?

If you have questions about PCI compliance or notice any discrepancies in this document:

- **Email:** security@wrext.com
- **Slack:** #security or #engineering
- **Incident:** Follow incident response procedures above

**Remember:** When in doubt about payment security, always err on the side of caution and escalate to the security team.
