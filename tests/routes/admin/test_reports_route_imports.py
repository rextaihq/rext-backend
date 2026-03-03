from pathlib import Path


def test_reports_routes_has_no_inline_json_import() -> None:
    """Ensure json is not imported inline in reports_routes.py."""
    source = Path("src/api/routes/admin/reports_routes.py").read_text()
    # Check for indented 'import json' which indicates function-local scope
    assert "\n        import json\n" not in source
    # Ensure it's imported at top level (no indentation)
    assert "\nimport json\n" in source or "import json" in source.splitlines()[0:20]
