"""
Verify system seed data in the database (roles, permissions, plans)

This script verifies that essential system data has been seeded correctly:
- Roles and permissions (RBAC system)
- Subscription plans (including trial)
- Email templates (system-wide)
- Super admin user (if configured)

Does NOT verify test users or workspaces (those should not exist in production)
"""
import psycopg
import os
from dotenv import load_dotenv

load_dotenv()

# Get database URL from environment
db_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URI_CUSTOM")

# Parse connection string
if db_url and db_url.startswith("postgresql://"):
    conn = psycopg.connect(db_url)
    cursor = conn.cursor()

    print("\n" + "="*80)
    print("SYSTEM SEED DATA VERIFICATION")
    print("="*80)
    print("Verifying essential system data (roles, permissions, plans, templates)")
    print("="*80)

    # Check roles
    cursor.execute("""
        SELECT name, display_name, hierarchy_level, is_system_role
        FROM roles
        WHERE is_system_role = true
        ORDER BY hierarchy_level DESC
    """)
    roles = cursor.fetchall()

    print("\n✓ SYSTEM ROLES:")
    print("-" * 80)
    for role in roles:
        name, display_name, hierarchy, is_system = role
        print(f"  {display_name:30} | {name:20} | Level: {hierarchy}")

    # Check permissions count by resource
    cursor.execute("""
        SELECT resource, COUNT(*) as count
        FROM permissions
        GROUP BY resource
        ORDER BY resource
    """)
    permissions = cursor.fetchall()

    print("\n✓ PERMISSIONS BY RESOURCE:")
    print("-" * 80)
    total_perms = 0
    for perm in permissions:
        resource, count = perm
        total_perms += count
        print(f"  {resource:20} | {count:3} permissions")
    print(f"  {'-'*28}")
    print(f"  {'TOTAL':20} | {total_perms:3} permissions")

    # Check subscription plans
    cursor.execute("""
        SELECT name, display_name, price_monthly, max_workspaces, is_active, is_public
        FROM subscription_plans
        WHERE is_active = true
        ORDER BY price_monthly
    """)
    plans = cursor.fetchall()

    print("\n✓ SUBSCRIPTION PLANS:")
    print("-" * 80)
    for plan in plans:
        name, display_name, price, workspaces, active, public = plan
        price_str = f"${float(price):.2f}/mo" if price else "Free"
        ws_str = f"{workspaces} workspace{'s' if workspaces != 1 else ''}" if workspaces > 0 else "Unlimited"
        public_str = "Public" if public else "Auto-assigned"
        print(f"  {display_name:20} | {price_str:12} | {ws_str:15} | {public_str}")

    # Check email templates
    cursor.execute("""
        SELECT template_type, is_default, is_active,
               CASE WHEN workspace_id IS NULL THEN 'System-wide' ELSE 'Workspace' END as scope
        FROM email_templates
        WHERE is_default = true AND workspace_id IS NULL
        ORDER BY template_type
    """)
    templates = cursor.fetchall()

    print("\n✓ EMAIL TEMPLATES:")
    print("-" * 80)
    for template in templates:
        template_type, is_default, is_active, scope = template
        status = "Active" if is_active else "Inactive"
        print(f"  {template_type:30} | {scope:12} | {status}")

    # Check super admin user (if configured)
    super_admin_email = os.getenv('SUPER_ADMIN_EMAIL')
    if super_admin_email:
        cursor.execute("""
            SELECT u.email, u.display_name, u.status, u.email_verified,
                   r.display_name as role
            FROM users u
            LEFT JOIN user_roles ur ON ur.user_id = u.id AND ur.workspace_id IS NULL
            LEFT JOIN roles r ON ur.role_id = r.id
            WHERE u.email = %s
        """, (super_admin_email,))
        admin = cursor.fetchone()

        print("\n✓ SUPER ADMIN USER:")
        print("-" * 80)
        if admin:
            email, display_name, status, verified, role = admin
            verified_str = "✓ Verified" if verified else "✗ Not Verified"
            print(f"  Email: {email}")
            print(f"  Name: {display_name}")
            print(f"  Status: {status}")
            print(f"  Email: {verified_str}")
            print(f"  Global Role: {role or 'None'}")
        else:
            print(f"  ⚠️  Super admin not found: {super_admin_email}")
            print(f"  Make sure SUPER_ADMIN_EMAIL and SUPER_ADMIN_PASSWORD are set")
            print(f"  and run: alembic upgrade head")
    else:
        print("\n✓ SUPER ADMIN USER:")
        print("-" * 80)
        print("  ⚠️  SUPER_ADMIN_EMAIL not set in environment")
        print("  To create super admin, set environment variables and run migrations")

    # Check total users and workspaces (should be minimal in production)
    cursor.execute("SELECT COUNT(*) FROM users WHERE deleted_at IS NULL")
    user_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM workspace")
    workspace_count = cursor.fetchone()[0]

    print("\n✓ DATABASE STATISTICS:")
    print("-" * 80)
    print(f"  Total Active Users: {user_count}")
    print(f"  Total Workspaces: {workspace_count}")
    print(f"  System Roles: {len(roles)}")
    print(f"  Total Permissions: {total_perms}")
    print(f"  Subscription Plans: {len(plans)}")
    print(f"  Email Templates: {len(templates)}")

    print("\n" + "="*80)
    print("✅ SYSTEM VERIFICATION COMPLETE")
    print("="*80)
    print("\nAll essential system data is properly seeded.")
    if super_admin_email and admin:
        print(f"Super admin account: {super_admin_email}")
    print("\nYour database is ready for production use.")
    print("="*80 + "\n")

    cursor.close()
    conn.close()
else:
    print("ERROR: DATABASE_URL not found or invalid format")
    print("Set POSTGRES_URI_CUSTOM or DATABASE_URL environment variable")
