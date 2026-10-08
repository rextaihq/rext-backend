"""A deploy pulls the new image and proves the server runs the commit it built.

The backend is a Coolify Service: /api/v1/deploy only starts it with the images it has, so the
workflows restart it with latest=true. CI writes the commit into src/api/build_commit.txt before
`langgraph build`; /health/live reports it, and the deploy job waits for it.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

import src.api.server as server
from src.api.build_info import UNKNOWN, read_build_commit

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
SHA = "0123456789abcdef0123456789abcdef01234567"


def _workflow(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_reads_the_commit_ci_wrote(tmp_path: Path) -> None:
    path = tmp_path / "build_commit.txt"
    path.write_text(f"{SHA}\n", encoding="utf-8")
    assert read_build_commit(path) == SHA


def test_no_file_means_unknown(tmp_path: Path) -> None:
    assert read_build_commit(tmp_path / "build_commit.txt") == UNKNOWN


@pytest.mark.parametrize("content", ["", "main", SHA[:7], SHA.upper(), f"{SHA}0", "<html>"])
def test_anything_but_a_full_sha_means_unknown(tmp_path: Path, content: str) -> None:
    path = tmp_path / "build_commit.txt"
    path.write_text(content, encoding="utf-8")
    assert read_build_commit(path) == UNKNOWN


@pytest.mark.asyncio
async def test_liveness_reports_the_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "BUILD_COMMIT", SHA)
    body = await server.liveness_check(None)
    assert body["status"] == "alive"
    assert body["commit"] == SHA


def test_the_commit_file_is_not_committed() -> None:
    assert "src/api/build_commit.txt" in (ROOT / ".gitignore").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["stage.yaml", "production.yaml"])
def test_ci_records_the_commit_before_building(name: str) -> None:
    text = _workflow(name)
    record = text.index('echo "${{ github.sha }}" > src/api/build_commit.txt')
    assert record < text.index("langgraph build")


DEPLOYS = [
    ("stage.yaml", "COOLIFY_UUID_STAGE", "https://staging-api.rext.ai/health/live"),
    ("production.yaml", "COOLIFY_UUID_PROD", "https://api.rext.ai/health/live"),
]


@pytest.mark.parametrize(("name", "secret", "health"), DEPLOYS)
def test_the_deploy_restarts_with_the_latest_images(name: str, secret: str, health: str) -> None:
    # Production too, since pgbouncer and minio-mirror are pinned by digest in its
    # Service (#423): a restart with latest=true pulls only the new backend image.
    runs = "\n".join(step.get("run", "") for step in _jobs(name)["deploy"]["steps"])
    assert f"/api/v1/services/${{{{ secrets.{secret} }}}}/restart" in runs
    assert '--url-query "latest=true"' in runs
    # /api/v1/deploy only starts a Service with the images it already has.
    assert f"uuid=${{{{ secrets.{secret} }}}}" not in runs


def _wait_step(name: str) -> dict:
    # The step that waits for the running commit: production's rollback guard reads
    # /health/live too, but expects no commit.
    (wait,) = [
        s
        for s in _jobs(name)["deploy"]["steps"]
        if "/health/live" in str(s.get("env")) and "EXPECTED" in (s.get("env") or {})
    ]
    return wait


@pytest.mark.parametrize(("name", "secret", "health"), DEPLOYS)
def test_the_deploy_waits_for_the_running_commit(name: str, secret: str, health: str) -> None:
    steps = _jobs(name)["deploy"]["steps"]
    wait = _wait_step(name)
    assert wait["env"]["HEALTH_URL"] == health
    assert wait["env"]["EXPECTED"] == "${{ github.sha }}"
    assert "jq -r '.commit" in wait["run"]
    # After the restart that it waits for.
    (restart,) = [
        i for i, s in enumerate(steps) if f"secrets.{secret} }}}}/restart" in s.get("run", "")
    ]
    assert restart < steps.index(wait)


def test_a_failed_production_deploy_says_what_to_do_by_hand() -> None:
    # The release is the first real run: the team needs the manual step in the error itself.
    steps = _jobs("production.yaml")["deploy"]["steps"]
    wait = _wait_step("production.yaml")["name"]
    checked = [s for s in steps if "COOLIFY_UUID_PROD" in s.get("run", "") or s["name"] == wait]
    assert [s["name"] for s in checked] == [
        "Restart the production backend with the new image",
        wait,
    ]
    for step in checked:
        error = [line for line in step["run"].splitlines() if "::error::" in line]
        assert error, step["name"]
        assert 'Restart with \\"Pull latest images\\" ticked' in error[-1], step["name"]
        assert "rext-backend service" in error[-1], step["name"]


def _jobs(name: str) -> dict:
    return yaml.safe_load(_workflow(name))["jobs"]


BRANCHES = [("stage.yaml", "stage"), ("production.yaml", "main")]
PUBLISHING_JOBS = ["docker_job", "docker_shopify", "deploy"]


@pytest.mark.parametrize(("name", "branch"), BRANCHES)
@pytest.mark.parametrize("job", PUBLISHING_JOBS)
def test_only_the_branch_publishes_or_deploys(name: str, branch: str, job: str) -> None:
    # A manual run on another ref must not reach the server.
    assert f"github.ref == 'refs/heads/{branch}'" in _jobs(name)[job]["if"]


@pytest.mark.parametrize(("name", "branch"), BRANCHES)
@pytest.mark.parametrize("job", PUBLISHING_JOBS)
def test_a_stale_run_is_refused_first(name: str, branch: str, job: str) -> None:
    # A re-run keeps its commit and runs can start out of push order: on every
    # attempt, an older commit must not publish or deploy over a newer one.
    first = _jobs(name)[job]["steps"][0]
    assert "if" not in first
    if (name, job) == ("production.yaml", "deploy"):
        # Merges land every few minutes: production deploys unless it would go back.
        assert first["name"] == "Refuse a rollback"
        assert "compare/$LIVE...${{ github.sha }}" in first["run"]
        assert "ahead|identical)" in first["run"]
        # No commit from production: the run must be main's head, as before.
        assert 'commits/main" --jq .sha' in first["run"]
        return
    assert first["name"] == "Refuse a stale run"
    if branch == "main":
        assert 'commits/main" --jq .sha' in first["run"]
        assert '"$HEAD" != "${{ github.sha }}"' in first["run"]
    else:
        assert "compare/${{ github.sha }}...stage" in first["run"]
        assert 'grep -E "$PATHS"' in first["run"]


def _sample(glob: str) -> str:
    """A file the push filter's glob matches."""
    return glob.replace("**", "a/b.py").replace("*", "x")


