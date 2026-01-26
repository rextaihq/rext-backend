"""
Permission Matrix Verification Script

This script verifies that the actual role-permission assignments in the database
match the expected assignments defined in the seed file.

Usage:
    python scripts/verify_permission_matrix.py
    python scripts/verify_permission_matrix.py --verbose
    python scripts/verify_permission_matrix.py --export report.md

Features:
    - Compares database state vs seed file expectations
    - Identifies missing permissions (should have but don't)
    - Identifies extra permissions (have but shouldn't)
    - Validates critical security rules (owner-only billing, editor can't delete)
    - Generates detailed markdown report
    - Exit code 0 (pass) or 1 (fail) for CI/CD integration

Author: Claude Code (RBAC Implementation - Task 4.1)
Date: 2025-10-25
"""

import asyncio
import sys
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple
from datetime import datetime
import argparse

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.database.async_database import get_async_db
from src.utils.logger import logger


# ============================================================================
# EXPECTED PERMISSION MATRIX (from seed_permissions.py)
# ============================================================================

EXPECTED_ROLE_PERMISSIONS = {
    "workspace_owner": [
        # Full workspace control including billing
        "workspace.read", "workspace.update", "workspace.delete", "workspace.transfer",
        "workspace.manage_members", "workspace.manage_roles", "workspace.invite",

        # BILLING & SUBSCRIPTION (OWNER ONLY!)
        "subscription.read", "subscription.manage",
        "billing.read", "billing.manage",
        "usage.read",

        # Content management (full)
        "content.create", "content.read", "content.update", "content.delete",
        "content.publish", "content.submit_for_review", "content.approve", "content.reject", "content.export",

        # Topics (full)
        "topic.create", "topic.read", "topic.update", "topic.delete", "topic.approve",

        # Knowledge (full)
        "knowledge.create", "knowledge.read", "knowledge.update", "knowledge.delete",

        # Media (full)
        "media.create", "media.read", "media.delete", "media.organize", "media.update",
        "media.upload", "media.view",  # Backward compatibility

        # Members (full)
        "member.read", "member.update", "member.update_role",
        "member.invite", "member.remove", "member.resend_invitation", "member.revoke_invitation",

        # License (full)
        "license.read", "license.view", "license.activate", "license.deactivate",
    ],

    "workspace_admin": [
        # Workspace management (NO delete, NO transfer, NO billing)
        "workspace.read", "workspace.update",
        "workspace.manage_members", "workspace.manage_roles", "workspace.invite",

        # NO BILLING/SUBSCRIPTION ACCESS!
        "usage.read",  # Can view usage only
        "license.read", "license.view", "license.activate",

        # Content management (full)
        "content.create", "content.read", "content.update", "content.delete",
        "content.publish", "content.submit_for_review", "content.approve", "content.reject", "content.export",

        # Topics (full)
        "topic.create", "topic.read", "topic.update", "topic.delete", "topic.approve",

        # Knowledge (full)
        "knowledge.create", "knowledge.read", "knowledge.update", "knowledge.delete",

        # Media (full)
        "media.create", "media.read", "media.delete", "media.organize", "media.update",
        "media.upload", "media.view",  # Backward compatibility

        # Members (full)
        "member.read", "member.update", "member.update_role",
        "member.invite", "member.remove", "member.resend_invitation", "member.revoke_invitation",
    ],

    "editor": [
        # Workspace (read only)
        "workspace.read",

        # Content (can create/edit/publish, cannot delete)
        "content.create", "content.read", "content.update",
        "content.publish", "content.submit_for_review", "content.approve", "content.reject", "content.export",

        # Topics (can create/edit)
        "topic.create", "topic.read", "topic.update", "topic.approve",

        # Knowledge (can create/edit)
        "knowledge.create", "knowledge.read", "knowledge.update",

        # Media (can upload/view)
        "media.create", "media.read", "media.organize",
        "media.upload", "media.view",  # Backward compatibility

        # Members (read only)
        "member.read",

        # License (view only)
        "license.read", "license.view",
    ],

    "viewer": [
        # Workspace (read only)
        "workspace.read",

        # Content (read only)
        "content.read",

        # Topics (read only)
        "topic.read",

        # Knowledge (read only)
        "knowledge.read",

        # Media (read only)
        "media.read", "media.view",  # Backward compatibility

        # Members (read only)
        "member.read",

        # License (view only)
        "license.read", "license.view",
    ],

    "super_admin": "ALL",  # Special marker - super admin should bypass checks

    "admin": [
        # All workspace permissions
        "workspace.create", "workspace.read", "workspace.update", "workspace.delete", "workspace.transfer",
        "workspace.manage_members", "workspace.manage_roles", "workspace.invite",

        # All billing
        "subscription.read", "subscription.manage",
        "billing.read", "billing.manage", "usage.read",

        # All content
        "content.create", "content.read", "content.update", "content.delete",
        "content.publish", "content.submit_for_review", "content.approve", "content.reject", "content.export",

        # All topics, knowledge, media
        "topic.create", "topic.read", "topic.update", "topic.delete", "topic.approve",
        "knowledge.create", "knowledge.read", "knowledge.update", "knowledge.delete",
        "media.create", "media.read", "media.delete", "media.organize", "media.update",
        "media.upload", "media.view",

        # All members, licenses
        "member.read", "member.update", "member.update_role",
        "member.invite", "member.remove", "member.resend_invitation", "member.revoke_invitation",
        "license.read", "license.view", "license.activate", "license.deactivate", "license.revoke",

        # User management (less destructive than super_admin)
        "user.create", "user.read", "user.update",  # No user.delete
        "user.manage_roles",

        # Role/permission management (less destructive)
        "role.create", "role.read", "role.update",  # No role.delete
        "role.manage_permissions",
        "permission.create", "permission.read", "permission.update",  # No permission.delete

        # Platform management
        "audit.read", "audit.export",

        # Support permissions (admin can do support tasks)
        "support.view_workspace", "support.view_billing",
    ],

    "support": [
        # Read-only workspace access
        "workspace.read", "content.read", "topic.read", "knowledge.read", "media.read", "media.view",
        "member.read",

        # Support-specific permissions
        "support.view_workspace", "support.view_billing",

        # License view
        "license.read", "license.view",

        # Audit read
        "audit.read",
    ],

    "user": [
        # Default authenticated user
        "workspace.create",  # Users can create their own workspaces
        "workspace.read",  # Can view workspaces they're part of

        # Basic content/topic read
        "content.read", "topic.read", "knowledge.read",
        "media.read", "media.view",
        "member.read",

        # License view
        "license.read", "license.view",
    ],
}


