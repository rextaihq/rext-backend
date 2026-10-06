"""The image's LangGraph server version is set in one place: langgraph.json's "api_version".

It picks the base image the server comes from. The dev group pins the same langgraph-api for
`langgraph dev`, and the committed Dockerfile is generated from langgraph.json. The CI workflows run
`langgraph build` without --api-version, so they read it from there too; the manual build scripts that
still pass one must name the same version.
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
    from langgraph_cli.config import config_to_docker, validate_config_file

    path = ROOT / "langgraph.json"
    generated, _ = config_to_docker(path, validate_config_file(path))
    committed = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    # The generator names the package folder after the checkout's folder; CI's is rext-backend.
    def normalise(text: str) -> str:
        return re.sub(r"/deps/[\w.\-]+", "/deps/<checkout>", text).strip()

    assert normalise(committed) == normalise(generated), (
        "the Dockerfile is out of date: run `langgraph dockerfile Dockerfile` in a checkout "
        "folder named rext-backend"
    )
    assert committed.startswith(f"FROM langchain/langgraph-api:{_config()['api_version']}-")


def test_ci_builds_take_the_server_version_from_langgraph_json() -> None:
    workflows = sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))
    passing = [p.name for p in workflows if "--api-version" in p.read_text(encoding="utf-8")]
    assert not passing, (
        f"these pass --api-version; langgraph.json's api_version is the one place: {passing}"
    )


def test_build_scripts_name_the_same_server_version() -> None:
    pattern = re.compile(r'--api-version[ =]"?([0-9][\w.\-]*)|API_VERSION="([^"$]+)"')
    found = {
        f"{path.name}: {a or b}"
        for path in sorted(ROOT.glob("*.sh"))
        for a, b in pattern.findall(path.read_text(encoding="utf-8"))
    }
    wrong = sorted(f for f in found if not f.endswith(f": {_config()['api_version']}"))
    assert not wrong, f"these name another server version than langgraph.json: {wrong}"
