"""The signed-out checks a deploy ends with (FB2.34, revnix/rext-control#727).

`scripts/smoke.py` asks what a visitor who has not signed in can ask: is the API the commit just
deployed, is it ready, does it refuse a call without a session, does it serve the plans and
the incident banner's read. Both deploy workflows run it in a job of its own after the deploy,
so a failure turns the run red and can't block or undo the deploy.
"""

import inspect
import io
import re
import urllib.error
from pathlib import Path

import pytest
import yaml

from scripts import smoke
from scripts.smoke import Answer, NoAnswer

ROOT = Path(__file__).resolve().parents[2]
SHA = "0123456789abcdef0123456789abcdef01234567"
API = "https://api.test"

GOOD = {
    "/health/live": Answer(200, {"status": "alive", "commit": SHA}),
    "/health/ready": Answer(200, {"status": "ready", "checks": {"database": "ready"}}),
    smoke.PROTECTED_PATH: Answer(422, {"success": False, "data": None}),
    "/api/v1/plans": Answer(200, {"success": True, "data": {"plans": [{"name": "Growth"}]}}),
    "/api/v1/status/banner": Answer(200, {"success": True, "data": {"active": False}}),
}


def _run(answers: dict, commit: str | None = SHA):
    """The failed checks, the lines said, the addresses asked and the pauses taken."""
    said, asked, pauses = [], [], []

    def fetch(url: str) -> Answer:
        asked.append(url)
        answer = answers[url.removeprefix(API)]
        if isinstance(answer, list):  # one answer per attempt
            answer = answer.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    failed = smoke.run(API, commit, fetch=fetch, sleep=pauses.append, say=said.append)
    return failed, said, asked, pauses


def test_a_healthy_deploy_passes_every_check():
    failed, said, asked, pauses = _run(dict(GOOD))

    assert failed == []
    assert [line[:4] for line in said] == ["pass"] * 5
    assert asked == [API + path for path in GOOD]  # each asked once
    assert pauses == []


@pytest.mark.parametrize(
    ("path", "answer", "check", "says"),
    [
        (
            "/health/live",
            Answer(200, {"status": "alive", "commit": "f" * 40}),
            "the API runs the deployed commit",
            f"runs {'f' * 40}, not {SHA}",
        ),
        ("/health/live", Answer(502, None), "the API runs the deployed commit", "answered 502"),
        (
            "/health/ready",
            Answer(
                503,
                {
                    "status": "not_ready",
                    "checks": {"database": "not_ready: down", "redis": "not_configured"},
                },
            ),
            "the API is ready",
            "answered 503, not ready (database)",
        ),
        (
            smoke.PROTECTED_PATH,
            Answer(200, {"success": True, "data": {"plan": "Growth"}}),
            "a call without a session is refused",
            "answered 200 to a call without a session",
        ),
        (
            smoke.PROTECTED_PATH,
            Answer(500, None),
            "a call without a session is refused",
            "answered 500",
        ),
        (
            "/api/v1/plans",
            Answer(200, {"success": True, "data": {"plans": []}}),
            "the plans are served",
            "answered 200 with no plans",
        ),
        ("/api/v1/plans", Answer(500, None), "the plans are served", "answered 500"),
        (
            "/api/v1/status/banner",
            Answer(404, {"success": False, "data": None}),
            "the incident banner's read answers",
            "answered 404 without saying whether a banner is showing",
        ),
        (
            "/api/v1/status/banner",
            Answer(503, None),
            "the incident banner's read answers",
            "answered 503",
        ),
    ],
)
def test_a_wrong_answer_fails_its_check_by_name(path, answer, check, says):
    failed, said, asked, pauses = _run({**GOOD, path: answer})

    assert failed == [check]
    (line,) = [line for line in said if line.startswith("FAIL")]
    assert check in line and path in line and says in line
    assert len(asked) == 5  # an answer is never asked for again, and the rest still run
    assert pauses == []


def test_a_request_that_got_no_answer_is_made_once_more():
    failed, _, asked, pauses = _run(
        {**GOOD, "/health/ready": [NoAnswer("timeout"), GOOD["/health/ready"]]}
    )

    assert failed == []
    assert asked.count(API + "/health/ready") == 2
    assert pauses == [smoke.PAUSE_BEFORE_SECOND_ATTEMPT]


def test_no_answer_twice_fails_the_check_and_is_not_asked_a_third_time():
    answers = {**GOOD, "/api/v1/plans": [NoAnswer("timeout"), NoAnswer("timeout")]}
    failed, said, asked, pauses = _run(answers)

    assert failed == ["the plans are served"]
    (line,) = [line for line in said if line.startswith("FAIL")]
    assert "no answer, twice (timeout)" in line
    assert asked.count(API + "/api/v1/plans") == 2
    assert pauses == [smoke.PAUSE_BEFORE_SECOND_ATTEMPT]


def test_without_a_commit_any_live_commit_passes():
    failed, *_ = _run(
        {**GOOD, "/health/live": Answer(200, {"status": "alive", "commit": "unknown"})}, None
    )

    assert failed == []


