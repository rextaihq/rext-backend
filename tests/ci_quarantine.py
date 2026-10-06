"""
A pytest plugin for the CI run only (.github/workflows/pr-checks.yaml loads it with -p).

- The tests listed in tests/quarantine.list fail on stage today. Their failures, in setup, call or
  teardown, are reported as expected (xfail), so any other failure is a new one. A quarantined test
  that passes is listed at the end, to be taken off the list.
- Once pytest has reported, the process ends at once with pytest's exit code, and names any thread
  still alive: the interpreter has hung on exit after a finished run (rext-control#373).
"""

import os
import sys
import threading
from pathlib import Path

import pytest

QUARANTINE = Path(__file__).with_name("quarantine.list")
REASON = "quarantined: fails on stage today (tests/quarantine.list)"


def quarantined() -> set:
    """The node ids in tests/quarantine.list: one per line; # starts a comment."""
    if not QUARANTINE.exists():
        return set()
    lines = (line.split(" #", 1)[0].strip() for line in QUARANTINE.read_text().splitlines())
    return {line for line in lines if line and not line.startswith("#")}


def pytest_configure(config):
    config._quarantine = quarantined()
    config._quarantine_passed = []
    config._quarantine_exit = 0


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if item.nodeid not in item.config._quarantine:
        return
    if report.failed:
        report.outcome = "skipped"
        report.wasxfail = REASON
    elif report.when == "call" and report.passed:
        item.config._quarantine_passed.append(item.nodeid)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    passed = config._quarantine_passed
    if passed:
        terminalreporter.section(
            "quarantined tests that passed: take them off tests/quarantine.list"
        )
        for nodeid in passed:
            terminalreporter.line(f"QUARANTINE-PASSED {nodeid}")


def pytest_sessionfinish(session, exitstatus):
    session.config._quarantine_exit = int(exitstatus)


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    alive = [t for t in threading.enumerate() if t is not threading.main_thread() and not t.daemon]
    if alive:
        names = ", ".join(f"{t.name} ({type(t).__name__})" for t in alive)
        print(f"threads still alive at exit: {names}", file=sys.stderr)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(config._quarantine_exit)
