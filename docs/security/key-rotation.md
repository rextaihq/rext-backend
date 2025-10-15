# JWT Secret Key Management & Rotation

**Last Updated:** October 15, 2025
**Owner:** Backend Security Team
**Status:** Active Policy

---

## Overview

This document describes the security policy and procedures for managing JWT secret keys used for access and refresh token signing in the WREXT backend application.

## Key Requirements

### Security Standards

- **Minimum Length:** 32 characters (64+ characters recommended for production)
- **Randomness:** Must be cryptographically secure (use `secrets.token_urlsafe()`)
- **Uniqueness:** `SECRET_KEY` and `REFRESH_SECRET_KEY` must be different
- **Separation:** Different keys for development, staging, and production environments
- **Storage:** Store in `.env` file (never commit to version control)

### Validation

The application enforces these requirements at startup:
- Keys must be at least 32 characters
- Keys cannot be common placeholder values (`your-secret-key-here`, `changeme`, etc.)
- Application will fail to start if validation fails

## Generating New Keys

### Using the Generation Script (Recommended)

```bash
cd wrext-backend
python scripts/generate_jwt_secret.py
```

This will output two cryptographically secure keys:
```
SECRET_KEY=<64-character-random-string>
REFRESH_SECRET_KEY=<64-character-random-string>
```

Copy these values to your `.env` file.

### Manual Generation (Alternative)

If you prefer to generate keys manually:

```python
import secrets
print(secrets.token_urlsafe(64))  # For SECRET_KEY
print(secrets.token_urlsafe(64))  # For REFRESH_SECRET_KEY
```

## Key Rotation Strategy

### When to Rotate Keys

**Immediate Rotation Required:**
- Key compromise suspected or confirmed
- Unauthorized access detected
- Employee with key access leaves the organization
- Key accidentally committed to version control
- Security audit recommendation

**Scheduled Rotation:**
- Production: Every 90 days (quarterly)
- Staging: Every 180 days (biannually)
- Development: As needed (minimum annually)

### Rotation Procedure

#### 1. Pre-Rotation Preparation

```bash
# Generate new keys
python scripts/generate_jwt_secret.py

# Save output to secure location (password manager)
# Example output:
# NEW_SECRET_KEY=<new-key-1>
# NEW_REFRESH_SECRET_KEY=<new-key-2>
```

#### 2. Plan Deployment Window

- **Production:** Schedule during low-traffic period (e.g., 2-4 AM)
- **Expected Impact:** All active sessions will be invalidated
- **User Impact:** Users will need to re-authenticate
- **Duration:** ~5 minutes downtime
- **Rollback Plan:** Keep old keys available for 24 hours

#### 3. Update Environment Variables

**Production (recommended approach):**

```bash
# Option A: Use your secrets manager (AWS Secrets Manager, Vault, etc.)
aws secretsmanager update-secret \
  --secret-id wrext/prod/SECRET_KEY \
  --secret-string "<NEW_SECRET_KEY>"

aws secretsmanager update-secret \
  --secret-id wrext/prod/REFRESH_SECRET_KEY \
  --secret-string "<NEW_REFRESH_SECRET_KEY>"

# Option B: Update .env file directly (if not using secrets manager)
# SSH into production server
ssh production-server
cd /path/to/wrext-backend

# Backup current .env
cp .env .env.backup.$(date +%Y%m%d)

# Update keys in .env
nano .env
# Replace SECRET_KEY and REFRESH_SECRET_KEY with new values
```

**Staging:**

```bash
# Update staging .env
ssh staging-server
cd /path/to/wrext-backend
cp .env .env.backup.$(date +%Y%m%d)
nano .env
# Update SECRET_KEY and REFRESH_SECRET_KEY
```

**Development:**

```bash
# Update local .env
cd wrext-backend
cp .env .env.backup
nano .env
# Update SECRET_KEY and REFRESH_SECRET_KEY
```

#### 4. Restart Application

```bash
# Production (example using systemd)
sudo systemctl restart wrext-backend

# Or using Docker
docker-compose restart backend

# Or using PM2
pm2 restart wrext-backend

# Verify application started successfully
curl http://localhost:8000/health
# Should return: {"status": "healthy"}
```

