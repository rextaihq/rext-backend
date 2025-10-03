"""
Simple script to verify seed data in the database
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

# Get database URL from environment
db_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URI_CUSTOM")

# Parse connection string
if db_url and db_url.startswith("postgresql://"):
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()

    print("\n" + "="*80)
    print("SEED DATA VERIFICATION")
    print("="*80)

    # Check users
    cursor.execute("""
        SELECT email, display_name, email_verified, status
        FROM users
        WHERE id IN (
            '11111111-1111-1111-1111-111111111111',
            '22222222-2222-2222-2222-222222222222',
            '33333333-3333-3333-3333-333333333333',
            '44444444-4444-4444-4444-444444444444',
            '55555555-5555-5555-5555-555555555555'
        )
        ORDER BY email
    """)
    users = cursor.fetchall()

    print("\n✓ TEST USERS:")
    print("-" * 80)
    for user in users:
        email, display_name, verified, status = user
        print(f"  {email:30} | {display_name:20} | Verified: {verified} | {status}")

    # Check workspaces
    cursor.execute("""
        SELECT w.name, w.description, u.display_name as owner
        FROM workspace w
        JOIN users u ON w.user_id = u.id
        WHERE w.id IN (
            'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
            'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
            'cccccccc-cccc-cccc-cccc-cccccccccccc'
        )
        ORDER BY w.name
    """)
    workspaces = cursor.fetchall()

    print("\n✓ TEST WORKSPACES:")
    print("-" * 80)
    for ws in workspaces:
        name, description, owner = ws
        print(f"  {name:25} | Owner: {owner:20}")
        print(f"    → {description}")

    # Check workspace memberships
    cursor.execute("""
        SELECT
            w.name as workspace,
            u.display_name as member,
            r.display_name as role,
            wm.is_default
        FROM workspace_members wm
        JOIN workspace w ON wm.workspace_id = w.id
        JOIN users u ON wm.user_id = u.id
        LEFT JOIN user_roles ur ON ur.user_id = u.id AND ur.workspace_id = w.id
        LEFT JOIN roles r ON ur.role_id = r.id
        WHERE w.id IN (
            'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
            'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
            'cccccccc-cccc-cccc-cccc-cccccccccccc'
        )
        ORDER BY w.name, u.display_name
    """)
    memberships = cursor.fetchall()

    print("\n✓ WORKSPACE MEMBERSHIPS:")
    print("-" * 80)
    current_workspace = None
    for membership in memberships:
        workspace, member, role, is_default = membership
        if workspace != current_workspace:
            print(f"\n  {workspace}:")
            current_workspace = workspace
        default_marker = " [DEFAULT]" if is_default else ""
        print(f"    • {member:20} → {role}{default_marker}")

    # Check role assignments
    cursor.execute("""
        SELECT
            u.display_name,
            r.display_name as role,
            CASE WHEN ur.workspace_id IS NULL THEN 'Global' ELSE w.name END as scope
        FROM user_roles ur
        JOIN users u ON ur.user_id = u.id
        JOIN roles r ON ur.role_id = r.id
        LEFT JOIN workspace w ON ur.workspace_id = w.id
        WHERE u.id IN (
            '11111111-1111-1111-1111-111111111111',
            '22222222-2222-2222-2222-222222222222',
            '33333333-3333-3333-3333-333333333333',
            '44444444-4444-4444-4444-444444444444',
            '55555555-5555-5555-5555-555555555555'
        )
        ORDER BY u.display_name, ur.workspace_id NULLS FIRST
    """)
    roles = cursor.fetchall()

    print("\n✓ ROLE ASSIGNMENTS:")
    print("-" * 80)
    current_user = None
    for role_assignment in roles:
        user, role, scope = role_assignment
        if user != current_user:
            print(f"\n  {user}:")
            current_user = user
        print(f"    • {role:25} (Scope: {scope})")

    print("\n" + "="*80)
    print("✅ VERIFICATION COMPLETE")
    print("="*80)
    print("\nLogin Credentials for Testing:")
    print("  Email: admin@wrext.com | Password: Test1234!")
    print("  Email: john.doe@wrext.com | Password: Test1234!")
    print("  Email: jane.smith@wrext.com | Password: Test1234!")
    print("  Email: bob.wilson@wrext.com | Password: Test1234!")
    print("  Email: alice.johnson@wrext.com | Password: Test1234!")
    print("="*80 + "\n")

    cursor.close()
    conn.close()
else:
    print("ERROR: DATABASE_URL not found or invalid format")