def test_every_failed_check_is_named_in_the_error(capsys):
    answers = {**GOOD, "/health/ready": Answer(503, None), "/api/v1/plans": Answer(500, None)}

    code = smoke.main(
        ["--api", API, "--commit", SHA], fetch=lambda url: answers[url.removeprefix(API)]
    )

    assert code == 1
    assert (
        f"::error::Smoke test failed on {API}: the API is ready; the plans are served"
        in capsys.readouterr().out
    )


def test_a_passing_run_exits_zero(capsys):
    assert smoke.main(["--api", API + "/"], fetch=lambda url: GOOD[url.removeprefix(API)]) == 0
    assert f"Smoke test passed on {API}/" in capsys.readouterr().out


class _Response:
    status = 200

    def __init__(self, raw: bytes):
        self.raw = raw

    def read(self) -> bytes:
        return self.raw

    def __enter__(self):
        return self

    def __exit__(self, *error):
        return False


def test_a_request_only_reads_and_carries_no_credentials(monkeypatch):
    made = []

    def urlopen(request, timeout):
        made.append((request, timeout))
        return _Response(b'{"status": "alive"}')

    monkeypatch.setattr(smoke.urllib.request, "urlopen", urlopen)

    assert smoke.get(API + "/health/live") == Answer(200, {"status": "alive"})
    ((request, timeout),) = made
    assert request.get_method() == "GET"
    assert request.data is None
    assert dict(request.header_items()) == {"Accept": "application/json"}
    assert timeout == smoke.TIMEOUT_SECONDS
    # The script has one way to ask, and it is that one.
    assert inspect.getsource(smoke).count("urlopen(") == 1


def test_an_error_status_is_an_answer_and_a_dead_connection_is_none(monkeypatch):
    def refused(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 422, "Unprocessable", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(smoke.urllib.request, "urlopen", refused)
    assert smoke.get(API + smoke.PROTECTED_PATH) == Answer(422, {})

    def dead(request, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(smoke.urllib.request, "urlopen", dead)
    with pytest.raises(NoAnswer):
        smoke.get(API + "/health/live")

    def slow(request, timeout):
        raise TimeoutError

    monkeypatch.setattr(smoke.urllib.request, "urlopen", slow)
    with pytest.raises(NoAnswer):
        smoke.get(API + "/health/live")


def test_a_page_that_is_not_json_is_an_answer_without_a_body(monkeypatch):
    monkeypatch.setattr(
        smoke.urllib.request, "urlopen", lambda request, timeout: _Response(b"<html>Bad Gateway")
    )
    assert smoke.get(API + "/health/live") == Answer(200, None)


def test_the_worst_case_fits_the_jobs_three_minutes():
    per_check = 2 * smoke.TIMEOUT_SECONDS + smoke.PAUSE_BEFORE_SECOND_ATTEMPT
    # Half a minute of the three is left for the checkout and the read of the running commit.
    assert len(smoke.checks(SHA)) * per_check <= 150


WORKFLOWS = [
    ("production.yaml", "https://api.rext.ai", "main"),
    ("stage.yaml", "https://staging-api.rext.ai", "stage"),
]


def _jobs(name: str) -> dict:
    return yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))[
        "jobs"
    ]


def _needs(job: dict) -> list:
    needs = job.get("needs", [])
    return [needs] if isinstance(needs, str) else needs


@pytest.mark.parametrize(("name", "api", "branch"), WORKFLOWS)
def test_the_smoke_job_runs_after_the_deploy_and_nothing_waits_for_it(name, api, branch):
    jobs = _jobs(name)
    job = jobs["smoke"]

    assert "deploy" in _needs(job)
    assert job["timeout-minutes"] == 3
    assert job["permissions"] == {"contents": "read"}
    # No job needs it: it can fail the run, never hold back or undo a deploy.
    assert [other for other, body in jobs.items() if "smoke" in _needs(body)] == []
    # Its own job: the deploy's steps don't run it.
    assert "smoke.py" not in str(jobs["deploy"])


@pytest.mark.parametrize(("name", "api", "branch"), WORKFLOWS)
def test_the_smoke_job_checks_the_deployed_commit_without_secrets(name, api, branch):
    (step,) = [s for s in _jobs(name)["smoke"]["steps"] if "smoke.py" in s.get("run", "")]

    assert step["env"]["API_URL"] == api
    assert step["env"]["EXPECTED"] == "${{ github.sha }}"
    assert 'python3 scripts/smoke.py --api "$API_URL" --commit "$EXPECTED"' in step["run"]
    assert "secrets." not in str(_jobs(name)["smoke"])
    # No waiting and no loop: the deploy job has already waited for the commit.
    commands = [line for line in step["run"].splitlines() if not line.strip().startswith("#")]
    assert not re.search(r"\b(sleep|while|until|for|retry)\b", "\n".join(commands))


def test_production_smokes_only_what_main_deployed():
    assert _jobs("production.yaml")["smoke"]["if"] == "github.ref == 'refs/heads/main'"


def test_staging_smokes_only_a_backend_this_run_deployed():
    # A push that changed only the Shopify app deploys no backend: its commit isn't the API's.
    condition = _jobs("stage.yaml")["smoke"]["if"]

    assert "needs.docker_job.result == 'success'" in condition
    assert "needs.deploy.result == 'success'" in condition
