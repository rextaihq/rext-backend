# Payment Dunning Task Setup

## Overview

The payment dunning task sends automated reminder emails to users with failed payments during their grace period. It runs daily and sends escalating reminders at specific intervals.

## Dunning Schedule

| Days After Failure | Email Type | Tone | Subject |
|-------------------|------------|------|---------|
| 1 day | First Reminder | Helpful & Informative | Payment Issue - Action Needed |
| 3 days | Second Reminder | Urgent | Urgent: Update Payment Method |
| 6 days | Final Warning | Very Urgent | FINAL NOTICE: Account Suspension Tomorrow |

## File Locations

- **Service:** `src/services/dunning_service.py`
- **Task:** `src/api/tasks/payment_dunning_task.py`
- **Email Templates:**
  - `emails/templates/billing/payment_dunning_1_day.py`
  - `emails/templates/billing/payment_dunning_3_days.py`
  - `emails/templates/billing/payment_dunning_6_days.py`

## Manual Execution

For testing or one-time runs:

```bash
# Navigate to backend directory
cd /path/to/wrext-backend

# Activate virtual environment
source .venv/bin/activate

# Run the task
python -m src.api.tasks.payment_dunning_task
```

## Automated Scheduling

### Option 1: Cron (Recommended for Production)

Add to crontab (`crontab -e`):

```bash
# Run daily at midnight UTC
0 0 * * * cd /path/to/wrext-backend && /path/to/.venv/bin/python -m src.api.tasks.payment_dunning_task >> /var/log/wrext/dunning.log 2>&1
```

### Option 2: systemd Timer (Linux)

Create `/etc/systemd/system/wrext-dunning.service`:

```ini
[Unit]
Description=WREXT Payment Dunning Task
After=network.target postgresql.service

[Service]
Type=oneshot
User=www-data
WorkingDirectory=/path/to/wrext-backend
Environment="PATH=/path/to/.venv/bin"
ExecStart=/path/to/.venv/bin/python -m src.api.tasks.payment_dunning_task
StandardOutput=journal
StandardError=journal
```

Create `/etc/systemd/system/wrext-dunning.timer`:

```ini
[Unit]
Description=Run WREXT Payment Dunning Daily
Requires=wrext-dunning.service

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and start:

```bash
sudo systemctl enable wrext-dunning.timer
sudo systemctl start wrext-dunning.timer
sudo systemctl status wrext-dunning.timer
```

### Option 3: APScheduler (Python-based)

Add to your FastAPI app startup:

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from src.api.tasks.payment_dunning_task import run_payment_dunning_task

scheduler = AsyncIOScheduler()

# Run daily at midnight UTC
scheduler.add_job(
    run_payment_dunning_task,
    'cron',
    hour=0,
    minute=0,
    id='payment_dunning_task'
)

scheduler.start()
```

## Monitoring

### Logs

The task logs to the application logger with these events:

- Task start/completion
- Subscriptions processed for each day (1, 3, 6)
- Emails sent/failed
- Errors and exceptions

Example log output:

```
2025-01-18 00:00:01 [info] === Payment Dunning Task Started ===
2025-01-18 00:00:01 [info] --- Processing 1-day dunning reminders ---
2025-01-18 00:00:01 [info] Found 5 subscriptions for 1-day dunning reminder
2025-01-18 00:00:02 [info] Sent 1-day dunning email to user@example.com
...
2025-01-18 00:00:05 [info] Completed 1-day dunning: 5 sent, 0 failed
2025-01-18 00:00:05 [info] --- Processing 3-day dunning reminders ---
...
2025-01-18 00:00:10 [info] === Payment Dunning Task Completed Successfully ===
2025-01-18 00:00:10 [info] Total emails sent: 12
```

### Metrics to Track

Monitor these metrics for dunning effectiveness:

- **Total dunning emails sent** (by day: 1, 3, 6)
- **Payment recovery rate** after each email
- **Email delivery failures**
- **Task execution time**
- **Subscriptions reaching final warning** (6-day mark)

