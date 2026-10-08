"""Which jobs the scheduler registers, and how often the publish job runs."""

import pytest

import src.tasks.scheduled_tasks as scheduled_tasks
from src.api.tasks.webhook_reprocessing_task import run_webhook_reprocessing_task


class _Job:
    def __init__(self, func, kwargs):
        self.func = func
        self.id = kwargs["id"]
        self.name = kwargs.get("name")
        self.kwargs = kwargs
        self.next_run_time = None


class _FakeScheduler:
    def __init__(self):
        self.jobs: list[_Job] = []
        self.started = False

    def add_job(self, func, **kwargs):
        self.jobs.append(_Job(func, kwargs))

    def add_listener(self, *_args, **_kwargs):
        pass

    def get_jobs(self):
        return self.jobs

    def start(self):
        self.started = True


@pytest.fixture
def manager(monkeypatch):
    fake = _FakeScheduler()
    monkeypatch.setattr(scheduled_tasks, "AsyncIOScheduler", lambda: fake)
    monkeypatch.setattr(scheduled_tasks, "APSCHEDULER_AVAILABLE", True)
    monkeypatch.setattr(scheduled_tasks.cleanup_config, "SCHEDULER_ENABLED", True)
    return scheduled_tasks.ScheduledTaskManager(), fake


def _jobs(fake):
    return {job.id: job for job in fake.jobs}


def test_failed_webhook_reprocessing_is_registered_when_enabled(manager, monkeypatch):
    monkeypatch.setattr(scheduled_tasks.cleanup_config, "WEBHOOK_REPROCESS_TASKS_ENABLED", True)
    task_manager, fake = manager
    task_manager.start()

    job = _jobs(fake)["webhook_reprocessing"]
    assert job.func is run_webhook_reprocessing_task
    assert (
        job.kwargs["minutes"] == scheduled_tasks.cleanup_config.WEBHOOK_REPROCESS_INTERVAL_MINUTES
    )
    assert job.kwargs["max_instances"] == 1


def test_failed_webhook_reprocessing_stays_off_when_disabled(manager, monkeypatch):
    monkeypatch.setattr(scheduled_tasks.cleanup_config, "WEBHOOK_REPROCESS_TASKS_ENABLED", False)
    task_manager, fake = manager
    task_manager.start()

    assert "webhook_reprocessing" not in _jobs(fake)


def test_the_daily_invitation_reminders_are_registered(manager, monkeypatch):
    from src.api.tasks.invitation_reminder_task import run_invitation_reminders_task

    monkeypatch.setattr(scheduled_tasks.cleanup_config, "INVITATION_REMINDERS_ENABLED", True)
    task_manager, fake = manager
    task_manager.start()

    job = _jobs(fake)["invitation_reminders"]
    assert job.func is run_invitation_reminders_task
    assert job.kwargs["max_instances"] == 1
    # Once a day, at the configured hour.
    daily = {field.name: str(field) for field in job.kwargs["trigger"].fields}
    assert daily["hour"] == str(scheduled_tasks.cleanup_config.INVITATION_REMINDER_HOUR)
    assert daily["minute"] == str(scheduled_tasks.cleanup_config.INVITATION_REMINDER_MINUTE)
    assert daily["day"] == "*"


def test_the_invitation_reminders_stay_off_when_disabled(manager, monkeypatch):
    monkeypatch.setattr(scheduled_tasks.cleanup_config, "INVITATION_REMINDERS_ENABLED", False)
    task_manager, fake = manager
    task_manager.start()

    assert "invitation_reminders" not in _jobs(fake)


def test_scheduled_publish_runs_every_minute(manager):
    task_manager, fake = manager
    task_manager.start()

    assert _jobs(fake)["scheduled_content_publish"].kwargs["minutes"] == 1


def test_nothing_is_registered_when_the_scheduler_is_off(manager, monkeypatch):
    monkeypatch.setattr(scheduled_tasks.cleanup_config, "SCHEDULER_ENABLED", False)
    task_manager, fake = manager
    task_manager.start()

    assert fake.jobs == []
    assert not fake.started


def test_the_nightly_subscription_reconcile_is_registered_and_the_grace_jobs_are_gone(
    manager, monkeypatch
):
    from src.api.tasks.subscription_reconcile_task import run_subscription_reconcile_task

    monkeypatch.setattr(scheduled_tasks.cleanup_config, "BILLING_TASKS_ENABLED", True)
    monkeypatch.setattr(scheduled_tasks.cleanup_config, "SUBSCRIPTION_RECONCILE_ENABLED", True)
    task_manager, fake = manager
    task_manager.start()
    jobs = _jobs(fake)

    assert jobs["subscription_reconcile"].func is run_subscription_reconcile_task
    assert jobs["subscription_reconcile"].kwargs["max_instances"] == 1
    # Lemon Squeezy's status replaced our own grace timer and its countdown emails (F11).
    assert "grace_period_expiration" not in jobs
    assert "payment_dunning" not in jobs


def test_the_billing_switch_turns_the_reconcile_off_too(manager, monkeypatch):
    """BILLING_TASKS_ENABLED=false stops subscription maintenance, the reconcile included."""
    monkeypatch.setattr(scheduled_tasks.cleanup_config, "BILLING_TASKS_ENABLED", False)
    monkeypatch.setattr(scheduled_tasks.cleanup_config, "SUBSCRIPTION_RECONCILE_ENABLED", True)
    task_manager, fake = manager
    task_manager.start()

    assert "subscription_reconcile" not in _jobs(fake)
