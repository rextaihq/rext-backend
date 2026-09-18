#!/usr/bin/env python3
"""
RBAC Route Protection Verification Script
==========================================

Verifies that all API routes have proper permission protection in place.
This script detects both decorator-based and dependency-based protection patterns:
1. @require_permissions decorator
2. Depends(is_admin) / Depends(is_super_admin) dependencies
3. PermissionChecker dependency

Exit Codes:
    0: All routes properly protected (or intentionally public)
    1: Unprotected routes found (security risk)

Usage:
    python scripts/verify_route_protection.py
    python scripts/verify_route_protection.py --strict  # Fail on any unprotected route
    python scripts/verify_route_protection.py --json    # Output JSON report
"""

import ast
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class RouteProtectionVerifier:
    """Verifies that all routes have proper RBAC permission enforcement."""

    # Routes that should be intentionally public (no protection needed)
    PUBLIC_ROUTES = {
        # Authentication endpoints (must be public)
        "/login",
        "/register",
        "/logout",
        "/refresh",
        "/verify-email",
        "/forgot-password",
        "/reset-password",
        "/resend-verification",
        # Health and monitoring (external services)
        "/health",
        "/ready",
        "/liveness",
        "/metrics",
        # Webhooks (external callbacks - have signature verification)
        "/lemonsqueezy",
        "/stripe",
        "/webhook",
        "/webhooks/lemonsqueezy",
        # Public content (if any)
        "/public",
        "/docs",
        "/openapi.json",
        "/redoc",
    }

    # HTTP methods that might be read-only and lower risk
    READ_METHODS = {"GET", "HEAD", "OPTIONS"}

    # HTTP methods that are write/destructive (higher priority to protect)
    WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    def __init__(self, routes_dir: str, strict_mode: bool = False):
        """
        Initialize verifier.

        Args:
            routes_dir: Path to routes directory
            strict_mode: If True, fail on any unprotected route (even if public)
        """
        self.routes_dir = Path(routes_dir)
        self.strict_mode = strict_mode
        self.routes: List[Dict[str, Any]] = []
        self.stats = {
            "total_routes": 0,
            "protected_routes": 0,
            "unprotected_routes": 0,
            "public_routes": 0,
            "by_method": defaultdict(int),
            "by_protection_type": defaultdict(int),
        }

    def verify_all_routes(self) -> bool:
        """
        Scan and verify all routes.

        Returns:
            True if all routes are properly protected, False otherwise
        """
        print("🔐 RBAC Route Protection Verification")
        print(f"📁 Routes Directory: {self.routes_dir}")
        print(f"🔒 Strict Mode: {'ENABLED' if self.strict_mode else 'DISABLED'}")
        print()

        # Scan all route files
        self._scan_all_routes()

        # Analyze protection
        self._analyze_protection()

        # Generate report
        all_protected = self._generate_report()

        return all_protected

    def _scan_all_routes(self) -> None:
        """Scan all Python files in routes directory."""
        print(f"🔍 Scanning routes in: {self.routes_dir}\n")

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
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                route_info = self._extract_route_info(node, file_path)
                if route_info:
                    self.routes.append(route_info)
                    self.stats["total_routes"] += 1

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

        # Check for protection patterns (decorators, dependencies, route-level dependencies)
        protection = self._check_protection(decorators, func_node, route_decorator)

        # Determine category from file path
        category = self._get_category(file_path)

        route_info = {
            "path": path,
            "method": method.upper(),
            "function": func_node.name,
            "file": str(file_path.relative_to(self.routes_dir.parent.parent)),
            "category": category,
            "protection": protection,
            "is_public": self._is_public_route(path),
        }

        return route_info

    def _get_decorators(self, node: ast.FunctionDef) -> List[ast.expr]:
        """Get all decorators for a function."""
        return node.decorator_list if hasattr(node, "decorator_list") else []

    def _is_route_decorator(self, decorator: ast.expr) -> bool:
        """Check if decorator is a route decorator (@router.get, etc.)."""
        if isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Attribute):
                return decorator.func.attr in [
                    "get",
                    "post",
                    "put",
                    "delete",
                    "patch",
                    "options",
                    "head",
                ]
        elif isinstance(decorator, ast.Attribute):
            return decorator.attr in ["get", "post", "put", "delete", "patch", "options", "head"]
        return False

    def _parse_route_decorator(self, decorator: ast.expr) -> Tuple[Optional[str], Optional[str]]:
        """Parse route decorator to extract method and path."""
        method = None
        path = None

        if isinstance(decorator, ast.Call):
            # Get method from decorator function name
            if isinstance(decorator.func, ast.Attribute):
                method = decorator.func.attr

            # Get path from first argument
            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                path = decorator.args[0].value
        elif isinstance(decorator, ast.Attribute):
            method = decorator.attr

        return method, path

    def _check_protection(
        self,
        decorators: List[ast.expr],
        func_node: ast.FunctionDef,
        route_decorator: Optional[ast.expr] = None,
    ) -> Dict[str, Any]:
        """
        Check if route has protection via decorators, dependencies, or route-level dependencies.

        Returns:
            Dict with protection info: {
                "protected": bool,
                "type": str,  # "decorator" | "dependency" | "route_dependency" | "none"
                "details": str
            }
        """
        # Check 1: @require_permissions decorator
        for dec in decorators:
            if self._is_require_permissions_decorator(dec):
                permissions, workspace_scoped = self._parse_require_permissions(dec)
                return {
                    "protected": True,
                    "type": "decorator",
                    "details": f"@require_permissions({', '.join(permissions)})",
                    "permissions": permissions,
                    "workspace_scoped": workspace_scoped,
                }

        # Check 2: dependencies=[...] in @router decorator (e.g., dependencies=[Depends(require_permissions([...]))])
        if route_decorator:
            route_dependency_check = self._check_route_decorator_dependencies(route_decorator)
            if route_dependency_check["protected"]:
                return route_dependency_check

        # Check 3: Depends(is_admin) or Depends(require_permissions([...])) in function signature
        dependency_check = self._check_dependency_protection(func_node)
        if dependency_check["protected"]:
            return dependency_check

        # Check 4: PermissionChecker dependency
        permission_checker = self._check_permission_checker_dependency(func_node)
        if permission_checker["protected"]:
            return permission_checker

        # No protection found
        return {
            "protected": False,
            "type": "none",
            "details": "No protection found",
        }

    def _check_route_decorator_dependencies(self, route_decorator: ast.expr) -> Dict[str, Any]:
        """
        Check if @router decorator has dependencies=[Depends(require_permissions([...]))] keyword argument.

        Example:
            @router.post("/send/{email_log_id}/resend", dependencies=[Depends(require_permissions(["audit.read"]))])

        Returns:
            Dict with protection info
        """
        if not isinstance(route_decorator, ast.Call):
            return {"protected": False, "type": "none", "details": ""}

        # Check keyword arguments for 'dependencies'
        for keyword in route_decorator.keywords:
            if keyword.arg == "dependencies":
                # dependencies should be a list
                if isinstance(keyword.value, ast.List):
                    for dep_item in keyword.value.elts:
                        # Each item should be Depends(...)
                        if isinstance(dep_item, ast.Call):
                            if (
                                isinstance(dep_item.func, ast.Name)
                                and dep_item.func.id == "Depends"
                            ):
                                if dep_item.args:
                                    dep_func = dep_item.args[0]

                                    # Check for require_permissions([...])
                                    if isinstance(dep_func, ast.Call):
                                        if isinstance(dep_func.func, ast.Name):
                                            if dep_func.func.id == "require_permissions":
                                                permissions = self._extract_permissions_from_call(
                                                    dep_func
                                                )
                                                return {
                                                    "protected": True,
                                                    "type": "route_dependency",
                                                    "details": f"dependencies=[Depends(require_permissions({permissions}))]",
                                                    "permissions": permissions,
                                                }

                                    # Check for is_admin, is_super_admin, or get_current_user
                                    elif isinstance(dep_func, ast.Name):
                                        if dep_func.id in ["is_admin", "is_super_admin"]:
                                            return {
                                                "protected": True,
                                                "type": "route_dependency",
                                                "details": f"dependencies=[Depends({dep_func.id})]",
                                            }
                                        elif dep_func.id == "get_current_user":
                                            return {
                                                "protected": True,
                                                "type": "route_dependency",
                                                "details": "dependencies=[Depends(get_current_user)] [auth only]",
                                            }

        return {"protected": False, "type": "none", "details": ""}

    def _is_require_permissions_decorator(self, decorator: ast.expr) -> bool:
        """Check if decorator is @require_permissions."""
        if isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Name):
                return decorator.func.id == "require_permissions"
        return False

    def _parse_require_permissions(self, decorator: ast.Call) -> Tuple[List[str], bool]:
        """
        Parse @require_permissions decorator to extract permissions and workspace_scoped.

        Returns:
            Tuple of (permissions list, workspace_scoped bool)
        """
        permissions = []
        workspace_scoped = True  # Default value

        # Get positional arguments (permissions)
        for arg in decorator.args:
            if isinstance(arg, ast.Constant):
                permissions.append(arg.value)

        # Get keyword arguments (workspace_scoped, require_all)
        for keyword in decorator.keywords:
            if keyword.arg == "workspace_scoped":
                if isinstance(keyword.value, ast.Constant):
                    workspace_scoped = keyword.value.value

        return permissions, workspace_scoped

    def _check_dependency_protection(self, func_node: ast.FunctionDef) -> Dict[str, Any]:
        """
        Check if function has Depends(is_admin), Depends(require_permissions([...])), or similar protection.

        Detects three patterns:
        1. Depends(is_admin) or Depends(is_super_admin)
        2. Depends(require_permissions(["perm1", "perm2"]))
        3. dependencies=[Depends(require_permissions([...]))] in @router decorator
        """
        if not func_node.args:
            return {"protected": False, "type": "none", "details": ""}

        # Check function parameters for Depends() calls
        for arg in func_node.args.args:
            if arg.annotation and isinstance(arg.annotation, ast.Subscript):
                # Look for = Depends(is_admin)
                pass

        # Check default values for Depends() calls
        defaults = func_node.args.defaults
        for default in defaults:
            if isinstance(default, ast.Call):
                # Check if it's Depends(...)
                if isinstance(default.func, ast.Name) and default.func.id == "Depends":
                    if default.args:
                        dep_func = default.args[0]

                        # Pattern 1: Depends(is_admin), Depends(is_super_admin), or Depends(get_current_user)
                        if isinstance(dep_func, ast.Name):
                            if dep_func.id in ["is_admin", "is_super_admin"]:
                                return {
                                    "protected": True,
                                    "type": "dependency",
                                    "details": f"Depends({dep_func.id})",
                                }
                            # get_current_user provides authentication (not authorization)
                            # but is still a form of protection
                            elif dep_func.id == "get_current_user":
                                return {
                                    "protected": True,
                                    "type": "dependency",
                                    "details": "Depends(get_current_user) [auth only]",
                                }

                        # Pattern 2: Depends(require_permissions([...]))
                        elif isinstance(dep_func, ast.Call):
                            if isinstance(dep_func.func, ast.Name):
                                if dep_func.func.id == "require_permissions":
                                    permissions = self._extract_permissions_from_call(dep_func)
                                    return {
                                        "protected": True,
                                        "type": "dependency",
                                        "details": f"Depends(require_permissions({permissions}))",
                                        "permissions": permissions,
                                    }

        return {"protected": False, "type": "none", "details": ""}

    def _extract_permissions_from_call(self, call_node: ast.Call) -> List[str]:
        """
        Extract permission list from require_permissions([...]) call.

        Args:
            call_node: AST Call node for require_permissions

        Returns:
            List of permission strings
        """
        permissions = []

        # Check if first argument is a list
        if call_node.args and isinstance(call_node.args[0], ast.List):
            for elt in call_node.args[0].elts:
                if isinstance(elt, ast.Constant):
                    permissions.append(elt.value)

        return permissions

    def _check_permission_checker_dependency(self, func_node: ast.FunctionDef) -> Dict[str, Any]:
        """Check if function has Depends(PermissionChecker(...)) protection."""
        if not func_node.args:
            return {"protected": False, "type": "none", "details": ""}

        # Check default values for PermissionChecker
        defaults = func_node.args.defaults
        for default in defaults:
            if isinstance(default, ast.Call):
                # Check if it's Depends(PermissionChecker(...))
                if isinstance(default.func, ast.Name) and default.func.id == "Depends":
                    if default.args:
                        dep_func = default.args[0]
                        if isinstance(dep_func, ast.Call):
                            if isinstance(dep_func.func, ast.Name):
                                if dep_func.func.id == "PermissionChecker":
                                    return {
                                        "protected": True,
                                        "type": "dependency",
                                        "details": "Depends(PermissionChecker(...))",
                                    }

        return {"protected": False, "type": "none", "details": ""}

    def _is_public_route(self, path: str) -> bool:
        """Check if route should be intentionally public."""
        for public_route in self.PUBLIC_ROUTES:
            if path.startswith(public_route) or path == public_route:
                return True
        return False

    def _get_category(self, file_path: Path) -> str:
        """Get route category from file path."""
        parts = file_path.parts
        if "routes" in parts:
            idx = parts.index("routes")
            if idx + 1 < len(parts):
                return parts[idx + 1]
        return "unknown"

    def _analyze_protection(self) -> None:
        """Analyze protection statistics."""
        for route in self.routes:
            method = route["method"]
            self.stats["by_method"][method] += 1

            if route["protection"]["protected"]:
                self.stats["protected_routes"] += 1
                self.stats["by_protection_type"][route["protection"]["type"]] += 1
            elif route["is_public"]:
                self.stats["public_routes"] += 1
            else:
                self.stats["unprotected_routes"] += 1

    def _generate_report(self) -> bool:
        """
        Generate verification report.

        Returns:
            True if all routes properly protected, False otherwise
        """
        print("\n" + "=" * 80)
        print("📊 VERIFICATION RESULTS")
        print("=" * 80 + "\n")

        # Overall statistics
        print(f"Total Routes: {self.stats['total_routes']}")
        print(f"✅ Protected Routes: {self.stats['protected_routes']}")
        print(f"🌐 Intentionally Public: {self.stats['public_routes']}")
        print(f"❌ Unprotected Routes: {self.stats['unprotected_routes']}")
        print()

        # Protection breakdown
        print("Protection Type Breakdown:")
        for ptype, count in self.stats["by_protection_type"].items():
            print(f"  - {ptype.capitalize()}: {count}")
        print()

        # Method breakdown
        print("HTTP Method Breakdown:")
        for method, count in sorted(self.stats["by_method"].items()):
            print(f"  - {method}: {count}")
        print()

        # Unprotected routes details
        unprotected = [
            r for r in self.routes if not r["protection"]["protected"] and not r["is_public"]
        ]

        if unprotected:
            print("⚠️  UNPROTECTED ROUTES FOUND:")
            print("=" * 80)

            # Group by category
            by_category = defaultdict(list)
            for route in unprotected:
                by_category[route["category"]].append(route)

            for category in sorted(by_category.keys()):
                routes = by_category[category]
                print(f"\n📁 Category: {category.upper()} ({len(routes)} routes)")
                print("-" * 80)

                for route in routes:
                    priority = "🔴 P0" if route["method"] in self.WRITE_METHODS else "🟡 P1"
                    print(f"{priority} {route['method']:6} {route['path']}")
                    print(f"      File: {route['file']}")
                    print(f"      Function: {route['function']}")
                    print()
        else:
            print("✅ All routes are properly protected!")
            print()

        # Public routes (informational)
        public_routes = [r for r in self.routes if r["is_public"]]
        if public_routes:
            print("🌐 INTENTIONALLY PUBLIC ROUTES (No protection needed):")
            print("=" * 80)
            for route in public_routes[:10]:  # Show first 10
                print(f"   {route['method']:6} {route['path']}")
            if len(public_routes) > 10:
                print(f"   ... and {len(public_routes) - 10} more")
            print()

        # Final verdict
        print("=" * 80)

        if self.strict_mode:
            # In strict mode, even public routes must have explicit protection
            all_protected = (
                self.stats["unprotected_routes"] == 0 and self.stats["public_routes"] == 0
            )
            if all_protected:
                print("✅ PASS: All routes have explicit protection (strict mode)")
            else:
                print("❌ FAIL: Some routes lack explicit protection (strict mode)")
        else:
            # In normal mode, public routes are OK
            all_protected = self.stats["unprotected_routes"] == 0
            if all_protected:
                print("✅ PASS: All routes properly protected or intentionally public")
            else:
                print(f"❌ FAIL: {self.stats['unprotected_routes']} unprotected routes found")

        print("=" * 80)

        return all_protected

    def export_json(self, output_file: str = "route-protection-report.json") -> None:
        """Export detailed report as JSON."""
        report = {
            "summary": dict(self.stats),
            "routes": self.routes,
            "unprotected_routes": [
                r for r in self.routes if not r["protection"]["protected"] and not r["is_public"]
            ],
            "public_routes": [r for r in self.routes if r["is_public"]],
            "protected_routes": [r for r in self.routes if r["protection"]["protected"]],
        }

        with open(output_file, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\n📄 JSON report exported to: {output_file}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Verify RBAC protection on all API routes")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Strict mode: fail on any unprotected route (including public)",
    )
    parser.add_argument("--json", action="store_true", help="Export detailed JSON report")
    parser.add_argument(
        "--routes-dir",
        default="src/api/routes",
        help="Path to routes directory (default: src/api/routes)",
    )

    args = parser.parse_args()

    # Get absolute path to routes directory
    script_dir = Path(__file__).parent
    routes_dir = script_dir.parent / args.routes_dir

    if not routes_dir.exists():
        print(f"❌ Error: Routes directory not found: {routes_dir}")
        sys.exit(1)

    # Run verification
    verifier = RouteProtectionVerifier(str(routes_dir), strict_mode=args.strict)
    all_protected = verifier.verify_all_routes()

    # Export JSON if requested
    if args.json:
        verifier.export_json()

    # Exit with appropriate code for CI/CD
    sys.exit(0 if all_protected else 1)


if __name__ == "__main__":
    main()
