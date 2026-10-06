#!/usr/bin/env python3
"""Export the API's OpenAPI spec, the dashboard's contract (rext-admin generates its types from it).

    uv run python scripts/export_openapi.py [--strict] [output.json]

The output defaults to openapi.json at the repository root. --strict fails on a duplicate
operation id (two routes on one function), which a typed client cannot be generated from;
CI runs it that way (.github/workflows/pr-checks.yaml) and keeps the spec as an artifact.
"""

import json
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main(argv: list[str]) -> int:
    strict = "--strict" in argv
    paths = [arg for arg in argv if not arg.startswith("--")]
    output = Path(paths[0]) if paths else ROOT / "openapi.json"

    if strict:
        warnings.filterwarnings("error", message="Duplicate Operation ID")

    from src.api.server import app

    try:
        spec = app.openapi()
    except UserWarning as exc:
        print(f"OpenAPI spec refused: {exc}", file=sys.stderr)
        return 1

    output.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"OpenAPI spec written to {output} ({len(spec.get('paths', {}))} paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