#### 5. Verify Rotation

```bash
# Test new token generation
curl -X POST http://localhost:8000/api/user/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "testpass"}'

# Should return new JWT tokens
# Old tokens should no longer work

# Test with old token (should fail)
curl -X GET http://localhost:8000/api/user/profile \
  -H "Authorization: Bearer <OLD_TOKEN>"
# Should return: 401 Unauthorized
```

#### 6. Monitor for Issues

- Check application logs for authentication errors
- Monitor Sentry/error tracking for JWT-related issues
- Watch user support channels for login complaints
- Verify no impact to automated integrations

#### 7. Clean Up

```bash
# After 24 hours of successful operation, delete old key backups
rm .env.backup.*

# Update documentation with rotation date
echo "Last rotation: $(date)" >> docs/security/rotation-log.md
```

## Emergency Rotation (Key Compromise)

If keys are compromised, follow this expedited procedure:

### 1. Immediate Actions (within 1 hour)

```bash
# Generate new keys immediately
python scripts/generate_jwt_secret.py

# Update production .env
ssh production-server
cd /path/to/wrext-backend
nano .env  # Replace keys

# Restart application
sudo systemctl restart wrext-backend

# Blacklist all existing tokens (database operation)
psql -d wrext_db -c "UPDATE token_blacklist SET is_active = false;"
```

### 2. Communication

- Notify all users via email about forced logout
- Post status update on status page
- Alert security team and management
- Document incident in security log

### 3. Post-Incident

- Investigate how compromise occurred
- Review access logs
- Update security procedures
- Consider additional monitoring

## Key Storage Best Practices

### DO

✅ Store keys in `.env` file
✅ Add `.env` to `.gitignore`
✅ Use secrets management service (AWS Secrets Manager, HashiCorp Vault)
✅ Encrypt backups of `.env` files
✅ Use different keys per environment
✅ Document key rotation dates
✅ Limit access to production keys (need-to-know basis)

### DON'T

❌ Commit keys to version control (git)
❌ Share keys via email, Slack, or unencrypted channels
❌ Use the same keys for dev/staging/production
❌ Use weak or predictable keys
❌ Store keys in application code
❌ Log keys in application logs
❌ Share keys with third parties

## Troubleshooting

### Application Won't Start After Rotation

**Error:** `ValueError: SECRET_KEY must be at least 32 characters long`

**Solution:**
```bash
# Check key length
echo $SECRET_KEY | wc -c
# Should be >= 32

# Regenerate if too short
python scripts/generate_jwt_secret.py
```

### Users Getting 401 Errors After Rotation

**Expected Behavior:** This is normal! Key rotation invalidates all existing tokens.

**User Action Required:** Re-authenticate (login again)

**To minimize impact:** Schedule rotations during low-traffic periods

### Token Blacklist Not Working

```sql
-- Check token blacklist table
SELECT COUNT(*) FROM token_blacklist WHERE is_active = true;

-- If empty, blacklisting may not be working
-- Check application logs for database errors
```

## Compliance & Auditing

### Rotation Log

Maintain a rotation log at `docs/security/rotation-log.md`:

```markdown
| Date       | Environment | Reason           | Performed By | Incident ID |
|------------|-------------|------------------|--------------|-------------|
| 2025-10-15 | Production  | Scheduled (90d)  | DevOps Team  | N/A         |
| 2025-09-01 | Staging     | Security Audit   | Security     | SEC-2025-09 |
| 2025-07-15 | Production  | Scheduled (90d)  | DevOps Team  | N/A         |
```

### Security Audits

- Quarterly review of key rotation procedures
- Annual penetration testing
- Monthly review of access logs
- Automated monitoring for weak keys

## References

- [OWASP JWT Security](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html)
- [NIST Password Guidelines](https://pages.nist.gov/800-63-3/sp800-63b.html)
- Backend Analysis Report (Issue 5.1)
- [PyJWT Documentation](https://pyjwt.readthedocs.io/)

## Support

**Questions or Issues?**
- Security incidents: security@wrext.com
- Technical support: #backend-support (Slack)
- On-call: PagerDuty escalation

---

**Document Version:** 1.0
**Next Review Date:** January 15, 2026