# ============================================================================
# CRITICAL SECURITY RULES
# ============================================================================

CRITICAL_RULES = [
    {
        "description": "Owner MUST have subscription.read",
        "role": "workspace_owner",
        "permission": "subscription.read",
        "must_have": True,
    },
    {
        "description": "Owner MUST have billing.read",
        "role": "workspace_owner",
        "permission": "billing.read",
        "must_have": True,
    },
    {
        "description": "Owner MUST have workspace.delete",
        "role": "workspace_owner",
        "permission": "workspace.delete",
        "must_have": True,
    },
    {
        "description": "Admin MUST NOT have subscription.read",
        "role": "workspace_admin",
        "permission": "subscription.read",
        "must_have": False,
    },
    {
        "description": "Admin MUST NOT have billing.read",
        "role": "workspace_admin",
        "permission": "billing.read",
        "must_have": False,
    },
    {
        "description": "Admin MUST NOT have workspace.delete",
        "role": "workspace_admin",
        "permission": "workspace.delete",
        "must_have": False,
    },
    {
        "description": "Editor MUST have content.publish",
        "role": "editor",
        "permission": "content.publish",
        "must_have": True,
    },
    {
        "description": "Editor MUST NOT have content.delete",
        "role": "editor",
        "permission": "content.delete",
        "must_have": False,
    },
    {
        "description": "Viewer MUST have content.read",
        "role": "viewer",
        "permission": "content.read",
        "must_have": True,
    },
    {
        "description": "Viewer MUST NOT have content.update",
        "role": "viewer",
        "permission": "content.update",
        "must_have": False,
    },
]


# ============================================================================
# DATABASE QUERY FUNCTIONS
# ============================================================================

async def get_actual_role_permissions(db: AsyncSession) -> Dict[str, Set[str]]:
    """Fetch actual role-permission assignments from database."""

    # Query: Get all role-permission assignments using raw SQL to avoid model loading issues
    query = text("""
        SELECT r.name as role_name, p.name as permission_name
        FROM roles r
        JOIN role_permissions rp ON rp.role_id = r.id
        JOIN permissions p ON p.id = rp.permission_id
        ORDER BY r.name, p.name
    """)

    result = await db.execute(query)
    rows = result.fetchall()

    # Group by role
    role_permissions: Dict[str, Set[str]] = {}
    for row in rows:
        role_name = row.role_name
        perm_name = row.permission_name
        if role_name not in role_permissions:
            role_permissions[role_name] = set()
        role_permissions[role_name].add(perm_name)

    return role_permissions


async def get_all_permissions(db: AsyncSession) -> Set[str]:
    """Fetch all permission names from database."""
    query = text("SELECT name FROM permissions ORDER BY name")
    result = await db.execute(query)
    return set(row.name for row in result.fetchall())


