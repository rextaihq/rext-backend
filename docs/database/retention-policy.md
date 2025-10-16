# Data Retention Policy

**Version:** 1.0
**Last Updated:** October 16, 2025
**Status:** Active

## Overview

This document defines the data retention policies for the WREXT backend system. It specifies how long different types of data are retained before being automatically cleaned up to manage database growth and comply with data retention best practices.

## Retention Periods

| Table | Data Type | Retention Period | Reason |
|-------|-----------|------------------|--------|
| `audit_logs` | Audit trail records | **90 days** | Compliance and security investigation window |
| `email_logs` | Email send tracking | **30 days** | Operational troubleshooting window |
| `email_events` | Email webhook events | **30 days** | Linked to email_logs, cleaned up with them |
| `user_sessions` | Active user sessions | **7 days** (inactive) | Security - remove stale sessions |

## Cleanup Schedule

### Automated Cleanup

- **Frequency:** Daily at 2:00 AM UTC
- **Method:** Scheduled task via APScheduler
- **Batch Size:** 1,000 records per batch
- **Status:** Enabled by default (configurable via `CLEANUP_ENABLED`)

### Manual Cleanup

Cleanup can be triggered manually using the cleanup script:

```bash
# Dry run (preview only)
python scripts/cleanup_old_data.py --dry-run

# Execute cleanup
python scripts/cleanup_old_data.py

# Clean specific table
python scripts/cleanup_old_data.py --table audit_logs

# Custom retention period
python scripts/cleanup_old_data.py --table email_logs --retention-days 60
```

## Configuration

Retention periods can be customized via environment variables:

```bash
# .env file
CLEANUP_ENABLED=true                    # Enable/disable automated cleanup
CLEANUP_HOUR=2                          # Hour to run cleanup (0-23)
CLEANUP_MINUTE=0                        # Minute to run cleanup (0-59)
CLEANUP_DRY_RUN=false                   # Test mode (count only, no deletion)
CLEANUP_BATCH_SIZE=1000                 # Records per batch

# Retention periods (in days)
AUDIT_LOG_RETENTION_DAYS=90
EMAIL_LOG_RETENTION_DAYS=30
EMAIL_EVENT_RETENTION_DAYS=30
USER_SESSION_INACTIVE_DAYS=7
```

## Cleanup Details

### Audit Logs (`audit_logs`)

**Retention:** 90 days
**Cleanup Criteria:** `created_at < now() - 90 days`

- Tracks sensitive operations (user management, role changes, etc.)
- 90-day retention provides sufficient audit trail for:
  - Security investigations
  - Compliance requirements
  - Dispute resolution
- Older logs can be archived to cold storage if long-term retention is needed

**Note:** Consider archiving critical audit logs before deletion for long-term compliance.

### Email Logs (`email_logs`)

**Retention:** 30 days
**Cleanup Criteria:** `created_at < now() - 30 days`

- Tracks all email sends (status, timestamps, provider details)
- 30-day window sufficient for:
  - Troubleshooting email delivery issues
  - User support inquiries
  - Operational monitoring
- Related `email_events` are automatically deleted via CASCADE

**Note:** Email events are cleaned up automatically when parent email_log is deleted due to CASCADE relationship.

### Email Events (`email_events`)

**Retention:** 30 days (orphaned records only)
**Cleanup Criteria:** `created_at < now() - 30 days AND email_log_id IS NULL`

- Webhook events from email providers (delivered, opened, clicked, etc.)
- Orphaned events (no parent email_log) are cleaned up independently
- Events linked to email_logs are cleaned via CASCADE when email_log is deleted

**Note:** Only cleans up orphaned records. Most events are deleted with their parent email_log.

### User Sessions (`user_sessions`)

**Retention:** 7 days (inactive)
**Cleanup Criteria:**
- `last_activity_at < now() - 7 days` (inactive), OR
- `expires_at < now()` (expired), OR
- `revoked_at IS NOT NULL` (revoked)

- Tracks active user login sessions
- Removes sessions that are:
  - Inactive for 7+ days
  - Past expiration time
  - Manually revoked
- Improves security by removing stale sessions
- Reduces session table size

**Note:** Active sessions are never deleted regardless of age.

## Data Deletion Process

### Batch Deletion

To avoid long-running transactions and database locks:

1. Delete records in batches (default: 1,000 records)
2. Commit after each batch
3. Continue until no more records match criteria
4. Log progress for monitoring

### Safety Measures

1. **Dry Run Mode**: Preview deletions without actually deleting
2. **Logging**: All cleanup operations are logged with record counts
3. **Transaction Safety**: Each batch is committed separately
4. **Error Handling**: Failures are logged and don't stop entire cleanup
5. **Monitoring**: Cleanup results available in application logs

## Monitoring

### Logging

All cleanup operations are logged with:
- Start/end timestamps
- Records deleted per table
- Total records deleted
- Retention periods used
- Errors (if any)

### Metrics

Monitor these metrics to track cleanup effectiveness:

