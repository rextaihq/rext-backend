# Background Tasks

This directory contains background tasks for automated operations.

## Subscription Tasks

File: `subscription_tasks.py`

Contains automated subscription management tasks that should run daily:

### Tasks

1. **`check_and_notify_expiring_trials()`** - Sends email notifications to users 3 days before their trial ends
2. **`expire_ended_trials()`** - Marks expired trials as EXPIRED status and sends notification
3. **`reset_monthly_usage()`** - Resets each paid plan's monthly credits when its billing period rolls over
4. **`run_daily_subscription_tasks()`** - Convenience function to run all tasks

### Setup with Cron

Add to your crontab (runs daily at 2 AM):

```bash
0 2 * * * cd /path/to/rext-backend && source .venv/bin/activate && python -c "import asyncio; from src.api.tasks.subscription_tasks import run_daily_subscription_tasks; asyncio.run(run_daily_subscription_tasks())" >> /var/log/rext/subscription-tasks.log 2>&1
```

### Setup with APScheduler (Recommended)

Create `scheduler.py` in your project root:

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from src.api.tasks.subscription_tasks import run_daily_subscription_tasks
import asyncio

scheduler = AsyncIOScheduler()

# Run daily at 2 AM UTC
scheduler.add_job(
    run_daily_subscription_tasks, "cron", hour=2, minute=0, id="daily_subscription_tasks"
)

if __name__ == "__main__":
    scheduler.start()
    print("Scheduler started. Press Ctrl+C to exit.")
    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
```

Run with:
```bash
python scheduler.py
```

### Setup with Celery

Add to your Celery beat schedule:

```python
from celery import Celery
from celery.schedules import crontab

app = Celery("rext")

app.conf.beat_schedule = {
    "daily-subscription-tasks": {
        "task": "src.api.tasks.subscription_tasks.run_daily_subscription_tasks",
        "schedule": crontab(hour=2, minute=0),  # Daily at 2 AM
    },
}
```

### Manual Execution (Testing)

```python
import asyncio
from src.api.tasks.subscription_tasks import run_daily_subscription_tasks

# Run all tasks
results = asyncio.run(run_daily_subscription_tasks())
print(results)

# Or run individual tasks
from src.api.tasks.subscription_tasks import check_and_notify_expiring_trials

results = asyncio.run(check_and_notify_expiring_trials())
```

### Monitoring

All tasks log to the standard logger. Check logs for:
- Number of trials expiring
- Number of emails sent
- Number of subscriptions expired
- Number of usage resets

Example log output:
```
INFO: Found 5 trial(s) expiring in 3 days
INFO: Sent trial ending email to user@example.com
INFO: Successfully sent 5/5 trial ending emails
INFO: Found 2 expired trial(s)
INFO: Expired trial subscription abc-123
INFO: Daily subscription tasks completed
```

### Environment Requirements

Ensure these environment variables are set:
- `RESEND_API_KEY` - For sending emails
- `DATABASE_URL` - Database connection
- `FRONTEND_URL` - For email links (default: http://localhost:3000; the deploys set the dashboard's address)

### Testing

To test without actually sending emails, set:
```bash
EMAIL_PROVIDER=mock
```

This will use the MockEmailProvider which logs emails instead of sending them.
