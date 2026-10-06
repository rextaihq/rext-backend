"""
Route Decorator Integrity Check Script
=======================================
Fails fast on:
  - Unresolved merge conflict markers
  - Placeholder comments that indicate incomplete code
  - Python syntax errors (catches incomplete except blocks and other parse failures)

Run this in CI before deployment:
    python scripts/check_route_decorator_integrity.py

Exit codes:
    0  - All checks passed
    1  - A blocked token or syntax error was found (printed to stderr)
"""

from pathlib import Path

# Files to guard. Extend this list if more shared decorators are added.
TARGETS = [
    Path("src/utils/route_decorators.py"),
]

# Tokens that must never appear in production code.
# These indicate merge conflicts, incomplete pastes, or placeholder stubs.
BLOCKED_TOKENS = [
    "<<<<<<<",
    "=======",
    ">>>>>>>",
    "# existing code...",
    "# TODO: implement",
    "# placeholder",
]


def check_file(target: Path) -> list[str]:
    """Return a list of error messages for the given file, or empty list if clean."""
    errors: list[str] = []

    if not target.exists():
        errors.append(f"File not found: {target}")
        return errors

    text = target.read_text(encoding="utf-8")

    # 1. Blocked token scan
    for token in BLOCKED_TOKENS:
        if token in text:
            errors.append(f"Blocked token {token!r} found in {target}")

    # 2. Python syntax / parse check
    # compile() raises SyntaxError on incomplete except blocks and all other
    # parse-time failures, catching regressions before they reach the runtime.
    try:
        compile(text, str(target), "exec")
    except SyntaxError as exc:
        errors.append(f"Syntax error in {target}: {exc}")

    return errors


def main() -> None:
    all_errors: list[str] = []

    for target in TARGETS:
        file_errors = check_file(target)
        all_errors.extend(file_errors)

    if all_errors:
        for err in all_errors:
            print(f"[FAIL] {err}")
        raise SystemExit(1)

    print("route_decorators integrity check passed")


if __name__ == "__main__":
    main()
