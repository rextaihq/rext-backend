-- Final permission fixes
BEGIN;

-- Add support role permissions
INSERT INTO role_permissions (id, role_id, permission_id, created_at)
SELECT gen_random_uuid(), r.id, p.id, NOW()
FROM roles r CROSS JOIN permissions p
WHERE r.name = 'support'
  AND p.name IN ('workspace.read', 'content.read', 'topic.read', 'knowledge.read', 'media.read', 'media.view', 'member.read', 'license.read', 'license.view', 'audit.read', 'support.view_workspace', 'support.view_billing')
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id);

-- Add media.view to user
INSERT INTO role_permissions (id, role_id, permission_id, created_at)
SELECT gen_random_uuid(), r.id, p.id, NOW()
FROM roles r CROSS JOIN permissions p
WHERE r.name = 'user' AND p.name = 'media.view'
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id);

-- Add license.read and removed non-canonical perms to super_admin
INSERT INTO role_permissions (id, role_id, permission_id, created_at)
SELECT gen_random_uuid(), r.id, p.id, NOW()
FROM roles r CROSS JOIN permissions p
WHERE r.name = 'super_admin' AND p.name = 'license.read'
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id);

-- Add admin.invite to admin
INSERT INTO role_permissions (id, role_id, permission_id, created_at)
SELECT gen_random_uuid(), r.id, p.id, NOW()
FROM roles r CROSS JOIN permissions p
WHERE r.name = 'admin' AND p.name = 'admin.invite'
  AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id);

COMMIT;

-- Show final counts
SELECT r.name, COUNT(rp.id) as permission_count
FROM roles r
LEFT JOIN role_permissions rp ON rp.role_id = r.id
WHERE r.name IN ('workspace_owner', 'workspace_admin', 'editor', 'viewer', 'admin', 'support', 'user', 'super_admin')
GROUP BY r.name
ORDER BY r.name;