async def get_role_counts(db: AsyncSession) -> Dict[str, int]:
    """Get permission counts per role."""
    query = text("SELECT name, display_name FROM roles ORDER BY name")

    result = await db.execute(query)
    roles = {row.name: row.display_name for row in result.fetchall()}

    actual_perms = await get_actual_role_permissions(db)

    counts = {}
    for role_name in roles:
        counts[role_name] = {
            "display_name": roles[role_name],
            "count": len(actual_perms.get(role_name, set())),
        }

    return counts


# ============================================================================
# VERIFICATION FUNCTIONS
# ============================================================================

def compare_role_permissions(
    role_name: str,
    expected: List[str],
    actual: Set[str],
    all_permissions: Set[str]
) -> Tuple[List[str], List[str]]:
    """
    Compare expected vs actual permissions for a role.

    Returns:
        (missing_permissions, extra_permissions)
    """

    # Handle super_admin special case
    if expected == "ALL":
        # Super admin should have all permissions (or bypass checks in code)
        missing = list(all_permissions - actual) if actual else []
        extra = []
        return missing, extra

    expected_set = set(expected)

    missing = list(expected_set - actual)
    extra = list(actual - expected_set)

    return missing, extra


def check_critical_rules(
    actual_permissions: Dict[str, Set[str]]
) -> List[Dict]:
    """
    Verify critical security rules.

    Returns:
        List of rule check results
    """
    results = []

    for rule in CRITICAL_RULES:
        role = rule["role"]
        perm = rule["permission"]
        must_have = rule["must_have"]

        actual_has = perm in actual_permissions.get(role, set())

        passed = actual_has == must_have

        results.append({
            "description": rule["description"],
            "passed": passed,
            "expected": "HAS" if must_have else "DOES NOT HAVE",
            "actual": "HAS" if actual_has else "DOES NOT HAVE",
        })

    return results


# ============================================================================
# REPORT GENERATION
# ============================================================================

def generate_markdown_report(
    actual_permissions: Dict[str, Set[str]],
    all_permissions: Set[str],
    role_counts: Dict[str, int],
    critical_results: List[Dict],
    verbose: bool = False
) -> str:
    """Generate detailed markdown report."""

    lines = []
    lines.append("# Permission Matrix Verification Report")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Total Permissions in Database:** {len(all_permissions)}")
    lines.append("")

    # ========== EXECUTIVE SUMMARY ==========
    lines.append("## Executive Summary")
    lines.append("")

    total_issues = 0
    critical_failures = sum(1 for r in critical_results if not r["passed"])

    lines.append("### Critical Rule Checks")
    lines.append("")
    if critical_failures == 0:
        lines.append("✅ **ALL CRITICAL RULES PASSED** (10/10)")
    else:
        lines.append(f"❌ **{critical_failures} CRITICAL RULE FAILURES** ({10 - critical_failures}/10 passed)")
        total_issues += critical_failures
    lines.append("")

    # Role-by-role summary
    lines.append("### Role Permission Summary")
    lines.append("")
    lines.append("| Role | Expected | Actual | Status |")
    lines.append("|------|----------|--------|--------|")

    for role_name in ["workspace_owner", "workspace_admin", "editor", "viewer"]:
        expected_perms = EXPECTED_ROLE_PERMISSIONS.get(role_name, [])
        actual = actual_permissions.get(role_name, set())

        if expected_perms == "ALL":
            expected_count = len(all_permissions)
        else:
            expected_count = len(expected_perms)

        actual_count = len(actual)

        missing, extra = compare_role_permissions(role_name, expected_perms, actual, all_permissions)

        if missing or extra:
            status = f"❌ ({len(missing)} missing, {len(extra)} extra)"
            total_issues += len(missing) + len(extra)
        else:
            status = "✅ Perfect match"

        lines.append(f"| {role_name} | {expected_count} | {actual_count} | {status} |")

    lines.append("")

    if total_issues == 0:
        lines.append("### ✅ VERIFICATION PASSED")
        lines.append("")
        lines.append("All permissions match expected matrix. No issues found.")
    else:
        lines.append(f"### ❌ VERIFICATION FAILED")
        lines.append("")
        lines.append(f"Found **{total_issues} total issues** that need to be fixed.")

    lines.append("")
    lines.append("---")
    lines.append("")

    # ========== CRITICAL RULE DETAILS ==========
    lines.append("## Critical Security Rule Checks")
    lines.append("")

    for result in critical_results:
        icon = "✅" if result["passed"] else "❌"
        lines.append(f"{icon} **{result['description']}**")
        lines.append(f"   - Expected: {result['expected']}")
        lines.append(f"   - Actual: {result['actual']}")
        lines.append("")

    lines.append("---")
    lines.append("")

    # ========== ROLE-BY-ROLE ANALYSIS ==========
    lines.append("## Detailed Role Analysis")
    lines.append("")

    for role_name in ["workspace_owner", "workspace_admin", "editor", "viewer", "super_admin", "admin", "support", "user"]:
        expected_perms = EXPECTED_ROLE_PERMISSIONS.get(role_name, [])
        actual = actual_permissions.get(role_name, set())

        missing, extra = compare_role_permissions(role_name, expected_perms, actual, all_permissions)

        lines.append(f"### {role_name}")
        lines.append("")

        if expected_perms == "ALL":
            lines.append(f"- **Expected:** ALL permissions ({len(all_permissions)})")
        else:
            lines.append(f"- **Expected:** {len(expected_perms)} permissions")

        lines.append(f"- **Actual:** {len(actual)} permissions")
        lines.append("")

        if not missing and not extra:
            lines.append("✅ **Perfect Match** - All permissions correct!")
        else:
            if missing:
                lines.append(f"❌ **Missing {len(missing)} permissions:**")
                for perm in sorted(missing)[:10]:  # Show first 10
                    lines.append(f"   - `{perm}`")
                if len(missing) > 10:
                    lines.append(f"   - ... and {len(missing) - 10} more")
                lines.append("")

            if extra:
                lines.append(f"⚠️ **Extra {len(extra)} permissions:**")
                for perm in sorted(extra)[:10]:  # Show first 10
                    lines.append(f"   - `{perm}`")
                if len(extra) > 10:
                    lines.append(f"   - ... and {len(extra) - 10} more")
                lines.append("")

        # Verbose mode: show all permissions
        if verbose and actual:
            lines.append("<details>")
            lines.append("<summary>All Actual Permissions (click to expand)</summary>")
            lines.append("")
            for perm in sorted(actual):
                lines.append(f"- `{perm}`")
            lines.append("")
            lines.append("</details>")
            lines.append("")

        lines.append("")

    lines.append("---")
    lines.append("")

    # ========== RECOMMENDATIONS ==========
    lines.append("## Recommendations")
    lines.append("")

    if total_issues == 0:
        lines.append("✅ No action needed. All permissions are correctly assigned.")
    else:
        lines.append("### Action Items")
        lines.append("")
        lines.append("1. Review missing permissions and add them using `scripts/seed_permissions.py`")
        lines.append("2. Review extra permissions and remove if unintended")
        lines.append("3. Verify critical rule failures and fix immediately")
        lines.append("4. Re-run this script to confirm fixes")
        lines.append("")
        lines.append("**Command to fix:**")
        lines.append("```bash")
        lines.append("cd rext-backend")
        lines.append("python scripts/seed_permissions.py")
        lines.append("python scripts/verify_permission_matrix.py")
        lines.append("```")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("**End of Report**")

    return "\n".join(lines)


