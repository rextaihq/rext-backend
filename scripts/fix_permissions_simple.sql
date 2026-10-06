-- Simple permission fixes without complex DO blocks
-- Run directly in Docker: docker exec rext-backend-langgraph-postgres-1 psql -U postgres -d postgres -f /tmp/fix.sql

BEGIN;

-- Step 1: Add license.read permission
INSERT INTO permissions (id, name, display_name, description, resource, action, created_at)
VALUES (gen_random_uuid(), 'license.read', 'View Licenses (Canonical)', 'View own license keys and activations (canonical)', 'license', 'read', NOW());

-- Step 2: Remove non-canonical workspace permissions
DELETE FROM role_permissions WHERE permission_id IN (
  SELECT id FROM permissions WHERE name IN ('workspace.manage_billing', 'workspace.transfer_ownership')
);

-- Step 3: Remove user.read from workspace roles
DELETE FROM role_permissions
WHERE role_id IN (SELECT id FROM roles WHERE name IN ('workspace_owner', 'workspace_admin', 'editor', 'viewer'))
  AND permission_id = (SELECT id FROM permissions WHERE name = 'user.read');

-- Step 4: Fix editor role
DELETE FROM role_permissions WHERE role_id = (SELECT id FROM roles WHERE name = 'editor')
  AND permission_id IN (SELECT id FROM permissions WHERE name IN ('license.activate', 'license.deactivate', 'media.delete', 'media.update'));

INSERT INTO role_permissions (id, role_id, permission_id, created_at)
SELECT gen_random_uuid(), r.id, p.id, NOW()
FROM roles r CROSS JOIN permissions p
WHERE r.name = 'editor' AND p.name IN ('license.read', 'content.approve', 'content.reject')
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id);

-- Step 5: Fix viewer role
DELETE FROM role_permissions WHERE role_id = (SELECT id FROM roles WHERE name = 'viewer')
  AND permission_id IN (SELECT id FROM permissions WHERE name IN ('license.activate', 'license.deactivate'));

INSERT INTO role_permissions (id, role_id, permission_id, created_at)
SELECT gen_random_uuid(), r.id, p.id, NOW()
FROM roles r CROSS JOIN permissions p
WHERE r.name = 'viewer' AND p.name = 'license.read'
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id);

-- Step 6: Fix workspace_admin
DELETE FROM role_permissions WHERE role_id = (SELECT id FROM roles WHERE name = 'workspace_admin')
  AND permission_id = (SELECT id FROM permissions WHERE name = 'license.deactivate');

INSERT INTO role_permissions (id, role_id, permission_id, created_at)
SELECT gen_random_uuid(), r.id, p.id, NOW()
FROM roles r CROSS JOIN permissions p
WHERE r.name = 'workspace_admin' AND p.name = 'license.read'
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id);

-- Step 7: Fix workspace_owner
INSERT INTO role_permissions (id, role_id, permission_id, created_at)
SELECT gen_random_uuid(), r.id, p.id, NOW()
FROM roles r CROSS JOIN permissions p
WHERE r.name = 'workspace_owner' AND p.name = 'license.read'
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id);

-- Step 8: Fix admin role
INSERT INTO role_permissions (id, role_id, permission_id, created_at)
SELECT gen_random_uuid(), r.id, p.id, NOW()
FROM roles r CROSS JOIN permissions p
WHERE r.name = 'admin' AND p.name IN ('admin.invite', 'license.read', 'license.revoke', 'permission.create', 'permission.update', 'role.create', 'workspace.transfer')
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id);

-- Step 9: Seed support role (all 12 permissions)
INSERT INTO role_permissions (id, role_id, permission_id, created_at)
SELECT gen_random_uuid(), r.id, p.id, NOW()
FROM roles r CROSS JOIN permissions p
WHERE r.name = 'support'
  AND p.name IN ('workspace.read', 'content.read', 'media.read', 'media.view', 'member.read', 'license.read', 'license.view', 'audit.read', 'support.view_workspace', 'support.view_billing')
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id);

-- Step 10: Fix user role
DELETE FROM role_permissions WHERE role_id = (SELECT id FROM roles WHERE name = 'user')
  AND permission_id IN (SELECT id FROM permissions WHERE name IN ('license.activate', 'license.deactivate'));

INSERT INTO role_permissions (id, role_id, permission_id, created_at)
SELECT gen_random_uuid(), r.id, p.id, NOW()
FROM roles r CROSS JOIN permissions p
WHERE r.name = 'user' AND p.name = 'license.read'
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id);

COMMIT;

-- Verify counts
SELECT r.name, COUNT(rp.id) as permission_count
FROM roles r
LEFT JOIN role_permissions rp ON rp.role_id = r.id
WHERE r.name IN ('workspace_owner', 'workspace_admin', 'editor', 'viewer', 'admin', 'support', 'user', 'super_admin')
GROUP BY r.name
ORDER BY r.name;
