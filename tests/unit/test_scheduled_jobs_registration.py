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
