import psycopg
from datetime import datetime, timezone

# Connect to database
conn = psycopg.connect("postgresql://localhost/mobeen")

try:
    cursor = conn.cursor()

    # Add newuser to all 3 workspaces
    newuser_id = '3ed6b679-3e6c-4db2-9ca8-dd0b4a2b3ab1'
    workspaces = [
        'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',  # Acme Corporation
        'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',  # TechStartup Inc
        'cccccccc-cccc-cccc-cccc-cccccccccccc'   # Personal Blog
    ]

    print("Adding newuser to workspaces...")
    for workspace_id in workspaces:
        cursor.execute("""
            INSERT INTO workspace_members (id, workspace_id, user_id, is_default, status, joined_at)
            VALUES (gen_random_uuid(), %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (workspace_id, newuser_id, False, 'active', datetime.now(timezone.utc)))
        print(f"  - Added to workspace: {workspace_id}")

    conn.commit()
    print("\n✅ Successfully added newuser to all workspaces!")

    # Verify the memberships
    cursor.execute("""
        SELECT wm.workspace_id, w.name, wm.is_default, wm.status
        FROM workspace_members wm
        JOIN workspace w ON w.id = wm.workspace_id
        WHERE wm.user_id = %s
    """, (newuser_id,))
    memberships = cursor.fetchall()

    print(f"\n✅ Verified: newuser is now member of {len(memberships)} workspace(s):")
    for membership in memberships:
        print(f"  - {membership[1]} (default: {membership[2]}, status: {membership[3]})")

finally:
    cursor.close()
    conn.close()