```sql
-- Check table sizes
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE tablename IN ('audit_logs', 'email_logs', 'email_events', 'user_sessions')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Check oldest records per table
SELECT 'audit_logs' as table, MIN(created_at) as oldest FROM audit_logs
UNION ALL
SELECT 'email_logs', MIN(created_at) FROM email_logs
UNION ALL
SELECT 'email_events', MIN(created_at) FROM email_events
UNION ALL
SELECT 'user_sessions', MIN(last_activity_at) FROM user_sessions;

-- Check record counts
SELECT 'audit_logs' as table, COUNT(*) as count FROM audit_logs
UNION ALL
SELECT 'email_logs', COUNT(*) FROM email_logs
UNION ALL
SELECT 'email_events', COUNT(*) FROM email_events
UNION ALL
SELECT 'user_sessions', COUNT(*) FROM user_sessions;
```

## Compliance Considerations

### GDPR

- **Right to Erasure**: User data in audit logs should be anonymized or deleted upon user request
- **Data Minimization**: Retention periods align with operational needs
- **Purpose Limitation**: Data retained only as long as necessary

### SOC 2

- **Audit Trail**: 90-day audit log retention supports security monitoring requirements
- **Access Logging**: Session tracking provides user activity audit trail
- **Incident Response**: Sufficient retention for security investigations

### Best Practices

1. **Document Retention**: This policy documents why data is retained and for how long
2. **Regular Review**: Review retention periods annually
3. **Data Classification**: Different retention for different data types
4. **Secure Deletion**: Data is permanently deleted (not soft-deleted)

## Archival (Optional)

For long-term retention needs, consider archiving before deletion:

### Archive to S3/Cloud Storage

```python
# Example: Archive audit logs before deletion
async def archive_old_audit_logs():
    """Archive audit logs older than 90 days to S3 before deletion."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)

    # Query old logs
    old_logs = await db.execute(
        select(AuditLog).where(AuditLog.created_at < cutoff)
    )

    # Export to JSON
    data = [log.to_dict() for log in old_logs.scalars()]

    # Upload to S3
    s3_client.put_object(
        Bucket='audit-archive',
        Key=f'audit_logs_{cutoff.date()}.json',
        Body=json.dumps(data)
    )

    # Now safe to delete
    await cleanup_service.cleanup_audit_logs()
```

### Archive to Data Warehouse

Consider streaming logs to a data warehouse (Snowflake, BigQuery) for long-term analytics:

- Real-time streaming via event pipeline
- No need for pre-deletion archival
- Enables long-term trend analysis

## Troubleshooting

### Cleanup Not Running

1. Check `CLEANUP_ENABLED=true` in environment
2. Verify APScheduler is installed: `pip install apscheduler`
3. Check application logs for scheduler startup messages
4. Verify cron schedule in configuration

### Performance Issues

If cleanup causes performance problems:

1. **Reduce batch size**: Set `CLEANUP_BATCH_SIZE=500`
2. **Run during off-hours**: Adjust `CLEANUP_HOUR` to lowest traffic time
3. **Add indexes**: Ensure `created_at` and `last_activity_at` are indexed
4. **Monitor locks**: Check for long-running queries blocking cleanup

### Too Much Data Deleted

If retention period is too aggressive:

1. **Increase retention**: Update `*_RETENTION_DAYS` environment variables
2. **Test with dry-run**: Always test new retention periods with `--dry-run`
3. **Restore from backup**: If data was accidentally deleted

## Testing

### Test Cleanup in Development

```bash
# 1. Create old test data
INSERT INTO audit_logs (id, action, resource_type, created_at)
VALUES (gen_random_uuid(), 'test.action', 'test', NOW() - INTERVAL '100 days');

# 2. Run dry-run
python scripts/cleanup_old_data.py --dry-run

# 3. Verify count matches expected
SELECT COUNT(*) FROM audit_logs WHERE created_at < NOW() - INTERVAL '90 days';

# 4. Run actual cleanup
python scripts/cleanup_old_data.py

# 5. Verify deletion
SELECT COUNT(*) FROM audit_logs WHERE created_at < NOW() - INTERVAL '90 days';  -- Should be 0
```

## Future Enhancements

Potential improvements to consider:

1. **Table Partitioning**: Partition large tables by date for faster cleanup
2. **Graduated Retention**: Different retention for different severity levels
3. **User-Configurable**: Allow workspaces to set their own retention periods
4. **Archive Automation**: Automatic archival to S3 before deletion
5. **Retention Tags**: Tag records for custom retention periods
6. **Compliance Reports**: Generate reports showing data retention compliance

## References

- Code: `src/services/data_cleanup_service.py`
- Configuration: `src/config/cleanup_config.py`
- Scheduled Tasks: `src/tasks/scheduled_tasks.py`
- Manual Script: `scripts/cleanup_old_data.py`
- Models: `src/api/models/audit_models/`, `src/api/models/email_models/`, `src/api/models/user_models/`

## Change Log

| Date | Version | Changes |
|------|---------|---------|
| 2025-10-16 | 1.0 | Initial retention policy document |

---

**Document Owner:** Backend Team
**Review Frequency:** Annually or as needed
**Next Review:** October 2026
