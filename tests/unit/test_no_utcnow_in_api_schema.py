from pathlib import Path


def test_no_datetime_utcnow_in_api_schema_package() -> None:
    schema_root = Path("src/api/schema")
    violating_files: list[str] = []

    for file_path in schema_root.rglob("*.py"):
        content = file_path.read_text(encoding="utf-8")
        if "datetime.utcnow(" in content:
            violating_files.append(str(file_path))

    assert not violating_files, (
        "Deprecated datetime.utcnow() usage found in API schema files: "
        + ", ".join(violating_files)
    )