def test_each_component_s_stale_paths_are_its_change_filter() -> None:
    # A newer commit counts against a component when it started a run that deploys
    # that component: exactly when the changes job's filter for it matched.
    config = yaml.safe_load(_workflow("stage.yaml"))
    filters = yaml.safe_load(config["jobs"]["changes"]["steps"][1]["with"]["filters"])
    for component, env in (("backend", "BACKEND_PATHS"), ("shopify", "SHOPIFY_PATHS")):
        pattern = re.compile(config["env"][env])
        for glob in filters[component]:
            assert pattern.search(_sample(glob)), (component, glob)
        other = filters["shopify" if component == "backend" else "backend"]
        for glob in other:
            assert not pattern.search(_sample(glob)), (component, glob)
        assert not pattern.search("docs/notes.md")
        assert not pattern.search(".github/workflows/stage.yaml")


@pytest.mark.parametrize(
    ("job", "backend", "shopify"),
    [("docker_job", "true", "false"), ("docker_shopify", "false", "true")],
)
def test_a_publisher_checks_only_its_own_component(job: str, backend: str, shopify: str) -> None:
    env = _jobs("stage.yaml")[job]["steps"][0]["env"]
    assert (env["WANT_BACKEND"], env["WANT_SHOPIFY"]) == (backend, shopify)


