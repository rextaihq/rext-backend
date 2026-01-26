-- ============================================================================
-- Fix Permission Discrepancies
-- ============================================================================
-- This SQL script fixes all 25 permission discrepancies found by the
-- verify_permission_matrix.py script.
--
-- Usage:
--   psql -d rext_db -f scripts/fix_permission_discrepancies.sql
--
-- Author: Claude Code (RBAC Task 4.1 Discrepancy Fixes)
-- Date: 2025-10-25
-- ============================================================================

\echo ''
\echo '========================================='
\echo 'STARTING PERMISSION DISCREPANCY FIXES'
\echo '========================================='
\echo ''

-- Start transaction
BEGIN;

-- ============================================================================
-- STEP 1: Add missing license.read permission (canonical version)
-- ============================================================================
\echo 'Step 1: Adding license.read permission (canonical)...'

INSERT INTO permissions (id, name, display_name, description, resource, action, created_at)
VALUES (
    gen_random_uuid(),
    'license.read',
    'View Licenses (Canonical)',
    'View own license keys and activations (canonical)',
    'license',
    'read',
    NOW()
)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    description = EXCLUDED.description;

\echo '✅ license.read permission added/updated'

-- ============================================================================
-- STEP 2: Remove non-canonical workspace permissions from roles
-- ============================================================================
\echo ''
\echo 'Step 2: Removing non-canonical workspace permissions...'

-- Remove workspace.manage_billing (should use billing.manage instead)
DELETE FROM role_permissions
WHERE role_id IN (SELECT id FROM roles WHERE name IN ('workspace_owner', 'super_admin'))
  AND permission_id = (SELECT id FROM permissions WHERE name = 'workspace.manage_billing');

\echo '  - Removed workspace.manage_billing from owner/super_admin'

-- Remove workspace.transfer_ownership (should use workspace.transfer instead)
DELETE FROM role_permissions
WHERE role_id IN (SELECT id FROM roles WHERE name IN ('workspace_owner', 'super_admin'))
  AND permission_id = (SELECT id FROM permissions WHERE name = 'workspace.transfer_ownership');

\echo '  - Removed workspace.transfer_ownership from owner/super_admin'
\echo '✅ Non-canonical workspace permissions removed'

-- ============================================================================
-- STEP 3: Remove user.read from workspace roles (global permission only)
-- ============================================================================
\echo ''
\echo 'Step 3: Removing user.read from workspace roles...'

DELETE FROM role_permissions
WHERE role_id IN (SELECT id FROM roles WHERE name IN ('workspace_owner', 'workspace_admin', 'editor', 'viewer'))
  AND permission_id = (SELECT id FROM permissions WHERE name = 'user.read');

\echo '✅ user.read removed from workspace roles (now admin-only)'

-- ============================================================================
-- STEP 4: Fix editor role permissions
-- ============================================================================
\echo ''
\echo 'Step 4: Fixing editor role permissions...'

-- Remove license activate/deactivate from editor
DELETE FROM role_permissions
WHERE role_id = (SELECT id FROM roles WHERE name = 'editor')
  AND permission_id IN (
    SELECT id FROM permissions WHERE name IN ('license.activate', 'license.deactivate')
  );

\echo '  - Removed license activate/deactivate from editor'

-- Remove media delete/update from editor
DELETE FROM role_permissions
WHERE role_id = (SELECT id FROM roles WHERE name = 'editor')
  AND permission_id IN (
    SELECT id FROM permissions WHERE name IN ('media.delete', 'media.update')
  );

\echo '  - Removed media.delete and media.update from editor'

-- Add license.read to editor
INSERT INTO role_permissions (id, role_id, permission_id, created_at)
SELECT
    gen_random_uuid(),
    (SELECT id FROM roles WHERE name = 'editor'),
    (SELECT id FROM permissions WHERE name = 'license.read'),
    NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions rp
    WHERE rp.role_id = (SELECT id FROM roles WHERE name = 'editor')
      AND rp.permission_id = (SELECT id FROM permissions WHERE name = 'license.read')
);

\echo '  - Added license.read to editor'

