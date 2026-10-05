"""The image's LangGraph server version is set in one place: langgraph.json's "api_version".

It picks the base image the server comes from. The dev group pins the same langgraph-api for
`langgraph dev`, the committed Dockerfile is generated from langgraph.json, and the CI workflows
and build scripts that still pass --api-version must name the same version.
"""

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVER_PACKAGES = {"langgraph-api", "langgraph-cli", "langgraph-runtime-inmem"}


def _config() -> dict:
    return json.loads((ROOT / "langgraph.json").read_text(encoding="utf-8"))


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _name(requirement: str) -> str:
    return re.split(r"[\[<>=~!; ]", requirement, maxsplit=1)[0].lower()


def test_dev_group_pins_the_server_version_of_the_image() -> None:
    dev = _pyproject()["dependency-groups"]["dev"]
    assert f"langgraph-api=={_config()['api_version']}" in dev


def test_lock_holds_the_server_version_of_the_image() -> None:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    versions = {p["version"] for p in lock["package"] if p["name"] == "langgraph-api"}
    assert versions == {_config()["api_version"]}


def test_server_packages_are_not_runtime_dependencies() -> None:
    # The image's server comes from the base image; installing these from the lock would replace it.
    names = {_name(d) for d in _pyproject()["project"]["dependencies"]}
    assert not names & SERVER_PACKAGES


def test_dockerfile_is_generated_from_langgraph_json() -> None:
    config = _config()
    lines = (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines()
    assert lines[0] == f"FROM langchain/langgraph-api:{config['api_version']}-py3.11-wolfi"
    missing = [line for line in config["dockerfile_lines"] if line not in lines]
    assert not missing, f"regenerate the Dockerfile with `langgraph dockerfile`: {missing}"
    positions = [lines.index(line) for line in config["dockerfile_lines"]]
    assert positions == sorted(positions)


def test_build_commands_name_the_same_server_version() -> None:
    files = sorted((ROOT / ".github" / "workflows").glob("*.y*ml")) + sorted(ROOT.glob("*.sh"))
    pattern = re.compile(r'--api-version[ =]"?([0-9][\w.\-]*)|API_VERSION="([^"$]+)"')
    found = {
        f"{path.name}: {a or b}"
        for path in files
        for a, b in pattern.findall(path.read_text(encoding="utf-8"))
    }
    wrong = sorted(f for f in found if not f.endswith(f": {_config()['api_version']}"))
    assert not wrong, f"these name another server version than langgraph.json: {wrong}"
