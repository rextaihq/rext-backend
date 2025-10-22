import psycopg

# Connect to database
conn = psycopg.connect("postgresql://localhost/mobeen")

try:
    cursor = conn.cursor()

    # Check users
    cursor.execute("SELECT id, email, username FROM users WHERE deleted_at IS NULL;")
    users = cursor.fetchall()
    print(f"Total users: {len(users)}")
    for user in users:
        print(f"  - User: {user[0]}, {user[1]}, {user[2]}")

    # Check workspaces
    cursor.execute("SELECT id, name, user_id FROM workspace;")
    workspaces = cursor.fetchall()
    print(f"\nTotal workspaces: {len(workspaces)}")
    for ws in workspaces:
        print(f"  - Workspace: {ws[0]}, {ws[1]}, owner: {ws[2]}")

    # Check workspace members
    cursor.execute("SELECT id, workspace_id, user_id, is_default FROM workspace_members;")
    members = cursor.fetchall()
    print(f"\nTotal workspace members: {len(members)}")
    for member in members:
        print(f"  - Member: workspace_id={member[1]}, user_id={member[2]}, is_default={member[3]}")

finally:
    cursor.close()
    conn.close()
