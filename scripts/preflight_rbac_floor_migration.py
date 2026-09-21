"""Read-only pre-flight for the 20260904rbacfloor migration.

Run this against production BEFORE deploying. It changes nothing - it reports
what the migration would do and flags the two conditions that would block or
disrupt the deploy.

    DATABASE_URL=<prod-url> python scripts/preflight_rbac_floor_migration.py
"""

import os
import re
import sys

import psycopg

PLATFORM_PERMISSIONS = ("user.read", "user.update", "workspace.create", "subscription.read")


def dsn() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("Set DATABASE_URL to the target database first.")
    return re.sub(r"^postgresql\+\w+://", "postgresql://", url.strip().strip('"'))


def main() -> int:
    blockers, warnings = [], []

    with psycopg.connect(dsn()) as conn, conn.cursor() as cur:
        # --- BLOCKER: alembic state -----------------------------------------
        cur.execute("SELECT version_num FROM alembic_version ORDER BY 1")
        applied = [r[0] for r in cur.fetchall()]
        print(f"alembic_version rows: {', '.join(applied) or '(none)'}")

        versions_dir = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")
        known = set()
        for fn in os.listdir(versions_dir):
            if fn.endswith(".py"):
                m = re.search(
                    r'^revision(?::\s*str)?\s*=\s*["\']([^"\']+)',
                    open(os.path.join(versions_dir, fn)).read(),
                    re.M,
                )
                if m:
                    known.add(m.group(1))
        dangling = [v for v in applied if v not in known]
        if dangling:
            blockers.append(
                f"alembic_version contains {dangling}, which no migration file defines. "
                '`alembic upgrade` aborts with "Can\'t locate revision". Delete the '
                "stale row(s) only after confirming they are genuinely orphaned."
            )

        # --- Effect 1: permissions removed from the global 'user' role -------
        cur.execute(
            """
            SELECT p.name FROM roles r
            JOIN role_permissions rp ON rp.role_id = r.id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE r.name = 'user' AND p.name <> ALL(%s)
            ORDER BY p.name
            """,
            (list(PLATFORM_PERMISSIONS),),
        )
        losing = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT count(*) FROM users")
        total_users = cur.fetchone()[0]
        print(
            f"\nGlobal 'user' role loses {len(losing)} permission(s): {', '.join(losing) or '(none)'}"
        )
        print(f"  affects all {total_users} account(s) - they keep these only via workspace roles")

        # --- BLOCKER: members with no workspace-scoped role ------------------
        cur.execute(
            """
            SELECT count(*) FROM workspace_members m
            WHERE NOT EXISTS (
                SELECT 1 FROM user_roles ur
                WHERE ur.user_id = m.user_id AND ur.workspace_id = m.workspace_id
            )
            """
        )
        orphan_members = cur.fetchone()[0]
        print(f"\nMembers with no workspace-scoped role: {orphan_members}")
        if orphan_members:
            print("  -> the migration backfills these (owner role / accepted invitation / viewer)")
            cur.execute(
                """
                SELECT count(*) FROM workspace_members m
                JOIN workspace w ON w.id = m.workspace_id
                WHERE NOT EXISTS (
                    SELECT 1 FROM user_roles ur
                    WHERE ur.user_id = m.user_id AND ur.workspace_id = m.workspace_id
                )
                AND w.user_id <> m.user_id
                AND NOT EXISTS (
                    SELECT 1 FROM user_invitations i
                    JOIN users u ON lower(u.email) = lower(i.email)
                    WHERE u.id = m.user_id AND i.workspace_id = m.workspace_id
                      AND i.status = 'accepted' AND i.role_id IS NOT NULL
                )
                """
            )
            to_viewer = cur.fetchone()[0]
            if to_viewer:
                warnings.append(
                    f"{to_viewer} member(s) have no owner status and no accepted invitation, "
                    "so they fall back to 'viewer'. If any were editors/admins, their role "
                    "is unrecoverable from data and must be reassigned by hand after deploy."
                )

        # --- Effect 2: unscoped workspace-role rows to be deleted ------------
        cur.execute(
            """
            SELECT u.email, r.name FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            JOIN users u ON u.id = ur.user_id
            WHERE ur.workspace_id IS NULL AND r.is_workspace_role IS TRUE
            ORDER BY u.email
            """
        )
        unscoped = cur.fetchall()
        print(f"\nUnscoped workspace-role rows to delete: {len(unscoped)}")
        for email, role in unscoped[:20]:
            print(f"  - {email}: {role} (currently grants {role} in EVERY workspace)")
        if len(unscoped) > 20:
            print(f"  ... and {len(unscoped) - 20} more")
        if unscoped:
            warnings.append(
                f"{len(unscoped)} user(s) lose a role that applied across all workspaces. "
                "That is the privilege bug being fixed, but confirm none of them relied on "
                "it for legitimate access."
            )

        # --- Effect 3: users needing a global platform role ------------------
        cur.execute(
            """
            SELECT count(*) FROM users u WHERE NOT EXISTS (
                SELECT 1 FROM user_roles ur
                JOIN roles r ON r.id = ur.role_id
                WHERE ur.user_id = u.id AND ur.workspace_id IS NULL
                  AND r.is_workspace_role IS NOT TRUE
            )
            """
        )
        print(f"\nUsers to be given the global 'user' role: {cur.fetchone()[0]}")

        # --- Effect 4: non-active memberships --------------------------------
        cur.execute(
            "SELECT status, count(*) FROM workspace_members GROUP BY status ORDER BY 2 DESC"
        )
        rows = cur.fetchall()
        print(f"\nMembership statuses: {', '.join(f'{s}={c}' for s, c in rows)}")
        non_active = sum(c for s, c in rows if s != "active")
        if non_active:
            warnings.append(
                f"{non_active} membership(s) are not 'active'. WorkspacePermissionService now "
                "requires an active membership, so these users will be denied workspace "
                "permissions where the global role previously carried them through."
            )

    print("\n" + "=" * 70)
    for b in blockers:
        print(f"BLOCKER: {b}")
    for w in warnings:
        print(f"WARNING: {w}")
    if not blockers and not warnings:
        print("No blockers or warnings. Safe to deploy.")
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
