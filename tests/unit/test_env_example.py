"""`.env.example` lists every environment name the backend reads, and no other (G16).

scripts/env_example.py generates the settings' part from the settings classes and the code's direct
reads; its check also refuses a hand-written name nothing reads. No database, no `.env`.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_env_example_matches_the_code():
    result = subprocess.run(
        [sys.executable, "scripts/env_example.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
