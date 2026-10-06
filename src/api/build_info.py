"""The commit an image was built from, so a deploy can prove the new code is running.

The CI workflows write the commit's SHA to `build_commit.txt` beside this module just before
`langgraph build`, which copies it into the image. `/health/live` reports it, and the deploy
job waits until it shows the commit it pushed. Outside a CI image the file is absent.
"""

import re
from pathlib import Path

COMMIT_FILE = Path(__file__).with_name("build_commit.txt")
UNKNOWN = "unknown"

_SHA = re.compile(r"[0-9a-f]{40}")


def read_build_commit(path: Path = COMMIT_FILE) -> str:
    """The full SHA in `path`, or "unknown" when the file is missing or holds anything else."""
    try:
        commit = path.read_text(encoding="utf-8").strip()
    except OSError:
        return UNKNOWN
    return commit if _SHA.fullmatch(commit) else UNKNOWN


# Read once at import (server start-up), so the health route never touches the disk.
BUILD_COMMIT = read_build_commit()
