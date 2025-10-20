# LemonSqueezy API Key Rotation Guide

## Overview

This document provides comprehensive procedures for rotating LemonSqueezy API keys in the WREXT backend system. API key rotation is a critical security practice that limits the window of opportunity for compromised credentials.

---

## Table of Contents

1. [Why Rotate API Keys?](#why-rotate-api-keys)
2. [Rotation Schedule](#rotation-schedule)
3. [Current Key Storage Architecture](#current-key-storage-architecture)
4. [Production Key Storage Recommendations](#production-key-storage-recommendations)
5. [Pre-Rotation Checklist](#pre-rotation-checklist)
6. [Zero-Downtime Rotation Procedure](#zero-downtime-rotation-procedure)
7. [Emergency Rotation (Compromised Key)](#emergency-rotation-compromised-key)
8. [Rollback Procedures](#rollback-procedures)
9. [Testing & Validation](#testing--validation)
10. [Monitoring & Alerting](#monitoring--alerting)
11. [Troubleshooting](#troubleshooting)

---

## Why Rotate API Keys?

### Security Benefits

1. **Limit Exposure Window**: Compromised keys have limited lifetime
2. **Reduce Impact**: Regular rotation minimizes damage from undetected breaches
3. **Compliance**: Many standards (PCI-DSS, SOC 2, ISO 27001) require periodic key rotation
4. **Detect Anomalies**: Rotation helps identify unauthorized key usage
5. **Insider Threat Mitigation**: Limits risk from former employees or contractors

### Risk Assessment

| Risk Level | Rotation Frequency | Trigger Events |
|------------|-------------------|----------------|
| **High** | Every 30 days | Production key, high transaction volume |
| **Medium** | Every 90 days | Staging/test environments |
| **Low** | Every 180 days | Development environments |
| **EMERGENCY** | Immediately | Suspected compromise, employee departure, security incident |

---

## Rotation Schedule

### Recommended Schedule

- **Production API Keys**: Every 90 days (or as required by compliance)
- **Webhook Secrets**: Every 90 days (rotate with API keys)
- **Test/Sandbox Keys**: Every 180 days
- **Development Keys**: Every 180 days or on developer offboarding

### Calendar Reminders

Set recurring calendar events:
- **60 days before rotation**: Review procedure, identify stakeholders
- **30 days before rotation**: Schedule maintenance window
- **7 days before rotation**: Final preparation, backup verification
- **Rotation day**: Execute procedure
- **1 day after rotation**: Validation and monitoring

---

## Current Key Storage Architecture

### Environment Variables (Development)

**Location**: `.env` file in `wrext-backend/` directory

```bash
# LemonSqueezy Configuration
LEMONSQUEEZY_API_KEY=your_api_key_here
LEMONSQUEEZY_STORE_ID=your_store_id_here
LEMONSQUEEZY_WEBHOOK_SECRET=your_webhook_signing_secret
```

**Configuration Loading**: `src/config/payment_config.py`

```python
class PaymentSettings(BaseSettings):
    lemonsqueezy_api_key: str = ""
    lemonsqueezy_store_id: str = ""
    lemonsqueezy_webhook_secret: str = ""
```

**Usage**: `src/providers/payment/providers/lemonsqueezy.py:71-73`

```python
self.client = httpx.AsyncClient(
    base_url=self.BASE_URL,
    headers={
        "Authorization": f"Bearer {self.api_key}",
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
    }
)
```

### Security Limitations

**Current Risks**:
- ⚠️ `.env` files stored on filesystem (unencrypted at rest)
- ⚠️ Keys visible to anyone with server access
- ⚠️ No automatic rotation mechanism
- ⚠️ No key versioning or rollback capability
- ⚠️ Manual process prone to errors

**Acceptable For**: Development and small deployments
**Not Recommended For**: Production systems handling sensitive payment data

---

## Production Key Storage Recommendations

### Option 1: AWS Secrets Manager (Recommended for AWS)

**Benefits**:
- Automatic rotation support
- Encryption at rest (AWS KMS)
- Fine-grained IAM access control
- Audit logging via CloudTrail
- Version management with rollback

**Implementation**:

```python
# Install: pip install boto3

import boto3
from botocore.exceptions import ClientError

def get_lemonsqueezy_api_key():
    """Retrieve LemonSqueezy API key from AWS Secrets Manager"""
    secret_name = "production/lemonsqueezy/api-key"
    region_name = "us-east-1"

    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
        secret = json.loads(get_secret_value_response['SecretString'])
        return secret['LEMONSQUEEZY_API_KEY']
    except ClientError as e:
        logger.error(f"Failed to retrieve secret: {e}")
        raise
```

**Cost**: $0.40/secret/month + $0.05 per 10,000 API calls

### Option 2: HashiCorp Vault

**Benefits**:
- Dynamic secrets with automatic rotation
- Multi-cloud and on-premise support
- Advanced audit logging
- Secrets versioning
- Lease management

**Implementation**:

```python
# Install: pip install hvac

import hvac

def get_lemonsqueezy_api_key():
    """Retrieve LemonSqueezy API key from Vault"""
    client = hvac.Client(url='https://vault.yourdomain.com:8200')

    # Authenticate (use appropriate method)
    client.auth.approle.login(
        role_id=os.environ['VAULT_ROLE_ID'],
        secret_id=os.environ['VAULT_SECRET_ID']
    )

    # Read secret
    secret = client.secrets.kv.v2.read_secret_version(
        path='lemonsqueezy/production'
    )

    return secret['data']['data']['api_key']
```

**Cost**: Open-source (self-hosted) or $0.03/hour for HCP Vault

### Option 3: Google Cloud Secret Manager

**Benefits**:
- Native GCP integration
- Automatic encryption
- IAM-based access control
- Audit logging
- Global replication

**Implementation**:

```python
# Install: pip install google-cloud-secret-manager

from google.cloud import secretmanager

def get_lemonsqueezy_api_key():
    """Retrieve LemonSqueezy API key from GCP Secret Manager"""
    client = secretmanager.SecretManagerServiceClient()

    name = "projects/YOUR_PROJECT/secrets/lemonsqueezy-api-key/versions/latest"

    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode('UTF-8')
```

**Cost**: $0.06/10,000 access operations

### Option 4: Azure Key Vault

**Benefits**:
- Azure-native integration
- HSM-backed key storage option
- RBAC access control
- Activity logging
- Soft-delete protection

**Implementation**:

```python
# Install: pip install azure-keyvault-secrets azure-identity

from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

def get_lemonsqueezy_api_key():
    """Retrieve LemonSqueezy API key from Azure Key Vault"""
    vault_url = "https://YOUR_VAULT.vault.azure.net/"

    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=vault_url, credential=credential)

    secret = client.get_secret("lemonsqueezy-api-key")
    return secret.value
```

**Cost**: $0.03/10,000 operations

### Comparison Matrix

| Feature | AWS Secrets Manager | HashiCorp Vault | GCP Secret Manager | Azure Key Vault |
|---------|-------------------|-----------------|-------------------|-----------------|
| **Automatic Rotation** | ✅ Native | ✅ Advanced | ⚠️ Manual | ⚠️ Manual |
| **Encryption at Rest** | ✅ KMS | ✅ Transit+Rest | ✅ Native | ✅ Native |
| **Audit Logging** | ✅ CloudTrail | ✅ Detailed | ✅ Cloud Logging | ✅ Monitor |
| **Versioning** | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| **Multi-Cloud** | ❌ AWS only | ✅ Yes | ❌ GCP only | ❌ Azure only |
| **Cost (monthly)** | ~$0.40 | Variable | ~$0.18 | ~$0.90 |
| **Setup Complexity** | Low | Medium | Low | Low |

**Recommendation**: For AWS deployments, use **AWS Secrets Manager**. For multi-cloud or on-premise, use **HashiCorp Vault**.

---

## Pre-Rotation Checklist

### 1. Communication

- [ ] Notify engineering team (minimum 7 days notice)
- [ ] Schedule maintenance window (off-peak hours recommended)
- [ ] Prepare rollback team (at least 2 engineers on-call)
- [ ] Document current key metadata (creation date, name, last rotation)

### 2. Backup & Documentation

- [ ] Backup current `.env` file: `cp .env .env.backup.$(date +%Y%m%d)`
- [ ] Document current key ID/name in LemonSqueezy dashboard
- [ ] Export current configuration: `env | grep LEMONSQUEEZY > keys-backup-$(date +%Y%m%d).txt`
- [ ] Verify backup integrity: `cat keys-backup-*.txt`

### 3. Environment Verification

- [ ] Confirm production environment is healthy
- [ ] Check recent error rates in Sentry
- [ ] Verify webhook processing is working: Check recent webhook logs
- [ ] Run health check: `curl https://api.yourdomain.com/health`

### 4. Access & Permissions

- [ ] Verify LemonSqueezy dashboard access (admin permissions required)
- [ ] Confirm server/container access (SSH, kubectl, etc.)
- [ ] Test deployment pipeline (CI/CD)
- [ ] Verify secrets management system access (AWS, Vault, etc.)

### 5. Testing Environment

- [ ] Test rotation procedure in staging environment first
- [ ] Validate zero-downtime approach works
- [ ] Document any issues encountered
- [ ] Time the procedure (expect 15-30 minutes)

---

## Zero-Downtime Rotation Procedure

### Architecture: Graceful Key Transition

The procedure uses a **dual-key approach** during transition:
1. New key deployed alongside old key
2. Application updated to use new key
3. Old key verified as unused
4. Old key deleted

### Step-by-Step Process

#### Phase 1: Generate New Key (Duration: 5 minutes)

**1.1. Access LemonSqueezy Dashboard**

```bash
# Open browser to LemonSqueezy API settings
# https://app.lemonsqueezy.com/settings/api
```

**1.2. Create New API Key**

1. Click **"Create API Key"**
2. Name: `wrext-production-YYYYMMDD` (e.g., `wrext-production-20250115`)
   - Naming convention ensures easy identification
   - Date suffix tracks rotation schedule
3. **IMPORTANT**: Copy the key immediately (only shown once)
4. Store temporarily in secure location (password manager)

**Example Key Name History**:
```
wrext-production-20241015  ← Old key (to be deleted)
wrext-production-20250115  ← New key (just created)
```

**1.3. Verify Key Permissions**

Test the new key before deploying:

```bash
# Test API key validity
curl -X GET 'https://api.lemonsqueezy.com/v1/users/me' \
  -H 'Accept: application/vnd.api+json' \
  -H 'Authorization: Bearer YOUR_NEW_API_KEY'

# Expected response: 200 OK with user data
# If 401 Unauthorized: Key is invalid, regenerate
```

#### Phase 2: Update Production Configuration (Duration: 10 minutes)

**Option A: Direct .env Update (Development/Small Deployments)**

```bash
# SSH into production server
ssh user@production-server

# Backup current configuration
cd /path/to/wrext-backend
cp .env .env.backup.$(date +%Y%m%d-%H%M%S)

# Update .env with new key
nano .env
# Replace: LEMONSQUEEZY_API_KEY=old_key_here
# With:    LEMONSQUEEZY_API_KEY=new_key_here

# Restart application (depends on deployment method)
# Option 1: systemd
sudo systemctl restart wrext-backend

# Option 2: Docker
docker-compose restart backend

# Option 3: Kubernetes
kubectl rollout restart deployment/wrext-backend -n production
```

**Option B: Secrets Manager Update (Production)**

**AWS Secrets Manager**:

```bash
# Update secret value
aws secretsmanager update-secret \
  --secret-id production/lemonsqueezy/api-key \
  --secret-string '{"LEMONSQUEEZY_API_KEY":"NEW_KEY_HERE","LEMONSQUEEZY_STORE_ID":"STORE_ID","LEMONSQUEEZY_WEBHOOK_SECRET":"WEBHOOK_SECRET"}' \
  --region us-east-1

# Verify update
aws secretsmanager get-secret-value \
  --secret-id production/lemonsqueezy/api-key \
  --region us-east-1 \
  --query 'SecretString' \
  --output text | jq .

# Force pod restart to pick up new secret (Kubernetes)
kubectl rollout restart deployment/wrext-backend -n production

# Monitor rollout
kubectl rollout status deployment/wrext-backend -n production
```

**HashiCorp Vault**:

```bash
# Update secret
vault kv put secret/lemonsqueezy/production \
  api_key=NEW_KEY_HERE \
  store_id=STORE_ID \
  webhook_secret=WEBHOOK_SECRET

# Verify
vault kv get secret/lemonsqueezy/production

# Restart application
kubectl rollout restart deployment/wrext-backend -n production
```

#### Phase 3: Validation (Duration: 10 minutes)

**3.1. Health Checks**

```bash
# Check application health
curl https://api.yourdomain.com/health

# Expected: 200 OK
```

**3.2. Functional Testing**

```bash
# Test checkout creation (replace with actual values)
curl -X POST https://api.yourdomain.com/api/v1/subscriptions/checkout \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "variant_id": "123456",
    "success_url": "https://yourdomain.com/success",
    "cancel_url": "https://yourdomain.com/cancel"
  }'

# Expected: 200 OK with checkout URL
```

**3.3. Monitor Logs**

```bash
# Check application logs for errors
# Docker:
docker logs -f wrext-backend --tail 100

# Kubernetes:
kubectl logs -f deployment/wrext-backend -n production --tail=100

# Look for:
# ✅ "LemonSqueezyProvider initialized"
# ✅ Successful API requests
# ❌ 401 Unauthorized errors (indicates key issue)
```

**3.4. Sentry Error Monitoring**

```bash
# Check Sentry dashboard for new errors
# https://sentry.io/organizations/YOUR_ORG/issues/

# Filter by:
# - Last 1 hour
# - Tag: component=lemonsqueezy
# - Search: "LemonSqueezy" OR "401" OR "Unauthorized"
```

**3.5. Webhook Testing**

Trigger a test webhook event:

1. Create test subscription in LemonSqueezy (test mode)
2. Monitor webhook endpoint logs
3. Verify signature verification passes

```bash
# Check webhook logs
grep "webhook_verification" /var/log/wrext-backend/app.log | tail -20

# Expected:
# ✅ "LemonSqueezy webhook signature verified successfully"
# ❌ "SECURITY: LemonSqueezy webhook signature verification FAILED"
```

#### Phase 4: Cleanup (Duration: 5 minutes)

**4.1. Wait Period**

⏱️ **IMPORTANT**: Wait at least 24 hours before deleting old key

**Reason**:
- Cached credentials may still be in use
- Load balancers may have old configuration
- Background jobs might still use old key

**4.2. Monitor Old Key Usage**

LemonSqueezy dashboard shows last usage timestamp for each key.

1. Navigate to **Settings » API**
2. Find old key: `wrext-production-20241015`
3. Check **"Last Used"** timestamp
4. If timestamp hasn't updated in 24+ hours → Safe to delete

**4.3. Delete Old Key**

```bash
# In LemonSqueezy dashboard:
# Settings » API » [Old Key] » Delete

# Confirm deletion
# Note: This action is irreversible
```

**4.4. Update Documentation**

```bash
# Update rotation log
echo "$(date +%Y-%m-%d): Rotated LemonSqueezy API key (old: wrext-production-20241015, new: wrext-production-20250115)" >> docs/security/rotation-log.txt

# Update team wiki/documentation
# Record: rotation date, key name, engineer who performed rotation
```

**4.5. Cleanup Backups (After 90 Days)**

```bash
# Remove old backup files after retention period
find . -name ".env.backup.*" -mtime +90 -delete
find . -name "keys-backup-*.txt" -mtime +90 -delete
```

---

## Emergency Rotation (Compromised Key)

### When to Perform Emergency Rotation

**IMMEDIATELY** if any of these occur:
- Key committed to version control (GitHub, GitLab, etc.)
- Key exposed in logs or error messages
- Suspicious API usage detected (unexpected charges, regions, IP addresses)
- Employee/contractor with key access leaves company
- Security incident or breach
- Key accidentally shared (email, Slack, chat)

### Emergency Procedure (15-Minute Response)

**1. Disable Old Key (1 minute)**

```bash
# LemonSqueezy Dashboard:
# Settings » API » [Compromised Key] » Delete
# DO THIS FIRST - Stop the bleeding
```

**2. Generate New Key (1 minute)**

```bash
# Settings » API » Create API Key
# Name: wrext-production-emergency-YYYYMMDD
# Copy key immediately
```

**3. Deploy New Key (5 minutes)**

```bash
# Update production configuration (choose fastest method)
# AWS Secrets Manager (recommended):
aws secretsmanager update-secret \
  --secret-id production/lemonsqueezy/api-key \
  --secret-string '{"LEMONSQUEEZY_API_KEY":"NEW_KEY"}' \
  --region us-east-1

# Restart application immediately
kubectl rollout restart deployment/wrext-backend -n production

# Monitor restart
kubectl rollout status deployment/wrext-backend -n production --timeout=2m
```

**4. Verify Recovery (3 minutes)**

```bash
# Test API functionality
curl https://api.yourdomain.com/health

# Check error rate in Sentry
# Ensure no 401 errors
```

**5. Incident Response (5 minutes)**

```bash
# Document incident
echo "EMERGENCY ROTATION - $(date)" >> docs/security/incident-log.txt
echo "Reason: [DESCRIBE COMPROMISE]" >> docs/security/incident-log.txt
echo "Old Key: [KEY_NAME]" >> docs/security/incident-log.txt
echo "New Key: [NEW_KEY_NAME]" >> docs/security/incident-log.txt

# Notify stakeholders
# - Engineering team
# - Security team
# - Management (if financial impact)

# If key was in version control:
git filter-repo --path .env --invert-paths  # Remove from history
# OR use: BFG Repo-Cleaner, git-secrets, truffleHog
```

**6. Post-Incident Analysis**

- Review logs for unauthorized API usage
- Check LemonSqueezy transaction history
- Assess financial impact
- Update security procedures to prevent recurrence
- Consider implementing: git hooks, secrets scanning, pre-commit checks

---

## Rollback Procedures

### When to Rollback

Rollback to previous key if:
- New key causes authentication errors
- Webhook verification starts failing
- Production payment processing breaks
- Errors spike in Sentry

### Quick Rollback Steps (5 Minutes)

**1. Restore Backup Configuration**

```bash
# SSH into production
ssh user@production-server

cd /path/to/wrext-backend

# List backups
ls -lah .env.backup.*

# Restore most recent backup
cp .env.backup.YYYYMMDD-HHMMSS .env

# Verify restoration
grep LEMONSQUEEZY_API_KEY .env
```

**2. Restart Application**

```bash
# systemd
sudo systemctl restart wrext-backend

# Docker
docker-compose restart backend

# Kubernetes
kubectl rollout restart deployment/wrext-backend -n production
kubectl rollout status deployment/wrext-backend -n production
```

**3. Verify Service Recovery**

```bash
# Health check
curl https://api.yourdomain.com/health

# Check logs for successful initialization
docker logs wrext-backend --tail 50 | grep "LemonSqueezyProvider initialized"

# Monitor error rate
# Should return to baseline within 1-2 minutes
```

**4. Post-Rollback Actions**

```bash
# Document rollback
echo "ROLLBACK - $(date): Reverted to backup from [DATE]. Reason: [REASON]" >> docs/security/rotation-log.txt

# Keep new key in LemonSqueezy dashboard
# DON'T delete it yet - investigate why it failed

# Schedule post-mortem
# Root cause analysis
# Update procedures based on learnings
```

---

## Testing & Validation

### Pre-Production Testing

**Test in Staging Environment First**

```bash
# 1. Create test API key in LemonSqueezy (Test Mode)
# Name: wrext-staging-test-YYYYMMDD

# 2. Update staging .env
LEMONSQUEEZY_API_KEY=test_key_here
LEMONSQUEEZY_STORE_ID=test_store_id

# 3. Restart staging application
docker-compose restart backend

# 4. Run integration tests
cd wrext-backend
source .venv/bin/activate
pytest tests/integration/test_lemonsqueezy_integration.py -v

# Expected: All tests pass
```

### Automated Validation Script

Create `scripts/validate_lemonsqueezy_key.py`:

```python
#!/usr/bin/env python3
"""
LemonSqueezy API Key Validation Script

Usage:
    python scripts/validate_lemonsqueezy_key.py

Environment Variables:
    LEMONSQUEEZY_API_KEY - API key to validate
"""

import os
import sys
import httpx
from datetime import datetime


def validate_api_key(api_key: str) -> bool:
    """Validate LemonSqueezy API key"""
    print(f"🔍 Validating LemonSqueezy API key...")
    print(f"   Key prefix: {api_key[:12]}...")

    try:
        response = httpx.get(
            "https://api.lemonsqueezy.com/v1/users/me",
            headers={
                "Accept": "application/vnd.api+json",
                "Authorization": f"Bearer {api_key}"
            },
            timeout=10.0
        )

        if response.status_code == 200:
            data = response.json()
            user_name = data.get("data", {}).get("attributes", {}).get("name", "Unknown")
            user_email = data.get("data", {}).get("attributes", {}).get("email", "Unknown")

            print(f"✅ API key is VALID")
            print(f"   Authenticated as: {user_name} ({user_email})")
            print(f"   Timestamp: {datetime.now().isoformat()}")
            return True

        elif response.status_code == 401:
            print(f"❌ API key is INVALID")
            print(f"   Error: 401 Unauthorized")
            print(f"   The key may be revoked, expired, or incorrectly formatted")
            return False

        else:
            print(f"⚠️  Unexpected response: {response.status_code}")
            print(f"   Response: {response.text}")
            return False

    except httpx.HTTPError as e:
        print(f"❌ HTTP Error: {e}")
        return False
    except Exception as e:
        print(f"❌ Validation failed: {e}")
        return False


def main():
    api_key = os.getenv("LEMONSQUEEZY_API_KEY")

    if not api_key:
        print("❌ Error: LEMONSQUEEZY_API_KEY environment variable not set")
        print("   Usage: LEMONSQUEEZY_API_KEY=your_key python scripts/validate_lemonsqueezy_key.py")
        sys.exit(1)

    if len(api_key) < 20:
        print(f"⚠️  Warning: API key seems too short ({len(api_key)} chars)")
        print("   LemonSqueezy keys are typically 40+ characters")

    is_valid = validate_api_key(api_key)

    if is_valid:
        print("\n✅ Validation successful - Key is ready for use")
        sys.exit(0)
    else:
        print("\n❌ Validation failed - Do not deploy this key")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

**Usage**:

```bash
# Make executable
chmod +x scripts/validate_lemonsqueezy_key.py

# Test new key before deployment
export LEMONSQUEEZY_API_KEY="your_new_key_here"
python scripts/validate_lemonsqueezy_key.py

# Expected output:
# 🔍 Validating LemonSqueezy API key...
#    Key prefix: eyJhbGciOiJI...
# ✅ API key is VALID
#    Authenticated as: Your Name (you@example.com)
```

### Validation Checklist

After rotation, verify:

- [ ] Health endpoint returns 200 OK
- [ ] Can create checkout session
- [ ] Can retrieve subscription data
- [ ] Can update subscription
- [ ] Can cancel subscription
- [ ] Customer portal URL generation works
- [ ] Webhook signature verification passes
- [ ] No 401 errors in logs (check last 1 hour)
- [ ] Sentry error rate unchanged
- [ ] Payment processing test transaction succeeds

---

## Monitoring & Alerting

### Key Performance Indicators (KPIs)

Monitor these metrics during and after rotation:

1. **API Error Rate**
   - Baseline: < 0.1% error rate
   - During rotation: May spike briefly (< 1 minute)
   - Post-rotation: Should return to baseline within 5 minutes

2. **Authentication Failures (401 errors)**
   - Baseline: 0 per hour
   - During rotation: May see 1-5 failures during transition
   - Post-rotation: Should be 0

3. **Webhook Verification Failures**
   - Baseline: 0-1 per day (occasional LemonSqueezy test webhooks)
   - Post-rotation: Should remain unchanged

4. **Response Time**
   - Baseline: p95 < 500ms for API calls
   - Post-rotation: Should remain unchanged (API key doesn't affect latency)

### Sentry Alert Configuration

**Create Alert Rule: "LemonSqueezy API Authentication Failure"**

```yaml
# Alert when: LemonSqueezy 401 errors occur
Filter:
  - error.type: "LemonSqueezyAPIError"
  - error.status_code: 401

Conditions:
  - Number of events: > 5 in 5 minutes

Actions:
  - Send notification to: #payments-alerts (Slack)
  - Email: ops-team@yourdomain.com
  - PagerDuty: P1 incident (if > 20 errors in 5 min)
```

### CloudWatch/Logging Queries

**AWS CloudWatch Insights Query**:

```sql
fields @timestamp, @message
| filter @message like /LemonSqueezy.*401/
    or @message like /webhook_verification_failed/
    or @message like /LemonSqueezyAPIError/
| sort @timestamp desc
| limit 100
```

**Monitor During Rotation**:

```bash
# Real-time log monitoring
aws logs tail /aws/ecs/wrext-backend --follow --format short \
  --filter-pattern "LemonSqueezy"

# Count authentication errors
aws logs filter-log-events \
  --log-group-name /aws/ecs/wrext-backend \
  --start-time $(date -u -d '1 hour ago' +%s)000 \
  --filter-pattern '"401"' \
  | jq '.events | length'
```

### Grafana Dashboard

Create dashboard with panels:

1. **LemonSqueezy API Calls (last 24h)**
   - Success count (200 responses)
   - Error count (4xx, 5xx)
   - Error rate percentage

2. **Authentication Errors**
   - 401 count per hour
   - Alert threshold line at 5 errors/hour

3. **Webhook Processing**
   - Webhooks received
   - Signature verification success rate
   - Verification failures

4. **API Response Times**
   - p50, p95, p99 latencies
   - By endpoint (checkout, subscription, cancel)

---

## Troubleshooting

### Common Issues

#### Issue 1: 401 Unauthorized After Rotation

**Symptoms**:
```
LemonSqueezyAPIError (401): Unauthorized
```

**Causes**:
- New key not properly updated in environment
- Application not restarted after key change
- Key copied incorrectly (whitespace, truncation)
- Old cached credentials still in use

**Diagnosis**:

```bash
# Check current environment variable
echo $LEMONSQUEEZY_API_KEY

# Check .env file
grep LEMONSQUEEZY_API_KEY /path/to/wrext-backend/.env

# Verify key with validation script
python scripts/validate_lemonsqueezy_key.py

# Check application logs
docker logs wrext-backend | grep "LemonSqueezyProvider initialized"
```

**Resolution**:

```bash
# 1. Verify key in .env is correct (no extra spaces/newlines)
cat -A .env | grep LEMONSQUEEZY_API_KEY
# Should show: LEMONSQUEEZY_API_KEY=key_here$
# Should NOT show: LEMONSQUEEZY_API_KEY=key_here $  (trailing space)

# 2. Restart application completely
docker-compose down
docker-compose up -d

# 3. If still failing, rollback to previous key
cp .env.backup.YYYYMMDD .env
docker-compose restart backend
```

#### Issue 2: Webhook Signature Verification Failures

**Symptoms**:
```
SECURITY: LemonSqueezy webhook signature verification FAILED
```

**Causes**:
- Webhook secret not rotated along with API key
- Webhook secret mismatch between LemonSqueezy dashboard and application
- Old webhook secret still cached

**Diagnosis**:

```bash
# Check webhook secret in environment
grep LEMONSQUEEZY_WEBHOOK_SECRET .env

# Check webhook configuration in LemonSqueezy dashboard
# Settings » Webhooks » [Your Webhook] » Signing Secret

# Check recent webhook logs
grep "webhook_verification" /var/log/wrext-backend/app.log | tail -20
```

**Resolution**:

```bash
# 1. Get webhook secret from LemonSqueezy dashboard
# Settings » Webhooks » [Your Webhook] » Signing Secret » Regenerate

# 2. Update .env
nano .env
# Update: LEMONSQUEEZY_WEBHOOK_SECRET=new_secret_here

# 3. Restart application
docker-compose restart backend

# 4. Test webhook
# Trigger test webhook from LemonSqueezy dashboard
# Verify signature verification passes
```

#### Issue 3: "Key Not Found" After Rotation

**Symptoms**:
- Old key deleted too quickly
- Some services still using old key

**Causes**:
- Load balancer cached old configuration
- Background workers not restarted
- Multi-region deployment with delayed propagation

**Diagnosis**:

```bash
# Check if multiple instances are running
docker ps | grep wrext-backend

# Check load balancer targets
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:...

# Check Kubernetes pod status
kubectl get pods -n production -l app=wrext-backend
```

**Resolution**:

```bash
# Rolling restart of all instances
kubectl rollout restart deployment/wrext-backend -n production

# Verify all pods are using new configuration
kubectl get pods -n production -l app=wrext-backend -o jsonpath='{.items[*].metadata.name}' | xargs -I {} kubectl logs {} | grep "LemonSqueezyProvider initialized"

# If issue persists, temporarily restore old key in LemonSqueezy
# (Settings » API » Create with same key if possible - not supported)
# Otherwise, rollback to backup .env
```

#### Issue 4: Application Won't Start After Rotation

**Symptoms**:
```
RuntimeError: LEMONSQUEEZY_WEBHOOK_SECRET is not configured
```

**Causes**:
- Validation check in `src/api/server.py:123-136` failing
- Environment variable not set
- Production mode enabled with empty secret

**Diagnosis**:

```bash
# Check environment mode
grep ENVIRONMENT .env

# Check all LemonSqueezy variables
grep LEMONSQUEEZY .env

# Check startup validation logs
docker logs wrext-backend 2>&1 | grep "CRITICAL"
```

**Resolution**:

```bash
# Ensure all required variables are set
cat >> .env << EOF
LEMONSQUEEZY_API_KEY=your_key_here
LEMONSQUEEZY_STORE_ID=your_store_id_here
LEMONSQUEEZY_WEBHOOK_SECRET=your_webhook_secret_here
EOF

# Restart application
docker-compose up -d

# Verify startup
docker logs -f wrext-backend
# Look for: "✅ LemonSqueezy webhook secret configured"
```

### Escalation Procedures

**Level 1: Self-Resolution (0-15 minutes)**
- Check this troubleshooting guide
- Review logs and error messages
- Attempt rollback to previous configuration

**Level 2: Team Support (15-30 minutes)**
- Contact on-call engineer
- Share: error logs, steps taken, current state
- Collaborate on diagnosis

**Level 3: Vendor Support (30+ minutes)**
- Contact LemonSqueezy support: https://app.lemonsqueezy.com/support
- Provide: Store ID, approximate time of issue, error messages
- Request: Key validation, webhook configuration review

**Level 4: Emergency Mitigation (Critical Production Impact)**
- Enable maintenance mode
- Rollback to last known good configuration
- Disable payment processing temporarily
- Communicate with customers via status page

---

## Appendix

### A. Key Rotation Log Template

Create `docs/security/rotation-log.txt`:

```
# LemonSqueezy API Key Rotation Log
# Format: [Date] - [Old Key Name] → [New Key Name] - [Engineer] - [Notes]

2025-01-15 - wrext-production-20241015 → wrext-production-20250115 - Jane Doe - Scheduled rotation, no issues
2024-10-15 - wrext-production-20240715 → wrext-production-20241015 - John Smith - Scheduled rotation
2024-07-20 - wrext-production-20240415 → wrext-production-20240720 - Jane Doe - EMERGENCY: Key exposed in logs
```

### B. Pre-Commit Hook to Prevent Key Commits

Create `.git/hooks/pre-commit`:

```bash
#!/bin/bash
# Pre-commit hook to prevent LemonSqueezy key commits

if git diff --cached --name-only | grep -qE '\.env$'; then
    echo "❌ ERROR: Attempting to commit .env file"
    echo "   This file contains secrets and should never be committed"
    echo "   Add .env to .gitignore"
    exit 1
fi

# Check for LemonSqueezy keys in staged files
if git diff --cached | grep -qE 'LEMONSQUEEZY_API_KEY.*=.*[^"]'; then
    echo "❌ ERROR: LemonSqueezy API key detected in commit"
    echo "   Remove the key before committing"
    exit 1
fi

exit 0
```

Make executable:
```bash
chmod +x .git/hooks/pre-commit
```

### C. Automated Rotation Reminder Script

Create `scripts/check_key_rotation_schedule.py`:

```python
#!/usr/bin/env python3
"""
Check if LemonSqueezy API key rotation is due

Sends alert if key is older than rotation policy (90 days)
"""

import os
from datetime import datetime, timedelta

ROTATION_POLICY_DAYS = 90
LAST_ROTATION_FILE = "docs/security/.last-rotation"


def check_rotation_due():
    if not os.path.exists(LAST_ROTATION_FILE):
        print("⚠️  No rotation history found. Run initial rotation.")
        return True

    with open(LAST_ROTATION_FILE) as f:
        last_rotation_str = f.read().strip()

    last_rotation = datetime.fromisoformat(last_rotation_str)
    days_since_rotation = (datetime.now() - last_rotation).days
    days_until_due = ROTATION_POLICY_DAYS - days_since_rotation

    print(f"Last rotation: {last_rotation.strftime('%Y-%m-%d')}")
    print(f"Days since rotation: {days_since_rotation}")
    print(f"Days until next rotation: {days_until_due}")

    if days_until_due <= 0:
        print("🚨 ROTATION OVERDUE - Perform rotation immediately")
        return True
    elif days_until_due <= 7:
        print("⚠️  ROTATION DUE SOON - Schedule rotation this week")
        return True
    elif days_until_due <= 30:
        print("📅 Rotation due in ~1 month - Start planning")
        return False
    else:
        print("✅ No action required")
        return False


if __name__ == "__main__":
    check_rotation_due()
```

Add to cron:
```bash
# Check rotation schedule weekly
0 9 * * 1 cd /path/to/wrext-backend && python scripts/check_key_rotation_schedule.py | mail -s "LemonSqueezy Key Rotation Check" ops-team@yourdomain.com
```

### D. References

- [LemonSqueezy API Documentation](https://docs.lemonsqueezy.com/api)
- [LemonSqueezy Security Best Practices](https://docs.lemonsqueezy.com/guides/developer-guide/getting-started)
- [OWASP API Security Top 10](https://owasp.org/www-project-api-security/)
- [AWS Secrets Manager Documentation](https://docs.aws.amazon.com/secretsmanager/)
- [HashiCorp Vault Documentation](https://www.vaultproject.io/docs)

---

**Document Version**: 1.0
**Last Updated**: 2025-01-15
**Next Review**: 2025-04-15
**Owner**: Security Team / DevOps Team