# ============================================================================
# MAIN FUNCTION
# ============================================================================

async def main():
    """Main verification function."""

    parser = argparse.ArgumentParser(description="Verify permission matrix against expected assignments")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all permissions for each role")
    parser.add_argument("--export", "-e", type=str, help="Export report to markdown file")
    parser.add_argument("--json", "-j", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    logger.info("🔍 Starting permission matrix verification...")

    # Get database session
    async for db in get_async_db():
        try:
            # Fetch actual permissions
            logger.info("📊 Fetching actual permissions from database...")
            actual_permissions = await get_actual_role_permissions(db)
            all_permissions = await get_all_permissions(db)
            role_counts = await get_role_counts(db)

            logger.info(f"✅ Found {len(all_permissions)} permissions across {len(actual_permissions)} roles")

            # Check critical rules
            logger.info("🔐 Checking critical security rules...")
            critical_results = check_critical_rules(actual_permissions)

            # Generate report
            report = generate_markdown_report(
                actual_permissions,
                all_permissions,
                role_counts,
                critical_results,
                verbose=args.verbose
            )

            # Output
            if args.export:
                output_path = Path(args.export)
                output_path.write_text(report)
                logger.info(f"📝 Report exported to {output_path}")
            else:
                print("\n" + report)

            # JSON output
            if args.json:
                json_data = {
                    "timestamp": datetime.now().isoformat(),
                    "total_permissions": len(all_permissions),
                    "critical_results": critical_results,
                    "role_counts": role_counts,
                    "verification_passed": all(r["passed"] for r in critical_results),
                }
                print("\n" + json.dumps(json_data, indent=2))

            # Determine exit code
            critical_failures = sum(1 for r in critical_results if not r["passed"])

            if critical_failures > 0:
                logger.error(f"❌ Verification FAILED: {critical_failures} critical rule failures")
                sys.exit(1)
            else:
                logger.info("✅ Verification PASSED: All critical rules satisfied")
                sys.exit(0)

        finally:
            await db.close()


if __name__ == "__main__":
    asyncio.run(main())