def test_the_deploy_runs_only_what_the_stale_check_left() -> None:
    steps = _jobs("stage.yaml")["deploy"]["steps"]
    check = steps[0]
    assert check["id"] == "fresh"
    assert check["env"]["WANT_BACKEND"] == "${{ needs.docker_job.result == 'success' }}"
    assert check["env"]["WANT_SHOPIFY"] == "${{ needs.docker_shopify.result == 'success' }}"
    for step in steps[1:]:
        run = step.get("run", "")
        if (
            "COOLIFY_UUID_STAGE" in run
            or "/health/live" in str(step.get("env"))
            or "GHCR" in step["name"]
        ):
            assert step["if"] == "steps.fresh.outputs.backend == 'true'", step["name"]
        if "COOLIFY_UUID_SHOPIFY_STAGE" in run:
            assert step["if"] == "steps.fresh.outputs.shopify == 'true'", step["name"]
    assert steps[-1]["if"] == "steps.fresh.outputs.skipped != ''"


def _run_stale_check(
    tmp_path: Path, compare: dict, want_backend: str, want_shopify: str
) -> tuple[int, dict, str]:
    """The deploy job's stale check, run by bash with a stand-in `gh` that answers the comparison."""
    config = yaml.safe_load(_workflow("stage.yaml"))
    script = config["jobs"]["deploy"]["steps"][0]["run"]
    script = script.replace("${{ github.repository }}", "rextaihq/rext-backend")
    script = script.replace("${{ github.sha }}", SHA)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (tmp_path / "compare.json").write_text(json.dumps(compare), encoding="utf-8")
    gh = bin_dir / "gh"
    gh.write_text(f'#!/bin/sh\ncat "{tmp_path / "compare.json"}"\n', encoding="utf-8")
    gh.chmod(0o755)
    output = tmp_path / "github_output"
    output.write_text("", encoding="utf-8")
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "GITHUB_OUTPUT": str(output),
        "WANT_BACKEND": want_backend,
        "WANT_SHOPIFY": want_shopify,
        "BACKEND_PATHS": config["env"]["BACKEND_PATHS"],
        "SHOPIFY_PATHS": config["env"]["SHOPIFY_PATHS"],
    }
    done = subprocess.run(
        ["bash", "-e", "-c", script], env=env, capture_output=True, text=True, check=False
    )
    outputs = dict(
        line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines() if line
    )
    return done.returncode, outputs, done.stdout


def _ahead(*files: dict) -> dict:
    return {"status": "ahead", "files": list(files)}


needs_jq = pytest.mark.skipif(shutil.which("jq") is None, reason="the step uses jq")


@needs_jq
def test_a_newer_backend_commit_leaves_the_shopify_deploy_to_this_run(tmp_path: Path) -> None:
    # A Shopify run cancelled by a later backend-only push can be re-run: the newer
    # run's filter saw only its own push, so it won't deploy the Shopify app.
    code, outputs, _ = _run_stale_check(
        tmp_path, _ahead({"filename": "src/api/server.py"}), "false", "true"
    )
    assert code == 0
    assert outputs == {"shopify": "true", "skipped": ""}


@needs_jq
def test_a_stale_component_is_skipped_and_the_other_still_deploys(tmp_path: Path) -> None:
    code, outputs, stdout = _run_stale_check(
        tmp_path, _ahead({"filename": "src/api/server.py"}), "true", "true"
    )
    assert code == 0
    assert outputs == {"shopify": "true", "skipped": "backend"}
    assert "touching the backend (src/api/server.py )" in stdout


@needs_jq
def test_nothing_left_is_refused(tmp_path: Path) -> None:
    code, outputs, _ = _run_stale_check(
        tmp_path, _ahead({"filename": "rext/app/routes.tsx"}), "false", "true"
    )
    assert code == 1
    assert outputs == {"skipped": "shopify"}


@needs_jq
def test_a_file_moved_out_of_a_component_counts_against_it(tmp_path: Path) -> None:
    moved = {"filename": "docs/old_service.py", "previous_filename": "src/services/old_service.py"}
    code, outputs, _ = _run_stale_check(tmp_path, _ahead(moved), "true", "false")
    assert code == 1
    assert outputs == {"skipped": "backend"}


