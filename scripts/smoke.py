"""The signed-out checks after a deploy: is the API the one just deployed, and does it answer?

    python scripts/smoke.py --api https://api.rext.ai --commit <sha>

What a visitor who has not signed in can ask, and nothing else: only GET requests, no
credentials, nothing written, no generation. Each check is asked once, and once more after
five seconds when the request itself failed (a timeout, a reset): never in a loop. With every
request timing out it still ends inside the three minutes its job is given.

Exit code 1 when a check failed, with each failed check named. Standard library only, so the
workflow runs it with the runner's own Python.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Optional

TIMEOUT_SECONDS = 10
PAUSE_BEFORE_SECOND_ATTEMPT = 5
# A route that needs a session, read-only: asked without one it must not be answered.
PROTECTED_PATH = "/api/v1/subscriptions/current"
REFUSALS = (401, 403, 422)  # 422: the Authorization header is a required field


@dataclass
class Answer:
    status: int
    body: Any  # the parsed JSON, or None when the body is not JSON


class NoAnswer(Exception):
    """The request got no HTTP answer: a timeout, a refused or reset connection."""


def get(url: str) -> Answer:
    """One GET without credentials. An HTTP error status is an answer, not an exception."""
    request = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    except (OSError, ValueError) as error:  # URLError and timeouts are OSErrors
        raise NoAnswer(type(error).__name__) from error
    try:
        body = json.loads(raw)
    except ValueError:
        body = None
    return Answer(status, body)


def _field(body: Any, *path: str) -> Any:
    for key in path:
        body = body.get(key) if isinstance(body, dict) else None
    return body


def check_live(answer: Answer, commit: Optional[str]) -> Optional[str]:
    if answer.status != 200 or _field(answer.body, "status") != "alive":
        return f"answered {answer.status}, not alive"
    running = _field(answer.body, "commit")
    if commit and running != commit:
        return f"runs {running}, not {commit}"
    return None


def check_ready(answer: Answer) -> Optional[str]:
    if answer.status == 200 and _field(answer.body, "status") == "ready":
        return None
    checks = _field(answer.body, "checks")
    not_ready = sorted(
        name
        for name, state in (checks if isinstance(checks, dict) else {}).items()
        if not str(state).startswith(("ready", "not_configured"))
    )
    return f"answered {answer.status}, not ready" + (
        f" ({', '.join(not_ready)})" if not_ready else ""
    )


def check_refused(answer: Answer) -> Optional[str]:
    if answer.status in REFUSALS and _field(answer.body, "data") is None:
        return None
    return f"answered {answer.status} to a call without a session"


def check_plans(answer: Answer) -> Optional[str]:
    plans = _field(answer.body, "data", "plans")
    if answer.status == 200 and isinstance(plans, list) and plans:
        return None
    return f"answered {answer.status} with no plans"


def check_banner(answer: Answer) -> Optional[str]:
    # Public, and read by every signed-in page: with no incident it says `active: false`.
    if answer.status == 200 and isinstance(_field(answer.body, "data", "active"), bool):
        return None
    return f"answered {answer.status} without saying whether a banner is showing"


def checks(commit: Optional[str]) -> list[tuple[str, str, Callable[[Answer], Optional[str]]]]:
    """Each check: its name, its path, and what is wrong with the answer (None when right)."""
    return [
        ("the API runs the deployed commit", "/health/live", lambda a: check_live(a, commit)),
        ("the API is ready", "/health/ready", check_ready),
        ("a call without a session is refused", PROTECTED_PATH, check_refused),
        ("the plans are served", "/api/v1/plans", check_plans),
        ("the incident banner's read answers", "/api/v1/status/banner", check_banner),
    ]


def ask(url: str, fetch: Callable[[str], Answer], sleep: Callable[[float], None]) -> Answer:
    """The answer, asked for a second time only when the first request got none."""
    try:
        return fetch(url)
    except NoAnswer:
        sleep(PAUSE_BEFORE_SECOND_ATTEMPT)
        return fetch(url)


def run(
    api: str,
    commit: Optional[str],
    fetch: Callable[[str], Answer] = get,
    sleep: Callable[[float], None] = time.sleep,
    say: Callable[[str], None] = print,
) -> list[str]:
    """Run every check and return the names of those that failed."""
    failed = []
    for name, path, wrong in checks(commit):
        try:
            problem = wrong(ask(api.rstrip("/") + path, fetch, sleep))
        except NoAnswer as error:
            problem = f"no answer, twice ({error})"
        if problem:
            failed.append(name)
            say(f"FAIL  {name}: {path} {problem}")
        else:
            say(f"pass  {name}")
    return failed


def main(argv: Optional[list[str]] = None, **how: Any) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", required=True, help="the API's address, without a path")
    parser.add_argument("--commit", help="the commit /health/live must report")
    args = parser.parse_args(argv)

    failed = run(args.api, args.commit, **how)
    if failed:
        print(f"::error::Smoke test failed on {args.api}: {'; '.join(failed)}")
        return 1
    print(f"Smoke test passed on {args.api}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
