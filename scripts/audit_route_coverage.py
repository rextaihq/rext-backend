"""
Route Permission Coverage Audit Script

This script audits all FastAPI routes to ensure they have proper permission protection.
It identifies unprotected routes and generates a comprehensive coverage report.

Usage:
    python scripts/audit_route_coverage.py
    python scripts/audit_route_coverage.py --output-format json
    python scripts/audit_route_coverage.py --show-protected

Requirements:
    - Must be run from rext-backend directory
    - Python 3.11+

Reference:
    See roles-permissions-improvement-plan.md for RBAC implementation details
"""

import ast
import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Set
from collections import defaultdict
from datetime import datetime


class RouteAuditor:
    """Audits FastAPI routes for permission protection coverage."""

    def __init__(self, routes_dir: str = "src/api/routes"):
        self.routes_dir = Path(routes_dir)
        self.protected_routes = []
        self.unprotected_routes = []
        self.public_routes = []
        self.route_stats = {
            "total_files": 0,
            "total_routes": 0,
            "protected_routes": 0,
            "unprotected_routes": 0,
            "public_routes": 0,
            "coverage_percentage": 0.0
        }

        # Public routes that don't need protection
        # These are exact matches or startswith patterns
        self.PUBLIC_ROUTE_EXACT = [
            "",  # Root route ""
            "/",  # Exact root "/"
            "/status",  # Status endpoints
            "/health",  # Health check
            "/docs",
            "/redoc",
            "/openapi.json",
        ]

        # Auth routes (don't need permission checks - have their own auth)
        self.PUBLIC_AUTH_ROUTES = [
            "/register",
            "/register-with-invitation",
            "/login",
            "/logout",
            "/refresh",
            "/verify-email",
            "/resend-verification",
            "/forgot-password",
            "/reset-password",
            "/oauth/login",
            "/oauth/link",
        ]

        # Routes that start with these patterns
        self.PUBLIC_STARTSWITH = [
            "/webhooks/",  # Webhooks have signature verification
            "/oauth/",  # OAuth routes
        ]

        # Webhook-specific routes (external services with signature verification)
        self.PUBLIC_WEBHOOK_ROUTES = [
            "/resend",  # Resend email webhook
            "/lemonsqueezy",  # LemonSqueezy payment webhook
        ]

        # Public routes for specific features
        self.PUBLIC_ROUTES_BY_FEATURE = [
            # Invitation tokens (token-based auth, public by design)
            "/{token}/validate",  # Workspace invitations
            "/{token}/accept",  # Workspace invitations
            "/{token}/decline",  # Admin invitations

            # Health check endpoints (monitoring)
            "/payment",  # Health check
            "/payment/quick",  # Health check

            # Public subscription endpoints
            "/public",  # Public subscription plans
            "/validate",  # License validation (public for external systems)

            # Email unsubscribe (email link)
            "/unsubscribe",  # Email preferences

            # Development/testing
            "/test",  # SSE test endpoint
        ]

    def is_public_route(self, route_path: str) -> bool:
        """Check if a route is public (doesn't need protection)."""
        # Check exact matches
        if route_path in self.PUBLIC_ROUTE_EXACT:
            return True

        # Check auth routes
        if route_path in self.PUBLIC_AUTH_ROUTES:
            return True

        # Check startswith patterns
        for pattern in self.PUBLIC_STARTSWITH:
            if route_path.startswith(pattern):
                return True

        # Check feature-based public routes
        if route_path in self.PUBLIC_ROUTES_BY_FEATURE:
            return True

        # Check webhook-specific routes
        if route_path in self.PUBLIC_WEBHOOK_ROUTES:
            return True

        return False

    def extract_routes_from_file(self, file_path: Path) -> List[Dict]:
        """Extract all route definitions from a Python file."""
        # Skip directories
        if file_path.is_dir():
            return []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"⚠️  Error reading {file_path}: {e}")
            return []

        routes = []

        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            print(f"⚠️  Syntax error in {file_path}: {e}")
            return []

        # Find all function definitions with route decorators
        # Check both FunctionDef and AsyncFunctionDef
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                route_info = self._extract_route_info(node, content, file_path)
                if route_info:
                    routes.append(route_info)

        return routes

    def _extract_route_info(
        self,
        func_node: ast.FunctionDef,
        content: str,
        file_path: Path
    ) -> Dict:
        """Extract route information from a function definition."""
        route_decorator = None
        http_method = None
        route_path = None
        has_permission_check = False
        permission_decorator = None

        # Check decorators
        for decorator in func_node.decorator_list:
            decorator_str = ast.unparse(decorator)

            # Check for route decorators (@router.get, @router.post, etc.)
            if "router." in decorator_str:
                route_decorator = decorator_str
                if ".get(" in decorator_str:
                    http_method = "GET"
                elif ".post(" in decorator_str:
                    http_method = "POST"
                elif ".put(" in decorator_str:
                    http_method = "PUT"
                elif ".patch(" in decorator_str:
                    http_method = "PATCH"
                elif ".delete(" in decorator_str:
                    http_method = "DELETE"

                # Extract route path from decorator
                if isinstance(decorator, ast.Call) and decorator.args:
                    if isinstance(decorator.args[0], ast.Constant):
                        route_path = decorator.args[0].value

            # Check for permission decorators
            if "require_permissions" in decorator_str:
                has_permission_check = True
                permission_decorator = decorator_str

        # If no route decorator found, not a route
        if not route_decorator or not http_method:
            return None

        # Check function body for permission checks
        has_depends_permission = self._check_function_for_permissions(func_node)
        has_is_admin = self._check_function_for_admin(func_node)
        has_current_user = self._check_function_for_current_user(func_node)

        if has_depends_permission or has_is_admin or has_current_user:
            has_permission_check = True

        return {
            "file": str(file_path.relative_to(self.routes_dir.parent.parent)),
            "function": func_node.name,
            "method": http_method,
            "path": route_path if route_path is not None else "Unknown",
            "has_permission": has_permission_check,
            "permission_type": self._get_permission_type(
                permission_decorator,
                has_depends_permission,
                has_is_admin,
                has_current_user
            ),
            "line_number": func_node.lineno
        }

    def _check_function_for_permissions(self, func_node: ast.FunctionDef) -> bool:
        """Check if function has Depends(require_permissions(...)) or PermissionChecker."""
        # Check annotations
        for arg in func_node.args.args + func_node.args.kwonlyargs:
            if arg.annotation:
                annotation_str = ast.unparse(arg.annotation)
                if "Depends" in annotation_str and (
                    "require_permissions" in annotation_str or
                    "PermissionChecker" in annotation_str
                ):
                    return True

        # Check default values (where Depends() is typically used)
        for default in func_node.args.defaults + func_node.args.kw_defaults:
            if default is not None:
                default_str = ast.unparse(default)
                if "Depends" in default_str and (
                    "require_permissions" in default_str or
                    "PermissionChecker" in default_str
                ):
                    return True

        return False

    def _check_function_for_admin(self, func_node: ast.FunctionDef) -> bool:
        """Check if function has Depends(is_admin)."""
        # Check annotations
        for arg in func_node.args.args + func_node.args.kwonlyargs:
            if arg.annotation:
                annotation_str = ast.unparse(arg.annotation)
                if "Depends" in annotation_str and "is_admin" in annotation_str:
                    return True

        # Check default values
        for default in func_node.args.defaults + func_node.args.kw_defaults:
            if default is not None:
                default_str = ast.unparse(default)
                if "Depends" in default_str and "is_admin" in default_str:
                    return True

        return False

    def _check_function_for_current_user(self, func_node: ast.FunctionDef) -> bool:
        """Check if function has Depends(get_current_user) for authentication."""
        # Check annotations
        for arg in func_node.args.args + func_node.args.kwonlyargs:
            if arg.annotation:
                annotation_str = ast.unparse(arg.annotation)
                if "Depends" in annotation_str and "get_current_user" in annotation_str:
                    return True

        # Check default values
        for default in func_node.args.defaults + func_node.args.kw_defaults:
            if default is not None:
                default_str = ast.unparse(default)
                if "Depends" in default_str and "get_current_user" in default_str:
                    return True

        return False

    def _get_permission_type(
        self,
        decorator: str,
        has_depends: bool,
        has_admin: bool,
        has_current_user: bool
    ) -> str:
        """Determine the type of permission check."""
        if has_admin:
            return "is_admin"
        elif decorator:
            return "decorator"
        elif has_depends:
            return "depends"
        elif has_current_user:
            return "authenticated"
        return "none"

    def audit_all_routes(self):
        """Audit all route files in the routes directory."""
        print("=" * 80)
        print("ROUTE PERMISSION COVERAGE AUDIT")
        print("=" * 80)
        print(f"\nScanning directory: {self.routes_dir}")
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        # Find all Python files
        route_files = list(self.routes_dir.rglob("*.py"))
        route_files = [f for f in route_files if "__pycache__" not in str(f) and "__init__" not in f.name]

        self.route_stats["total_files"] = len(route_files)

        print(f"Found {len(route_files)} route files\n")

        # Process each file
        for file_path in sorted(route_files):
            routes = self.extract_routes_from_file(file_path)

            for route in routes:
                self.route_stats["total_routes"] += 1

                if self.is_public_route(route["path"]):
                    route["is_public"] = True
                    self.public_routes.append(route)
                    self.route_stats["public_routes"] += 1
                elif route["has_permission"]:
                    route["is_public"] = False
                    self.protected_routes.append(route)
                    self.route_stats["protected_routes"] += 1
                else:
                    route["is_public"] = False
                    self.unprotected_routes.append(route)
                    self.route_stats["unprotected_routes"] += 1

        # Calculate coverage
        non_public_routes = self.route_stats["total_routes"] - self.route_stats["public_routes"]
        if non_public_routes > 0:
            self.route_stats["coverage_percentage"] = (
                self.route_stats["protected_routes"] / non_public_routes * 100
            )

    def print_summary(self):
        """Print audit summary."""
        print("\n" + "=" * 80)
        print("AUDIT SUMMARY")
        print("=" * 80)
        print(f"\nTotal Files Scanned:     {self.route_stats['total_files']}")
        print(f"Total Routes Found:      {self.route_stats['total_routes']}")
        print(f"Public Routes:           {self.route_stats['public_routes']}")
        print(f"Protected Routes:        {self.route_stats['protected_routes']}")
        print(f"Unprotected Routes:      {self.route_stats['unprotected_routes']}")
        print(f"\nCoverage:                {self.route_stats['coverage_percentage']:.1f}% "
              f"({self.route_stats['protected_routes']}/{self.route_stats['total_routes'] - self.route_stats['public_routes']})")

        if self.route_stats["coverage_percentage"] >= 100:
            print("\n✅ EXCELLENT! 100% route protection coverage achieved!")
        elif self.route_stats["coverage_percentage"] >= 90:
            print("\n✅ GOOD! Most routes are protected. A few more to go.")
        elif self.route_stats["coverage_percentage"] >= 70:
            print("\n⚠️  WARNING: Some routes are unprotected. Needs attention.")
        else:
            print("\n❌ CRITICAL: Many routes are unprotected! Security risk!")

    def print_unprotected_routes(self):
        """Print list of unprotected routes."""
        if not self.unprotected_routes:
            print("\n✅ No unprotected routes found!")
            return

        print("\n" + "=" * 80)
        print("UNPROTECTED ROUTES (REQUIRES ATTENTION)")
        print("=" * 80)

        # Group by file
        routes_by_file = defaultdict(list)
        for route in self.unprotected_routes:
            routes_by_file[route["file"]].append(route)

        for file_path in sorted(routes_by_file.keys()):
            print(f"\n📁 {file_path}")
            for route in routes_by_file[file_path]:
                print(f"   ❌ {route['method']:6} {route['path']}")
                print(f"      Function: {route['function']} (line {route['line_number']})")

    def print_protected_routes(self):
        """Print list of protected routes."""
        if not self.protected_routes:
            return

        print("\n" + "=" * 80)
        print("PROTECTED ROUTES")
        print("=" * 80)

        # Group by file
        routes_by_file = defaultdict(list)
        for route in self.protected_routes:
            routes_by_file[route["file"]].append(route)

        for file_path in sorted(routes_by_file.keys()):
            print(f"\n📁 {file_path}")
            for route in routes_by_file[file_path]:
                perm_type = route["permission_type"]
                icon = "✅"
                print(f"   {icon} {route['method']:6} {route['path']} ({perm_type})")

    def export_json(self, output_file: str = "route_audit_report.json"):
        """Export audit results to JSON."""
        report = {
            "audit_date": datetime.now().isoformat(),
            "statistics": self.route_stats,
            "unprotected_routes": self.unprotected_routes,
            "protected_routes": self.protected_routes,
            "public_routes": self.public_routes
        }

        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)

        print(f"\n📄 JSON report exported to: {output_file}")

    def export_markdown(self, output_file: str = "ROUTE-AUDIT.md"):
        """Export audit results to Markdown."""
        with open(output_file, 'w') as f:
            f.write("# Route Permission Coverage Audit Report\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            # Summary
            f.write("## Summary\n\n")
            f.write(f"- **Total Files:** {self.route_stats['total_files']}\n")
            f.write(f"- **Total Routes:** {self.route_stats['total_routes']}\n")
            f.write(f"- **Public Routes:** {self.route_stats['public_routes']}\n")
            f.write(f"- **Protected Routes:** {self.route_stats['protected_routes']}\n")
            f.write(f"- **Unprotected Routes:** {self.route_stats['unprotected_routes']}\n")
            f.write(f"- **Coverage:** {self.route_stats['coverage_percentage']:.1f}%\n\n")

            # Unprotected routes
            if self.unprotected_routes:
                f.write("## Unprotected Routes\n\n")
                f.write("These routes need permission protection:\n\n")

                routes_by_file = defaultdict(list)
                for route in self.unprotected_routes:
                    routes_by_file[route["file"]].append(route)

                for file_path in sorted(routes_by_file.keys()):
                    f.write(f"### {file_path}\n\n")
                    for route in routes_by_file[file_path]:
                        f.write(f"- ❌ `{route['method']} {route['path']}`\n")
                        f.write(f"  - Function: `{route['function']}` (line {route['line_number']})\n")
                    f.write("\n")

            # Protected routes
            if self.protected_routes:
                f.write("## Protected Routes\n\n")
                f.write(f"Total protected routes: {len(self.protected_routes)}\n\n")

        print(f"\n📄 Markdown report exported to: {output_file}")


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(description="Audit route permission coverage")
    parser.add_argument(
        "--output-format",
        choices=["text", "json", "markdown", "all"],
        default="all",
        help="Output format (default: all)"
    )
    parser.add_argument(
        "--show-protected",
        action="store_true",
        help="Show list of protected routes"
    )
    parser.add_argument(
        "--routes-dir",
        default="src/api/routes",
        help="Routes directory to scan (default: src/api/routes)"
    )

    args = parser.parse_args()

    # Create auditor
    auditor = RouteAuditor(routes_dir=args.routes_dir)

    # Run audit
    auditor.audit_all_routes()

    # Print results
    auditor.print_summary()
    auditor.print_unprotected_routes()

    if args.show_protected:
        auditor.print_protected_routes()

    # Export reports
    if args.output_format in ["json", "all"]:
        auditor.export_json()

    if args.output_format in ["markdown", "all"]:
        auditor.export_markdown()

    print("\n" + "=" * 80)
    print("Audit complete!")
    print("=" * 80 + "\n")

    # Exit with error code if coverage is below 100%
    if auditor.route_stats["coverage_percentage"] < 100:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