### Health Checks

Ensure the task runs successfully:

```bash
# Check last execution (if using systemd timer)
sudo systemctl status wrext-dunning.timer

# Check logs
journalctl -u wrext-dunning.service -n 100

# Check database for recent dunning activity
psql -d wrext -c "
  SELECT
    DATE(payment_failed_at) as failure_date,
    COUNT(*) as count,
    MIN(grace_period_end) as earliest_grace_end,
    MAX(grace_period_end) as latest_grace_end
  FROM user_subscriptions
  WHERE status = 'suspended'
    AND payment_failed_at IS NOT NULL
  GROUP BY DATE(payment_failed_at)
  ORDER BY failure_date DESC
  LIMIT 7;
"
```

## Testing

### Test the Service Directly

```python
import asyncio
from src.api.database.async_database import get_async_db_context
from src.services.dunning_service import DunningService

async def test_dunning():
    async with get_async_db_context() as db:
        service = DunningService(db)

        # Test 1-day dunning
        stats = await service.process_dunning_reminders(days_since_failure=1)
        print(f"1-day dunning: {stats}")

asyncio.run(test_dunning())
```

### Test Email Templates

```python
from emails.templates.billing import render_payment_dunning_1_day_email

html = render_payment_dunning_1_day_email(
    user_name="Test User",
    plan_name="Pro Plan",
    amount="$29.99",
    grace_period_end_date="January 25, 2025"
)

# Save to file for visual inspection
with open("test_dunning_email.html", "w") as f:
    f.write(html)
```

## Troubleshooting

### No Emails Sent

**Check:**
1. Are there subscriptions with `status = 'suspended'` and `payment_failed_at` set?
2. Is the `payment_failed_at` date exactly 1, 3, or 6 days ago?
3. Are email preferences enabled for users?
4. Is the email service (Resend) configured correctly?

**Debug query:**
```sql
SELECT
  id,
  user_id,
  status,
  payment_failed_at,
  grace_period_end,
  NOW() - payment_failed_at as days_since_failure
FROM user_subscriptions
WHERE status = 'suspended'
  AND payment_failed_at IS NOT NULL
  AND grace_period_end > NOW()
ORDER BY payment_failed_at DESC;
```

### Duplicate Emails

The service uses a time window (±1 hour) to prevent exact timestamp matching issues. If duplicates occur:

1. Check that the task only runs once per day
2. Verify cron isn't configured multiple times
3. Check for overlapping scheduler configurations

### Task Failing

Check error logs for common issues:

- Database connection errors
- Email service API key issues
- Missing user or plan records
- Template rendering errors

## Grace Period Logic

The dunning system works in conjunction with the grace period:

1. **Payment fails** → Status set to `SUSPENDED`, `grace_period_end` set to +7 days
2. **Day 1** → First reminder sent (informative)
3. **Day 3** → Second reminder sent (urgent)
4. **Day 6** → Final warning sent (very urgent, 1 day before suspension)
5. **Day 7** → Grace period expires → Automatic suspension task runs (Task 3.4.3)

## Configuration

### Environment Variables

None required - uses existing email service configuration.

### Grace Period Duration

Default: 7 days (set in payment failure webhook handler)

To modify, update:
```python
# src/services/webhook_handlers/subscription_handlers.py
grace_period_days = 7  # Change this value
```

### Dunning Email Schedule

To modify reminder timing, update the task to run on different days:

```python
# src/api/tasks/payment_dunning_task.py

# Change from days 1, 3, 6 to custom schedule
day_1_stats = await self.dunning_service.process_dunning_reminders(
    days_since_failure=2  # Change this
)
```

## Related Documentation

- [Subscription Architecture](./SUBSCRIPTION_ARCHITECTURE.md)
- [Payment Recovery Handling](./PAYMENT_RECOVERY.md)
- [Email Service Configuration](./EMAIL_SERVICE.md)
- [Background Tasks](./BACKGROUND_TASKS.md)
