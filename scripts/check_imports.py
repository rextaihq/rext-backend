#!/usr/bin/env python3
"""Fail if any module-level import cannot be resolved.

Catches the ModuleNotFoundError class of bug *before* it reaches an image.
A missing module referenced at module scope crashes the app on boot, so this
runs as a blocking CI job and as a pre-commit hook.

Only module-level (depth 0) imports are checked. Imports nested inside
`if TYPE_CHECKING:`, `try/except ImportError`, or a function body are
conditional by design and are deliberately skipped.

With --tracked, modules resolve against git's index rather than the
filesystem. That is the mode the pre-commit hook uses: a module sitting on
your disk but never `git add`-ed does not exist for anyone else, and that is
precisely how a missing task module shipped a crash-looping image.

Usage: python scripts/check_imports.py [--tracked] [root ...]
Exit code 0 = clean, 1 = unresolvable imports found.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import warnings

warnings.simplefilter("ignore")

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ROOTS = ("src", "tests")
LOCAL_ROOTS = {"src", "tests"}
SKIP_DIRS = {
    "__pycache__",
    ".venv",
    "venv",
    ".git",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
}


def tracked_paths() -> set[str]:
    """Every path in git's index -- i.e. what the commit will actually contain."""
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout
    return {line.strip() for line in out.splitlines() if line.strip()}


def target_path(node: ast.ImportFrom | ast.Import, name: str | None, rel_file: str) -> str | None:
    """Repo-relative path (no extension) that an import should resolve to.

    Relative imports are resolved against the importing file's own directory
    rather than by rebuilding a dotted package name. A directory whose name
    contains a dot cannot round-trip through dotted form, and resolving by
    path stays correct regardless.
    """
    level = getattr(node, "level", 0) or 0
    if level == 0:
        if not name or name.split(".")[0] not in LOCAL_ROOTS:
            return None
        return name.replace(".", "/")

    base = os.path.dirname(rel_file)
    for _ in range(level - 1):
        base = os.path.dirname(base)
    if not base:
        return None
    return f"{base}/{name.replace('.', '/')}" if name else base


def display(node: ast.ImportFrom | ast.Import, name: str | None) -> str:
    level = getattr(node, "level", 0) or 0
    return ("." * level) + (name or "")


def module_level_imports(tree: ast.Module):
    """Yield (node, dotted_name) for imports that execute at import time."""
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            yield node, node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield node, alias.name


def main(argv: list[str]) -> int:
    args = argv[1:]
    use_index = "--tracked" in args
    roots = [a for a in args if not a.startswith("-")] or list(DEFAULT_ROOTS)

    index = tracked_paths() if use_index else None

    def exists(rel: str) -> bool:
        if index is not None:
            return f"{rel}.py" in index or f"{rel}/__init__.py" in index
        base = os.path.join(REPO, *rel.split("/"))
        return os.path.isfile(base + ".py") or os.path.isfile(os.path.join(base, "__init__.py"))

    failures: list[tuple[str, int, str]] = []
    checked = files = 0

    for root in roots:
        for dirpath, dirnames, filenames in os.walk(os.path.join(REPO, root)):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in sorted(filenames):
                if not name.endswith(".py"):
                    continue
                path = os.path.join(dirpath, name)
                rel_file = os.path.relpath(path, REPO).replace(os.sep, "/")
                if index is not None and rel_file not in index:
                    continue  # untracked scratch file: not part of the commit
                files += 1
                try:
                    with open(path, encoding="utf-8") as fh:
                        tree = ast.parse(fh.read(), path)
                except SyntaxError as exc:
                    failures.append((rel_file, exc.lineno or 0, f"syntax error: {exc.msg}"))
                    continue
                for node, mod in module_level_imports(tree):
                    rel = target_path(node, mod, rel_file)
                    if rel is None:
                        continue
                    checked += 1
                    if not exists(rel):
                        failures.append((rel_file, node.lineno, display(node, mod)))

    scope = "tracked in git" if use_index else "on disk"
    print(f"checked {checked} module-level first-party imports across {files} files ({scope})")
    if not failures:
        print("OK: every module-level import resolves")
        return 0

    print(f"\nFAILED: {len(failures)} unresolvable module-level import(s)\n")
    for rel_file, lineno, mod in failures:
        print(f"  {rel_file}:{lineno}: cannot resolve '{mod}'")
    print(
        "\nA module-level import that does not resolve crashes the app on boot.\n"
        "Either add the missing module, or remove/relocate the import.\n"
        "If the file is genuinely absent from git, check .gitignore -- it may be\n"
        "silently excluding it from `git add`."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