-- Add content.approve to editor
INSERT INTO role_permissions (id, role_id, permission_id, created_at)
SELECT
    gen_random_uuid(),
    (SELECT id FROM roles WHERE name = 'editor'),
    (SELECT id FROM permissions WHERE name = 'content.approve'),
    NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions rp
    WHERE rp.role_id = (SELECT id FROM roles WHERE name = 'editor')
      AND rp.permission_id = (SELECT id FROM permissions WHERE name = 'content.approve')
);

\echo '  - Added content.approve to editor'

-- Add content.reject to editor
INSERT INTO role_permissions (id, role_id, permission_id, created_at)
SELECT
    gen_random_uuid(),
    (SELECT id FROM roles WHERE name = 'editor'),
    (SELECT id FROM permissions WHERE name = 'content.reject'),
    NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions rp
    WHERE rp.role_id = (SELECT id FROM roles WHERE name = 'editor')
      AND rp.permission_id = (SELECT id FROM permissions WHERE name = 'content.reject')
);

\echo '  - Added content.reject to editor'
\echo '✅ Editor role fixed'

-- ============================================================================
-- STEP 5: Fix viewer role permissions
-- ============================================================================
\echo ''
\echo 'Step 5: Fixing viewer role permissions...'

-- Remove license activate/deactivate from viewer
DELETE FROM role_permissions
WHERE role_id = (SELECT id FROM roles WHERE name = 'viewer')
  AND permission_id IN (
    SELECT id FROM permissions WHERE name IN ('license.activate', 'license.deactivate')
  );

\echo '  - Removed license activate/deactivate from viewer'

-- Add license.read to viewer
INSERT INTO role_permissions (id, role_id, permission_id, created_at)
SELECT
    gen_random_uuid(),
    (SELECT id FROM roles WHERE name = 'viewer'),
    (SELECT id FROM permissions WHERE name = 'license.read'),
    NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions rp
    WHERE rp.role_id = (SELECT id FROM roles WHERE name = 'viewer')
      AND rp.permission_id = (SELECT id FROM permissions WHERE name = 'license.read')
);

\echo '  - Added license.read to viewer'
\echo '✅ Viewer role fixed'

-- ============================================================================
-- STEP 6: Fix workspace_admin role permissions
-- ============================================================================
\echo ''
\echo 'Step 6: Fixing workspace_admin role permissions...'

-- Remove license.deactivate from workspace_admin
DELETE FROM role_permissions
WHERE role_id = (SELECT id FROM roles WHERE name = 'workspace_admin')
  AND permission_id = (SELECT id FROM permissions WHERE name = 'license.deactivate');

\echo '  - Removed license.deactivate from workspace_admin'

-- Add license.read to workspace_admin
INSERT INTO role_permissions (id, role_id, permission_id, created_at)
SELECT
    gen_random_uuid(),
    (SELECT id FROM roles WHERE name = 'workspace_admin'),
    (SELECT id FROM permissions WHERE name = 'license.read'),
    NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions rp
    WHERE rp.role_id = (SELECT id FROM roles WHERE name = 'workspace_admin')
      AND rp.permission_id = (SELECT id FROM permissions WHERE name = 'license.read')
);

\echo '  - Added license.read to workspace_admin'
\echo '✅ Workspace Admin role fixed'

-- ============================================================================
-- STEP 7: Fix workspace_owner role permissions
-- ============================================================================
\echo ''
\echo 'Step 7: Fixing workspace_owner role permissions...'

-- Add license.read to workspace_owner
INSERT INTO role_permissions (id, role_id, permission_id, created_at)
SELECT
    gen_random_uuid(),
    (SELECT id FROM roles WHERE name = 'workspace_owner'),
    (SELECT id FROM permissions WHERE name = 'license.read'),
    NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions rp
    WHERE rp.role_id = (SELECT id FROM roles WHERE name = 'workspace_owner')
      AND rp.permission_id = (SELECT id FROM permissions WHERE name = 'license.read')
);

\echo '  - Added license.read to workspace_owner'
\echo '✅ Workspace Owner role fixed'

