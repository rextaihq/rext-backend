#!/usr/bin/env python3
"""
RBAC Route Audit Script
=======================

Scans all FastAPI route files in the backend to extract:
- Route path and HTTP method
- Permission decorators (@require_permissions)
- Workspace-scoped flag
- Function name and file location

Outputs:
- route-inventory.json: Machine-readable full inventory
- backend-route-audit-report.md: Human-readable audit report

Usage:
    python scripts/audit_routes.py
"""

import ast
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class RouteAuditor:
    """Audits FastAPI routes for RBAC permission enforcement."""

    def __init__(self, routes_dir: str):
        self.routes_dir = Path(routes_dir)
        self.routes: List[Dict[str, Any]] = []
        self.stats = {
            "total_routes": 0,
            "protected_routes": 0,
            "unprotected_routes": 0,
            "workspace_scoped": 0,
            "by_method": defaultdict(int),
            "by_category": defaultdict(int),
        }

    def scan_all_routes(self) -> None:
        """Scan all Python files in routes directory."""
        print(f"🔍 Scanning routes in: {self.routes_dir}")

        for py_file in self.routes_dir.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue

            try:
                self._scan_file(py_file)
            except Exception as e:
                print(f"⚠️  Error scanning {py_file}: {e}")

    def _scan_file(self, file_path: Path) -> None:
        """Scan a single Python file for routes."""
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read(), filename=str(file_path))
            except SyntaxError as e:
                print(f"⚠️  Syntax error in {file_path}: {e}")
                return

        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) or isinstance(node, ast.FunctionDef):
                route_info = self._extract_route_info(node, file_path)
                if route_info:
                    self.routes.append(route_info)

    def _extract_route_info(
        self, func_node: ast.FunctionDef, file_path: Path
    ) -> Optional[Dict[str, Any]]:
        """Extract route information from a function definition."""
        decorators = self._get_decorators(func_node)

        # Look for router decorators like @router.get, @router.post, etc.
        route_decorator = None
        for dec in decorators:
            if self._is_route_decorator(dec):
                route_decorator = dec
                break

        if not route_decorator:
            return None

        # Extract HTTP method and path
        method, path = self._parse_route_decorator(route_decorator)
        if not method or not path:
            return None

        # Check for @require_permissions decorator
        permission_info = self._extract_permission_info(decorators)

        # Determine category from file path
        category = self._get_category(file_path)

        route_info = {
            "path": path,
            "method": method.upper(),
            "function": func_node.name,
            "file": str(file_path.relative_to(self.routes_dir.parent)),
            "line": func_node.lineno,
            "category": category,
            "has_permission_check": permission_info["has_check"],
            "permissions": permission_info["permissions"],
            "workspace_scoped": permission_info["workspace_scoped"],
            "require_all": permission_info["require_all"],
            "is_admin_only": self._has_admin_dependency(decorators, func_node),
        }

        # Update statistics
        self._update_stats(route_info)

        return route_info

    def _get_decorators(self, func_node: ast.FunctionDef) -> List[ast.expr]:
        """Get all decorators from a function."""
        return func_node.decorator_list

    def _is_route_decorator(self, decorator: ast.expr) -> bool:
        """Check if decorator is a route decorator (e.g., @router.get)."""
        if isinstance(decorator, ast.Call):
            decorator = decorator.func

        if isinstance(decorator, ast.Attribute):
            if isinstance(decorator.value, ast.Name):
                # @router.get, @router.post, etc.
                if decorator.value.id == "router":
                    return decorator.attr in ["get", "post", "put", "patch", "delete"]

        return False

    def _parse_route_decorator(self, decorator: ast.expr) -> Tuple[Optional[str], Optional[str]]:
        """Parse route decorator to extract HTTP method and path."""
        if isinstance(decorator, ast.Call):
            # Get method from decorator function name
            if isinstance(decorator.func, ast.Attribute):
                method = decorator.func.attr

                # Get path from first argument
                if decorator.args and isinstance(decorator.args[0], ast.Constant):
                    path = decorator.args[0].value
                    return method, path

        return None, None

    def _extract_permission_info(self, decorators: List[ast.expr]) -> Dict[str, Any]:
        """Extract permission information from decorators."""
        info = {
            "has_check": False,
            "permissions": [],
            "workspace_scoped": False,
            "require_all": True,
        }

        for dec in decorators:
            if isinstance(dec, ast.Call):
                if isinstance(dec.func, ast.Name):
                    if dec.func.id == "require_permissions":
                        info["has_check"] = True

                        # Extract permissions from first argument
                        if dec.args:
                            perms = self._extract_permissions_arg(dec.args[0])
                            info["permissions"] = perms

                        # Extract keyword arguments
                        for keyword in dec.keywords:
                            if keyword.arg == "workspace_scoped":
                                if isinstance(keyword.value, ast.Constant):
                                    info["workspace_scoped"] = keyword.value.value
                            elif keyword.arg == "require_all":
                                if isinstance(keyword.value, ast.Constant):
                                    info["require_all"] = keyword.value.value

        return info

    def _extract_permissions_arg(self, arg: ast.expr) -> List[str]:
        """Extract permission names from decorator argument."""
        permissions = []

        if isinstance(arg, ast.Constant):
            # Single permission string
            permissions.append(arg.value)
        elif isinstance(arg, ast.List):
            # List of permissions
            for elt in arg.elts:
                if isinstance(elt, ast.Constant):
                    permissions.append(elt.value)

        return permissions

    def _has_admin_dependency(self, decorators: List[ast.expr], func_node: ast.FunctionDef) -> bool:
        """Check if function has is_admin dependency."""
        # Check function parameters for Depends(is_admin)
        for arg in func_node.args.args:
            if arg.annotation and isinstance(arg.annotation, ast.Call):
                if isinstance(arg.annotation.func, ast.Name):
                    if arg.annotation.func.id == "Depends":
                        if arg.annotation.args:
                            if isinstance(arg.annotation.args[0], ast.Name):
                                if arg.annotation.args[0].id == "is_admin":
                                    return True

        return False

    def _get_category(self, file_path: Path) -> str:
        """Determine route category from file path."""
        parts = file_path.relative_to(self.routes_dir).parts

        if len(parts) > 0:
            return parts[0]  # First directory name (e.g., "content", "admin", "workspaces")

        return "other"

    def _update_stats(self, route_info: Dict[str, Any]) -> None:
        """Update statistics based on route info."""
        self.stats["total_routes"] += 1
        self.stats["by_method"][route_info["method"]] += 1
        self.stats["by_category"][route_info["category"]] += 1

        if route_info["has_permission_check"] or route_info["is_admin_only"]:
            self.stats["protected_routes"] += 1
        else:
            self.stats["unprotected_routes"] += 1

        if route_info["workspace_scoped"]:
            self.stats["workspace_scoped"] += 1

    def generate_json_report(self, output_path: str) -> None:
        """Generate machine-readable JSON report."""
        report = {
            "generated_at": "2025-10-24",
            "statistics": dict(self.stats),
            "routes": sorted(self.routes, key=lambda r: (r["category"], r["path"], r["method"])),
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        print(f"✅ JSON report saved to: {output_path}")

    def generate_markdown_report(self, output_path: str) -> None:
        """Generate human-readable Markdown report."""
        lines = [
            "# Backend Route Audit Report",
            "",
            "**Generated:** 2025-10-24",
            f"**Routes Scanned:** {self.stats['total_routes']}",
            "",
            "---",
            "",
            "## Executive Summary",
            "",
            f"- **Total Routes:** {self.stats['total_routes']}",
            f"- **Protected Routes:** {self.stats['protected_routes']} ({self._percentage(self.stats['protected_routes'], self.stats['total_routes'])}%)",
            f"- **Unprotected Routes:** {self.stats['unprotected_routes']} ({self._percentage(self.stats['unprotected_routes'], self.stats['total_routes'])}%)",
            f"- **Workspace-Scoped Routes:** {self.stats['workspace_scoped']}",
            "",
            "### Protection Status",
            "",
            "```",
            f"✅ Protected:    {self.stats['protected_routes']:3d} routes",
            f"❌ Unprotected:  {self.stats['unprotected_routes']:3d} routes",
            "```",
            "",
            "---",
            "",
            "## Routes by HTTP Method",
            "",
        ]

        for method, count in sorted(self.stats["by_method"].items()):
            lines.append(f"- **{method}:** {count} routes")

        lines.extend(
            [
                "",
                "---",
                "",
                "## Routes by Category",
                "",
            ]
        )

        for category, count in sorted(self.stats["by_category"].items(), key=lambda x: -x[1]):
            category_routes = [r for r in self.routes if r["category"] == category]
            protected = sum(
                1 for r in category_routes if r["has_permission_check"] or r["is_admin_only"]
            )
            lines.append(
                f"- **{category}:** {count} routes ({protected} protected, {count - protected} unprotected)"
            )

        lines.extend(
            [
                "",
                "---",
                "",
                "## ❌ UNPROTECTED ROUTES (CRITICAL)",
                "",
                "These routes lack `@require_permissions` decorator and should be reviewed:",
                "",
            ]
        )

        unprotected = [
            r for r in self.routes if not r["has_permission_check"] and not r["is_admin_only"]
        ]

        if unprotected:
            for route in sorted(unprotected, key=lambda r: (r["category"], r["path"])):
                lines.append(f"### {route['method']} {route['path']}")
                lines.append(f"- **Category:** {route['category']}")
                lines.append(f"- **Function:** `{route['function']}`")
                lines.append(f"- **File:** `{route['file']}:{route['line']}`")
                lines.append("- **Status:** ❌ No permission check")
                lines.append("")
        else:
            lines.append("✅ **All routes are protected!**")
            lines.append("")

        lines.extend(
            [
                "---",
                "",
                "## ✅ PROTECTED ROUTES",
                "",
                "Routes with proper permission checks:",
                "",
            ]
        )

        protected = [r for r in self.routes if r["has_permission_check"] or r["is_admin_only"]]

        # Group by category
        by_category = defaultdict(list)
        for route in protected:
            by_category[route["category"]].append(route)

        for category in sorted(by_category.keys()):
            lines.append(f"### Category: {category}")
            lines.append("")

            for route in sorted(by_category[category], key=lambda r: (r["path"], r["method"])):
                perms_str = (
                    ", ".join(f"`{p}`" for p in route["permissions"])
                    if route["permissions"]
                    else "N/A"
                )
                scope = "✅ Workspace-scoped" if route["workspace_scoped"] else "Global"
                admin = " (Admin Only)" if route["is_admin_only"] else ""

                lines.append(f"**{route['method']} {route['path']}**{admin}")
                lines.append(f"- Permissions: {perms_str}")
                lines.append(f"- Scope: {scope}")
                lines.append(f"- File: `{route['file']}:{route['line']}`")
                lines.append("")

        lines.extend(
            [
                "---",
                "",
                "## Recommendations",
                "",
                "### Immediate Actions (P0)",
                "",
            ]
        )

        if unprotected:
            lines.append(
                f"1. **Review {len(unprotected)} unprotected routes** - Add `@require_permissions` decorator"
            )
            lines.append(
                "2. **Verify critical routes** (subscription, billing, workspace settings)"
            )
            lines.append("3. **Test with different user roles** to ensure access control works")
        else:
            lines.append("1. ✅ All routes have permission checks - Continue to Phase 1, Task 1.2")

        lines.extend(
            [
                "",
                "### Next Steps",
                "",
                "1. Review unprotected routes and add appropriate decorators",
                "2. Map each route to required permissions (Task 1.1.2)",
                "3. Create automated verification script (Task 1.4)",
                "",
                "---",
                "",
                "**End of Report**",
            ]
        )

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print(f"✅ Markdown report saved to: {output_path}")

    def _percentage(self, part: int, total: int) -> str:
        """Calculate percentage as string."""
        if total == 0:
            return "0.0"
        return f"{(part / total * 100):.1f}"

    def print_summary(self) -> None:
        """Print summary to console."""
        print("\n" + "=" * 60)
        print("📊 ROUTE AUDIT SUMMARY")
        print("=" * 60)
        print(f"Total Routes:        {self.stats['total_routes']}")
        print(
            f"Protected:           {self.stats['protected_routes']} ({self._percentage(self.stats['protected_routes'], self.stats['total_routes'])}%)"
        )
        print(
            f"Unprotected:         {self.stats['unprotected_routes']} ({self._percentage(self.stats['unprotected_routes'], self.stats['total_routes'])}%)"
        )
        print(f"Workspace-Scoped:    {self.stats['workspace_scoped']}")
        print("=" * 60)
        print("\n📁 By Category:")
        for category, count in sorted(self.stats["by_category"].items(), key=lambda x: -x[1]):
            print(f"  {category:20s} {count:3d} routes")
        print("=" * 60 + "\n")


def main():
    """Main execution function."""
    # Determine routes directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    routes_dir = project_root / "src" / "api" / "routes"

    if not routes_dir.exists():
        print(f"❌ Routes directory not found: {routes_dir}")
        return

    # Create auditor and scan
    auditor = RouteAuditor(str(routes_dir))
    auditor.scan_all_routes()

    # Generate reports
    output_dir = project_root.parent  # Output to project root (rext/)
    json_output = output_dir / "route-inventory.json"
    md_output = output_dir / "backend-route-audit-report.md"

    auditor.generate_json_report(str(json_output))
    auditor.generate_markdown_report(str(md_output))

    # Print summary
    auditor.print_summary()

    # Return exit code based on unprotected routes
    if auditor.stats["unprotected_routes"] > 0:
        print(f"⚠️  WARNING: {auditor.stats['unprotected_routes']} unprotected routes found!")
        print("   Review backend-route-audit-report.md for details.")
    else:
        print("✅ SUCCESS: All routes have permission checks!")


if __name__ == "__main__":
    main()
