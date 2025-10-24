#!/usr/bin/env python3
"""
Map Unprotected Routes to Required Permissions
===============================================

Analyzes unprotected routes and creates a mapping to required permissions.
Uses route patterns, categories, and HTTP methods to suggest appropriate permissions.

Usage:
    python scripts/map_route_permissions.py
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class PermissionMapper:
    """Maps unprotected routes to required permissions."""

    # Permission mapping rules based on route patterns and categories
    PERMISSION_RULES = {
        # Subscription routes
        "subscriptions": {
            "GET /status": ("subscription.read", False, "P0", "View subscription status - owner only"),
            "GET /trial-eligibility": ("subscription.read", False, "P1", "Check trial eligibility"),
            "GET /public": (None, False, "PUBLIC", "Public plan listing - no auth needed"),
            "POST /lemonsqueezy": (None, False, "WEBHOOK", "External webhook - uses signature validation"),
            "POST /validate": ("license.view", False, "P0", "License validation"),
            "GET /webhooks/*": ("subscription.manage", False, "P0", "View webhook events - admin/owner"),
            "POST /webhooks/*": ("subscription.manage", False, "P0", "Retry webhook - admin/owner"),
        },

        # User routes
        "users": {
            "GET *": ("user.read", False, "P0", "View users - admin only"),
            "POST *": ("user.create", False, "P0", "Create users - admin only"),
            "PUT *": ("user.update", False, "P0", "Update users - admin only"),
            "PATCH *": ("user.update", False, "P0", "Update users - admin only"),
            "DELETE *": ("user.delete", False, "P0", "Delete users - super admin only"),
        },

        # Admin routes
        "admin": {
            "GET /error-logs": ("audit.read", False, "P0", "View error logs - admin only"),
            "PATCH /error-logs/*": ("audit.read", False, "P0", "Resolve errors - admin only"),
            "GET /failed": ("audit.read", False, "P0", "View failed emails - admin only"),
            "POST /resend*": ("audit.read", False, "P1", "Resend emails - admin only"),
            "GET /revenue*": ("audit.read", False, "P0", "View revenue reports - admin only"),
            "GET /system-health": (None, False, "MONITORING", "System health check - monitoring only"),
            "GET /export/*": ("audit.export", False, "P0", "Export data - admin only"),
        },

        # Audit routes
        "audit": {
            "GET *": ("audit.read", False, "P0", "View audit logs - admin only"),
            "DELETE *": ("audit.read", False, "P1", "Delete old audit logs - admin only"),
        },

        # Content routes
        "content": {
            "GET *": ("content.read", True, "P0", "View content"),
            "POST *": ("content.create", True, "P0", "Create content"),
            "PUT *": ("content.update", True, "P0", "Update content"),
            "DELETE *": ("content.delete", True, "P0", "Delete content"),
        },

        # Topic routes
        "topics": {
            "GET *": ("topic.read", True, "P0", "View topics"),
            "POST *": ("topic.create", True, "P0", "Create topics"),
            "PUT *": ("topic.update", True, "P0", "Update topics"),
            "DELETE *": ("topic.delete", True, "P0", "Delete topics"),
        },

        # Security routes
        "security": {
            "POST /rotate-keys": ("user.manage_roles", False, "P0", "Rotate API keys - super admin only"),
            "GET /validate-keys": ("user.read", False, "P1", "Validate keys - admin only"),
        },

        # Email routes
        "email": {
            "GET *": ("audit.read", False, "P0", "View email logs - admin only"),
            "POST *": ("audit.read", False, "P1", "Manage emails - admin only"),
        },

        # Events
        "events": {
            "GET *": ("audit.read", False, "P1", "View events - admin only"),
        },

        # Health/monitoring
        "health.py": {
            "GET *": (None, False, "MONITORING", "Health check - no auth needed"),
        },

        # Invitations (root level)
        "invitations.py": {
            "GET *": (None, False, "PUBLIC", "Accept invitation - uses token auth"),
            "POST *": (None, False, "PUBLIC", "Accept invitation - uses token auth"),
        },
    }

    def __init__(self, inventory_path: str):
        """Initialize with route inventory."""
        with open(inventory_path, "r") as f:
            self.inventory = json.load(f)

        self.unprotected_routes = [
            r for r in self.inventory["routes"]
            if not r["has_permission_check"] and not r["is_admin_only"]
        ]

        self.mapping: Dict[str, Dict[str, Any]] = {}

    def map_all_routes(self) -> None:
        """Map all unprotected routes to permissions."""
        print(f"🔍 Mapping {len(self.unprotected_routes)} unprotected routes...")

        for route in self.unprotected_routes:
            mapping = self._map_single_route(route)
            route_key = f"{route['method']} {route['path']}"
            self.mapping[route_key] = mapping

    def _map_single_route(self, route: Dict[str, Any]) -> Dict[str, Any]:
        """Map a single route to its required permission."""
        category = route["category"]
        method = route["method"]
        path = route["path"]

        # Try exact match first
        permission, workspace_scoped, priority, rationale = self._find_permission(
            category, method, path
        )

        # Build mapping entry
        mapping = {
            "file": route["file"],
            "line": route["line"],
            "function": route["function"],
            "category": category,
            "current_protection": "none",
            "recommended_permission": permission,
            "workspace_scoped": workspace_scoped,
            "require_all": True,
            "priority": priority,
            "rationale": rationale,
            "action_required": self._get_action(permission, priority),
        }

        return mapping

    def _find_permission(
        self, category: str, method: str, path: str
    ) -> tuple[Optional[str], bool, str, str]:
        """Find matching permission rule for a route."""

        if category not in self.PERMISSION_RULES:
            # Default to admin-only for unknown categories
            return "audit.read", False, "P1", f"Unknown category '{category}' - defaulting to admin"

        rules = self.PERMISSION_RULES[category]

        # Try exact match: METHOD /specific/path
        exact_key = f"{method} {path}"
        if exact_key in rules:
            perm, ws, priority, rationale = rules[exact_key]
            return perm, ws, priority, rationale

        # Try pattern match: METHOD /path*
        for pattern, (perm, ws, priority, rationale) in rules.items():
            if self._matches_pattern(method, path, pattern):
                return perm, ws, priority, rationale

        # Try wildcard method: GET *, POST *, etc.
        wildcard_key = f"{method} *"
        if wildcard_key in rules:
            perm, ws, priority, rationale = rules[wildcard_key]
            return perm, ws, priority, rationale

        # Default fallback
        return "audit.read", False, "P2", f"No specific rule found - defaulting to admin"

    def _matches_pattern(self, method: str, path: str, pattern: str) -> bool:
        """Check if method and path match a pattern."""
        if " " not in pattern:
            return False

        pattern_method, pattern_path = pattern.split(" ", 1)

        # Method must match
        if pattern_method != "*" and pattern_method != method:
            return False

        # Path matching
        if pattern_path == "*":
            return True

        if pattern_path.endswith("*"):
            prefix = pattern_path[:-1]
            return path.startswith(prefix)

        if pattern_path.startswith("*"):
            suffix = pattern_path[1:]
            return path.endswith(suffix)

        return path == pattern_path

    def _get_action(self, permission: Optional[str], priority: str) -> str:
        """Determine action required based on permission and priority."""
        if priority == "PUBLIC":
            return "REVIEW - Confirm public access is intentional"
        elif priority == "WEBHOOK":
            return "REVIEW - Verify webhook signature validation is in place"
        elif priority == "MONITORING":
            return "REVIEW - Confirm monitoring endpoint needs no auth"
        elif permission is None:
            return "REVIEW - Determine if protection is needed"
        elif priority == "P0":
            return f"ADD DECORATOR - @require_permissions('{permission}')"
        elif priority == "P1":
            return f"ADD DECORATOR - @require_permissions('{permission}') - Medium priority"
        else:
            return f"REVIEW AND ADD - @require_permissions('{permission}') - Low priority"

    def generate_json_report(self, output_path: str) -> None:
        """Generate JSON mapping report."""
        report = {
            "generated_at": "2025-10-24",
            "total_unprotected_routes": len(self.unprotected_routes),
            "mappings": self.mapping,
            "summary": self._generate_summary(),
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        print(f"✅ JSON mapping saved to: {output_path}")

    def _generate_summary(self) -> Dict[str, Any]:
        """Generate summary statistics."""
        by_priority = {"P0": 0, "P1": 0, "P2": 0, "PUBLIC": 0, "WEBHOOK": 0, "MONITORING": 0}
        by_permission = {}

        for mapping in self.mapping.values():
            priority = mapping["priority"]
            by_priority[priority] = by_priority.get(priority, 0) + 1

            perm = mapping["recommended_permission"]
            if perm:
                by_permission[perm] = by_permission.get(perm, 0) + 1

        return {
            "by_priority": by_priority,
            "by_permission": by_permission,
            "needs_immediate_action": by_priority.get("P0", 0),
            "needs_review": by_priority.get("PUBLIC", 0) + by_priority.get("WEBHOOK", 0) + by_priority.get("MONITORING", 0),
        }

    def generate_markdown_report(self, output_path: str) -> None:
        """Generate human-readable markdown report."""
        lines = [
            "# Routes-to-Permissions Mapping",
            "",
            f"**Generated:** 2025-10-24",
            f"**Total Unprotected Routes:** {len(self.unprotected_routes)}",
            "",
            "---",
            "",
            "## Summary",
            "",
        ]

        summary = self._generate_summary()

        lines.extend([
            f"- **P0 (Critical):** {summary['by_priority']['P0']} routes - Immediate action required",
            f"- **P1 (High):** {summary['by_priority']['P1']} routes - Add soon",
            f"- **P2 (Medium):** {summary['by_priority']['P2']} routes - Review and add",
            f"- **PUBLIC:** {summary['by_priority']['PUBLIC']} routes - Review public access",
            f"- **WEBHOOK:** {summary['by_priority']['WEBHOOK']} routes - Verify webhook auth",
            f"- **MONITORING:** {summary['by_priority']['MONITORING']} routes - Review monitoring access",
            "",
            "---",
            "",
            "## P0 Routes (Critical - Add Immediately)",
            "",
        ])

        # Group by priority
        p0_routes = {k: v for k, v in self.mapping.items() if v["priority"] == "P0"}

        if p0_routes:
            for route_key, mapping in sorted(p0_routes.items()):
                lines.append(f"### {route_key}")
                lines.append(f"- **File:** `{mapping['file']}:{mapping['line']}`")
                lines.append(f"- **Function:** `{mapping['function']}`")
                lines.append(f"- **Category:** {mapping['category']}")
                lines.append(f"- **Required Permission:** `{mapping['recommended_permission']}`")
                lines.append(f"- **Workspace Scoped:** {'Yes' if mapping['workspace_scoped'] else 'No'}")
                lines.append(f"- **Rationale:** {mapping['rationale']}")
                lines.append(f"- **Action:** {mapping['action_required']}")
                lines.append("")
        else:
            lines.append("✅ No P0 routes found!")
            lines.append("")

        lines.extend([
            "---",
            "",
            "## Special Cases (Review Required)",
            "",
        ])

        special = {k: v for k, v in self.mapping.items()
                  if v["priority"] in ["PUBLIC", "WEBHOOK", "MONITORING"]}

        if special:
            for route_key, mapping in sorted(special.items()):
                lines.append(f"### {route_key} - {mapping['priority']}")
                lines.append(f"- **Rationale:** {mapping['rationale']}")
                lines.append(f"- **Action:** {mapping['action_required']}")
                lines.append(f"- **File:** `{mapping['file']}:{mapping['line']}`")
                lines.append("")

        # Write file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print(f"✅ Markdown mapping saved to: {output_path}")

    def print_summary(self) -> None:
        """Print summary to console."""
        summary = self._generate_summary()

        print("\n" + "=" * 60)
        print("📊 PERMISSION MAPPING SUMMARY")
        print("=" * 60)
        print(f"Total Unprotected:   {len(self.unprotected_routes)}")
        print(f"P0 (Critical):       {summary['by_priority']['P0']}")
        print(f"P1 (High):           {summary['by_priority']['P1']}")
        print(f"P2 (Medium):         {summary['by_priority']['P2']}")
        print(f"Special Cases:       {summary['needs_review']}")
        print("=" * 60)
        print("\n🔑 Top Permissions Needed:")
        for perm, count in sorted(summary["by_permission"].items(), key=lambda x: -x[1])[:10]:
            print(f"  {perm:30s} {count:3d} routes")
        print("=" * 60 + "\n")


def main():
    """Main execution."""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    output_dir = project_root.parent

    inventory_path = output_dir / "route-inventory.json"

    if not inventory_path.exists():
        print(f"❌ Route inventory not found: {inventory_path}")
        print("   Run audit_routes.py first!")
        return

    # Create mapper
    mapper = PermissionMapper(str(inventory_path))
    mapper.map_all_routes()

    # Generate reports
    json_output = output_dir / "routes-permissions-mapping.json"
    md_output = output_dir / "routes-permissions-mapping.md"

    mapper.generate_json_report(str(json_output))
    mapper.generate_markdown_report(str(md_output))
    mapper.print_summary()

    print(f"\n✅ Mapping complete! Review the reports and proceed to Task 1.2")


if __name__ == "__main__":
    main()