-- ============================================================================
-- STEP 8: Fix admin role permissions
-- ============================================================================
\echo ''
\echo 'Step 8: Fixing admin (global) role permissions...'

-- Add missing permissions to admin
DO $$
DECLARE
    admin_role_id UUID;
    perm RECORD;
    missing_perms TEXT[] := ARRAY[
        'admin.invite',
        'license.read',
        'license.revoke',
        'permission.create',
        'permission.update',
        'role.create',
        'workspace.transfer'
    ];
    perm_name TEXT;
BEGIN
    SELECT id INTO admin_role_id FROM roles WHERE name = 'admin';

    FOREACH perm_name IN ARRAY missing_perms LOOP
        INSERT INTO role_permissions (id, role_id, permission_id, created_at)
        SELECT
            gen_random_uuid(),
            admin_role_id,
            p.id,
            NOW()
        FROM permissions p
        WHERE p.name = perm_name
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = admin_role_id
                AND rp.permission_id = p.id
          );

        RAISE NOTICE '  - Added % to admin', perm_name;
    END LOOP;
END $$;

\echo '✅ Admin role fixed'

-- ============================================================================
-- STEP 9: Seed support role permissions (currently has 0)
-- ============================================================================
\echo ''
\echo 'Step 9: Seeding support role permissions...'

-- Add all permissions for support role
DO $$
DECLARE
    support_role_id UUID;
    support_perms TEXT[] := ARRAY[
        'workspace.read',
        'content.read',
        'topic.read',
        'knowledge.read',
        'media.read',
        'media.view',
        'member.read',
        'license.read',
        'license.view',
        'audit.read',
        'support.view_workspace',
        'support.view_billing'
    ];
    perm_name TEXT;
BEGIN
    SELECT id INTO support_role_id FROM roles WHERE name = 'support';

    IF support_role_id IS NULL THEN
        RAISE NOTICE 'WARNING: support role does not exist in database!';
    ELSE
        FOREACH perm_name IN ARRAY support_perms LOOP
            INSERT INTO role_permissions (id, role_id, permission_id, created_at)
            SELECT
                gen_random_uuid(),
                support_role_id,
                p.id,
                NOW()
            FROM permissions p
            WHERE p.name = perm_name
              AND NOT EXISTS (
                  SELECT 1 FROM role_permissions rp
                  WHERE rp.role_id = support_role_id
                    AND rp.permission_id = p.id
              );

            RAISE NOTICE '  - Added % to support', perm_name;
        END LOOP;
    END IF;
END $$;

\echo '✅ Support role seeded'

-- ============================================================================
-- STEP 10: Fix user (default) role permissions
-- ============================================================================
\echo ''
\echo 'Step 10: Fixing user (default) role permissions...'

-- Remove license activate/deactivate from user
DELETE FROM role_permissions
WHERE role_id = (SELECT id FROM roles WHERE name = 'user')
  AND permission_id IN (
    SELECT id FROM permissions WHERE name IN ('license.activate', 'license.deactivate')
  );

\echo '  - Removed license activate/deactivate from user'

-- Add license.read to user
INSERT INTO role_permissions (id, role_id, permission_id, created_at)
SELECT
    gen_random_uuid(),
    (SELECT id FROM roles WHERE name = 'user'),
    (SELECT id FROM permissions WHERE name = 'license.read'),
    NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM role_permissions rp
    WHERE rp.role_id = (SELECT id FROM roles WHERE name = 'user')
      AND rp.permission_id = (SELECT id FROM permissions WHERE name = 'license.read')
);

\echo '  - Added license.read to user'
\echo '✅ User role fixed'

-- ============================================================================
-- FINAL STEP: Commit transaction
-- ============================================================================
\echo ''
\echo '========================================='
\echo 'ALL FIXES APPLIED SUCCESSFULLY'
\echo '========================================='
\echo ''
\echo 'Committing transaction...'

COMMIT;

\echo '✅ Transaction committed'
\echo ''
\echo 'Please run verify_permission_matrix.py to confirm 0 discrepancies!'
\echo ''
