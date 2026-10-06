"""A deploy pulls the new image and proves the server runs the commit it built.

The backend is a Coolify Service: /api/v1/deploy only starts it with the images it has, so the
workflows restart it with latest=true. CI writes the commit into src/api/build_commit.txt before
`langgraph build`; /health/live reports it, and the deploy job waits for it.
"""

import re
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


@pytest.mark.parametrize(
    ("name", "uuid"),
    [("stage.yaml", "COOLIFY_UUID_STAGE"), ("production.yaml", "COOLIFY_UUID_PROD")],
)
def test_backend_deploy_restarts_with_the_latest_images(name: str, uuid: str) -> None:
    text = _workflow(name)
    assert f"/api/v1/services/${{{{ secrets.{uuid} }}}}/restart" in text
    assert '--url-query "latest=true"' in text
    # /api/v1/deploy only starts a Service with the images it already has.
    assert not re.search(
        rf"api/v1/deploy\"[^\n]*\n[^\n]*uuid=\$\{{\{{ secrets\.{uuid} \}}\}}", text
    )


@pytest.mark.parametrize("name", ["stage.yaml", "production.yaml"])
def test_deploy_waits_for_the_running_commit(name: str) -> None:
    text = _workflow(name)
    assert "/health/live" in text
    assert "EXPECTED: ${{ github.sha }}" in text
    assert "jq -r '.commit" in text


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
def test_a_stale_rerun_is_refused_first(name: str, branch: str, job: str) -> None:
    # A re-run keeps its old commit; publishing or deploying it would roll the server back.
    first = _jobs(name)[job]["steps"][0]
    assert first["if"] == "github.run_attempt != '1'"
    assert f"commits/{branch}" in first["run"]
    assert '"$HEAD" != "${{ github.sha }}"' in first["run"]


@pytest.mark.parametrize("name", ["stage.yaml", "production.yaml"])
def test_the_wait_has_a_wall_clock_deadline(name: str) -> None:
    (wait,) = [s for s in _jobs(name)["deploy"]["steps"] if "/health/live" in str(s.get("env"))]
    assert "DEADLINE=$((SECONDS + 900))" in wait["run"]
    assert wait["timeout-minutes"] <= 20