@needs_jq
def test_a_comparison_at_the_300_file_limit_is_refused(tmp_path: Path) -> None:
    # GitHub lists at most 300 files: a newer deployable change could be past the list.
    files = [{"filename": f"docs/page-{i}.md"} for i in range(300)]
    code, outputs, stdout = _run_stale_check(tmp_path, _ahead(*files), "true", "true")
    assert code == 1
    assert outputs == {}
    assert "300 or more files" in stdout


@needs_jq
@pytest.mark.parametrize(
    ("compare", "code", "outputs"),
    [
        (
            {"status": "identical", "files": []},
            0,
            {"backend": "true", "shopify": "true", "skipped": ""},
        ),
        (
            _ahead({"filename": "docs/notes.md"}),
            0,
            {"backend": "true", "shopify": "true", "skipped": ""},
        ),
        ({"status": "diverged", "files": []}, 1, {}),
        ({"status": "behind", "files": []}, 1, {}),
    ],
)
def test_the_stage_head_decides(tmp_path: Path, compare: dict, code: int, outputs: dict) -> None:
    assert _run_stale_check(tmp_path, compare, "true", "true")[:2] == (code, outputs)


@pytest.mark.parametrize("name", ["stage.yaml", "production.yaml"])
def test_the_wait_has_a_wall_clock_deadline(name: str) -> None:
    wait = _wait_step(name)
    assert "DEADLINE=$((SECONDS + 900))" in wait["run"]
    assert wait["timeout-minutes"] <= 20


def _shopify_step() -> dict:
    (step,) = [s for s in _jobs("production.yaml")["deploy"]["steps"] if "Shopify App" in s["name"]]
    return step


def _run_shopify_step(tmp_path: Path, uuid: str) -> subprocess.CompletedProcess:
    """Production's Shopify deploy step, with a stand-in `curl` that records it was called."""
    script = _shopify_step()["run"].replace("${{ secrets.COOLIFY_API_URL }}", "https://coolify")
    script = script.replace("${{ secrets.COOLIFY_TOKEN }}", "token")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    curl.write_text(f"#!/bin/sh\ntouch \"{tmp_path / 'called'}\"\nprintf '{{}}\\n200'\n")
    curl.chmod(0o755)
    env = {"PATH": f"{bin_dir}:{os.environ['PATH']}", "SHOPIFY_UUID": uuid}
    return subprocess.run(
        ["bash", "-e", "-c", script], env=env, capture_output=True, text=True, check=False
    )


def test_production_s_shopify_step_reads_its_uuid_from_the_secret() -> None:
    step = _shopify_step()
    assert step["env"] == {"SHOPIFY_UUID": "${{ secrets.COOLIFY_UUID_SHOPIFY }}"}
    assert "secrets.COOLIFY_UUID_SHOPIFY" not in step["run"]


def test_production_skips_the_shopify_app_without_its_secret(tmp_path: Path) -> None:
    # No Coolify resource exists for it yet: a warning, not a red release run.
    done = _run_shopify_step(tmp_path, "")
    assert done.returncode == 0
    assert "::warning::Shopify app not deployed: COOLIFY_UUID_SHOPIFY is not set" in done.stdout
    assert not (tmp_path / "called").exists()


def test_production_deploys_the_shopify_app_once_its_secret_exists(tmp_path: Path) -> None:
    done = _run_shopify_step(tmp_path, "shopify-uuid")
    assert done.returncode == 0
    assert (tmp_path / "called").exists()
    assert "Shopify app deployment triggered" in done.stdout


def test_a_refused_rollback_points_latest_back_at_what_production_runs() -> None:
    # The publish already moved :latest: a later restart pulling it must not roll back.
    deploy = _jobs("production.yaml")["deploy"]
    guard = deploy["steps"][0]["run"]
    assert 'imagetools create -t "$IMAGE:latest" "$IMAGE:sha-$LIVE"' in guard
    assert deploy["permissions"] == {"contents": "read", "packages": "write"}


