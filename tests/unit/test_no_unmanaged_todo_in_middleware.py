from pathlib import Path

ALLOWED_TODO_PATTERNS = {
    # Keep empty unless a TODO is explicitly approved with tracking metadata.
}


def test_no_unmanaged_todo_markers_in_middleware() -> None:
    middleware_root = Path("src/api/middleware")
    violations: list[str] = []

    for file_path in middleware_root.rglob("*.py"):
        content = file_path.read_text(encoding="utf-8")
        if "TODO:" in content:
            matched_allowlist = any(pattern in content for pattern in ALLOWED_TODO_PATTERNS)
            if not matched_allowlist:
                violations.append(str(file_path))

    assert not violations, "Unmanaged TODO markers found in middleware files: " + ", ".join(
        sorted(violations)
    )