def test_production_counts_a_newer_commit_that_contains_this_one() -> None:
    # A later run's deploy can land first: the wait accepts a commit ahead of this one.
    run = _wait_step("production.yaml")["run"]
    assert 'compare/$EXPECTED...$RUNNING" --jq .status' in run
    assert '= "ahead" ]' in run


# --- one deploy per merge window (G97, revnix/rext-control#777) -------------------------

# The start of a half hour (00:00:00 UTC on 2026-10-08): the windows are its first ten minutes.
HALF_HOUR = 1_791_417_600


def _window_step() -> dict:
    (step,) = _jobs("production.yaml")["window"]["steps"]
    return step


def _waited(tmp_path: Path, pushed: int | None, now: int) -> list[str]:
    """The window step run by bash `now` seconds into a half hour, for a run created `pushed`
    seconds into it (None: GitHub doesn't answer): the seconds it slept, if it did."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    slept = tmp_path / "slept"
    gh = "exit 1" if pushed is None else f"echo {HALF_HOUR + pushed}"
    stubs = (("date", f"echo {HALF_HOUR + now}"), ("gh", gh), ("sleep", f'echo "$1" >> "{slept}"'))
    for name, body in stubs:
        stub = bin_dir / name
        stub.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        stub.chmod(0o755)
    script = _window_step()["run"]
    script = script.replace("${{ github.repository }}", "rextaihq/rext-backend")
    script = script.replace("${{ github.run_id }}", "1")
    subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script],
        env={"PATH": f"{bin_dir}:{os.environ['PATH']}"},
        check=True,
        capture_output=True,
    )
    return slept.read_text(encoding="utf-8").split() if slept.exists() else []


def test_the_half_hour_the_window_tests_start_from_is_one() -> None:
    assert HALF_HOUR % 1800 == 0


@pytest.mark.parametrize(
    ("pushed", "now", "slept"),
    [
        # Pushed inside a window (minutes 00-09 and 30-39): until its end, and 20 seconds more.
        (0, 0, ["620"]),
        (0, 5, ["615"]),
        (8 * 60, 8 * 60 + 5, ["135"]),
        (599, 600, ["20"]),
        (1800, 1805, ["615"]),
        # Pushed outside one: an urgent fix deploys at once, even when its run starts
        # (or leaves the queue) inside the next window.
        (600, 601, []),
        (15 * 60, 15 * 60 + 5, []),
        (1799, 1800, []),
        (25 * 60, 31 * 60, []),
        # Its window has passed: the run queued behind another, or is run again.
        (599, 700, []),
        (8 * 60, 10 * 60 + 25, []),
        (0, 7200, []),
        # GitHub doesn't say when the run was created: the time now stands in for it.
        (None, 61, ["559"]),
        (None, 700, []),
    ],
)
def test_a_run_pushed_inside_a_merge_window_waits_for_its_end(
    tmp_path: Path, pushed: int | None, now: int, slept: list[str]
) -> None:
    assert _waited(tmp_path, pushed, now) == slept


def test_the_window_is_the_pushs_not_the_runners() -> None:
    # A runner that starts late, or a run that queued, must not move a push into a window.
    step = _window_step()
    assert "actions/runs/${{ github.run_id }}" in step["run"]
    assert ".created_at | fromdateiso8601" in step["run"]
    assert _jobs("production.yaml")["window"]["permissions"] == {"actions": "read"}


def test_only_a_push_waits_for_the_window() -> None:
    # A manual run is asked for now: it never waits.
    assert _window_step()["if"] == "github.event_name == 'push'"


@pytest.mark.parametrize("job", ["docker_job", "docker_shopify"])
def test_the_stale_check_comes_after_the_window(job: str) -> None:
    # The wait is a job of its own, so the stale check (each publisher's first step)
    # reads main once the window has closed, and one run deploys all its merges.
    jobs = _jobs("production.yaml")
    assert set(jobs[job]["needs"]) == {"quality", "window"}
    assert jobs[job]["steps"][0]["name"] == "Refuse a stale run"


def test_the_quality_gate_runs_during_the_wait() -> None:
    jobs = _jobs("production.yaml")
    assert "needs" not in jobs["quality"]
    assert "needs" not in jobs["window"]
