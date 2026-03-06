-- ============================================================================
-- Permission Matrix Generator
-- ============================================================================
-- This SQL script generates a complete permission matrix showing which
-- permissions are assigned to each role.
--
-- Usage:
--   psql -d rext_db -f scripts/generate_permission_matrix.sql > matrix.txt
--   OR
--   Run via DBeaver, pgAdmin, or any PostgreSQL client
--
-- Output: Visual matrix with ✅ for granted permissions, ❌ for denied
-- ============================================================================

-- Enable extended display for better readability
\x off

-- Set formatting
\pset border 2
\pset format aligned

-- ============================================================================
-- SECTION 1: Workspace Roles Permission Matrix
-- ============================================================================
\echo ''
\echo '========================================='
\echo 'WORKSPACE ROLES PERMISSION MATRIX'
\echo '========================================='
\echo ''

SELECT
    p.name as permission,
    p.resource,
    p.action,
    CASE WHEN bool_or(r.name = 'workspace_owner' AND rp.id IS NOT NULL) THEN '✅' ELSE '❌' END as owner,
    CASE WHEN bool_or(r.name = 'workspace_admin' AND rp.id IS NOT NULL) THEN '✅' ELSE '❌' END as admin,
    CASE WHEN bool_or(r.name = 'editor' AND rp.id IS NOT NULL) THEN '✅' ELSE '❌' END as editor,
    CASE WHEN bool_or(r.name = 'viewer' AND rp.id IS NOT NULL) THEN '✅' ELSE '❌' END as viewer
FROM permissions p
CROSS JOIN roles r
LEFT JOIN role_permissions rp ON rp.permission_id = p.id AND rp.role_id = r.id
WHERE r.name IN ('workspace_owner', 'workspace_admin', 'editor', 'viewer')
  AND p.resource IN ('workspace', 'subscription', 'billing', 'usage', 'content', 'topic', 'knowledge', 'media', 'member', 'license')
GROUP BY p.id, p.name, p.resource, p.action
ORDER BY p.resource, p.action;

-- ============================================================================
-- SECTION 2: Global Roles Permission Matrix
-- ============================================================================
\echo ''
\echo '========================================='
\echo 'GLOBAL ROLES PERMISSION MATRIX'
\echo '========================================='
\echo ''

SELECT
    p.name as permission,
    p.resource,
    p.action,
    CASE WHEN bool_or(r.name = 'super_admin' AND rp.id IS NOT NULL) THEN '✅' ELSE '❌' END as super_admin,
    CASE WHEN bool_or(r.name = 'admin' AND rp.id IS NOT NULL) THEN '✅' ELSE '❌' END as admin,
    CASE WHEN bool_or(r.name = 'support' AND rp.id IS NOT NULL) THEN '✅' ELSE '❌' END as support,
    CASE WHEN bool_or(r.name = 'user' AND rp.id IS NOT NULL) THEN '✅' ELSE '❌' END as user
FROM permissions p
CROSS JOIN roles r
LEFT JOIN role_permissions rp ON rp.permission_id = p.id AND rp.role_id = r.id
WHERE r.name IN ('super_admin', 'admin', 'support', 'user')
  AND p.resource IN ('user', 'role', 'permission', 'audit', 'support', 'workspace')
GROUP BY p.id, p.name, p.resource, p.action
ORDER BY p.resource, p.action;

-- ============================================================================
-- SECTION 3: Role Permission Counts
-- ============================================================================
\echo ''
\echo '========================================='
\echo 'ROLE PERMISSION COUNTS'
\echo '========================================='
\echo ''

SELECT
    r.name as role_name,
    r.display_name,
    r.is_workspace_role,
    r.is_system_role,
    COUNT(rp.id) as permission_count,
    r.hierarchy_level
FROM roles r
LEFT JOIN role_permissions rp ON rp.role_id = r.id
GROUP BY r.id, r.name, r.display_name, r.is_workspace_role, r.is_system_role, r.hierarchy_level
ORDER BY r.hierarchy_level DESC;

-- ============================================================================
-- SECTION 4: Permission Coverage by Resource
-- ============================================================================
\echo ''
\echo '========================================='
\echo 'PERMISSION COVERAGE BY RESOURCE'
\echo '========================================='
\echo ''

SELECT
    p.resource,
    COUNT(DISTINCT p.id) as total_permissions,
    COUNT(DISTINCT CASE WHEN r.name = 'workspace_owner' THEN p.id END) as owner_has,
    COUNT(DISTINCT CASE WHEN r.name = 'workspace_admin' THEN p.id END) as admin_has,
    COUNT(DISTINCT CASE WHEN r.name = 'editor' THEN p.id END) as editor_has,
    COUNT(DISTINCT CASE WHEN r.name = 'viewer' THEN p.id END) as viewer_has
FROM permissions p
LEFT JOIN role_permissions rp ON rp.permission_id = p.id
LEFT JOIN roles r ON r.id = rp.role_id AND r.name IN ('workspace_owner', 'workspace_admin', 'editor', 'viewer')
WHERE p.resource IN ('workspace', 'subscription', 'billing', 'usage', 'content', 'topic', 'knowledge', 'media', 'member', 'license')
GROUP BY p.resource
ORDER BY p.resource;

-- ============================================================================
-- SECTION 5: Critical Permission Checks
-- ============================================================================
\echo ''
\echo '========================================='
\echo 'CRITICAL PERMISSION CHECKS'
\echo '========================================='
\echo ''

-- Verify owner-only permissions
SELECT
    'OWNER ONLY: Subscription.read' as check_description,
    CASE WHEN EXISTS (
        SELECT 1 FROM roles r
        JOIN role_permissions rp ON rp.role_id = r.id
        JOIN permissions p ON p.id = rp.permission_id
        WHERE r.name = 'workspace_owner' AND p.name = 'subscription.read'
    ) THEN '✅ PASS' ELSE '❌ FAIL' END as owner_has,
    CASE WHEN NOT EXISTS (
        SELECT 1 FROM roles r
        JOIN role_permissions rp ON rp.role_id = r.id
        JOIN permissions p ON p.id = rp.permission_id
        WHERE r.name IN ('workspace_admin', 'editor', 'viewer') AND p.name = 'subscription.read'
    ) THEN '✅ PASS' ELSE '❌ FAIL' END as others_dont_have

UNION ALL

SELECT
    'OWNER ONLY: Billing.read',
    CASE WHEN EXISTS (
        SELECT 1 FROM roles r
        JOIN role_permissions rp ON rp.role_id = r.id
        JOIN permissions p ON p.id = rp.permission_id
        WHERE r.name = 'workspace_owner' AND p.name = 'billing.read'
    ) THEN '✅ PASS' ELSE '❌ FAIL' END,
    CASE WHEN NOT EXISTS (
        SELECT 1 FROM roles r
        JOIN role_permissions rp ON rp.role_id = r.id
        JOIN permissions p ON p.id = rp.permission_id
        WHERE r.name IN ('workspace_admin', 'editor', 'viewer') AND p.name = 'billing.read'
    ) THEN '✅ PASS' ELSE '❌ FAIL' END

UNION ALL

SELECT
    'OWNER ONLY: Workspace.delete',
    CASE WHEN EXISTS (
        SELECT 1 FROM roles r
        JOIN role_permissions rp ON rp.role_id = r.id
        JOIN permissions p ON p.id = rp.permission_id
        WHERE r.name = 'workspace_owner' AND p.name = 'workspace.delete'
    ) THEN '✅ PASS' ELSE '❌ FAIL' END,
    CASE WHEN NOT EXISTS (
        SELECT 1 FROM roles r
        JOIN role_permissions rp ON rp.role_id = r.id
        JOIN permissions p ON p.id = rp.permission_id
        WHERE r.name IN ('workspace_admin', 'editor', 'viewer') AND p.name = 'workspace.delete'
    ) THEN '✅ PASS' ELSE '❌ FAIL' END

UNION ALL

SELECT
    'EDITOR: Can publish content',
    CASE WHEN EXISTS (
        SELECT 1 FROM roles r
        JOIN role_permissions rp ON rp.role_id = r.id
        JOIN permissions p ON p.id = rp.permission_id
        WHERE r.name = 'editor' AND p.name = 'content.publish'
    ) THEN '✅ PASS' ELSE '❌ FAIL' END,
    'N/A'

UNION ALL

SELECT
    'EDITOR: Cannot delete content',
    'N/A',
    CASE WHEN NOT EXISTS (
        SELECT 1 FROM roles r
        JOIN role_permissions rp ON rp.role_id = r.id
        JOIN permissions p ON p.id = rp.permission_id
        WHERE r.name = 'editor' AND p.name = 'content.delete'
    ) THEN '✅ PASS' ELSE '❌ FAIL' END

UNION ALL

SELECT
    'VIEWER: Can read content',
    CASE WHEN EXISTS (
        SELECT 1 FROM roles r
        JOIN role_permissions rp ON rp.role_id = r.id
        JOIN permissions p ON p.id = rp.permission_id
        WHERE r.name = 'viewer' AND p.name = 'content.read'
    ) THEN '✅ PASS' ELSE '❌ FAIL' END,
    'N/A'

UNION ALL

SELECT
    'VIEWER: Cannot update content',
    'N/A',
    CASE WHEN NOT EXISTS (
        SELECT 1 FROM roles r
        JOIN role_permissions rp ON rp.role_id = r.id
        JOIN permissions p ON p.id = rp.permission_id
        WHERE r.name = 'viewer' AND p.name = 'content.update'
    ) THEN '✅ PASS' ELSE '❌ FAIL' END;

-- ============================================================================
-- SECTION 6: Export as CSV (Optional)
-- ============================================================================
\echo ''
\echo '========================================='
\echo 'CSV EXPORT QUERY'
\echo '========================================='
\echo 'Run the following to export as CSV:'
\echo '\copy (SELECT p.name, p.resource, p.action, ...) TO ''permission_matrix.csv'' CSV HEADER'
\echo ''

-- Generate CSV-ready output
\copy (SELECT p.name as permission, p.resource, p.action, CASE WHEN bool_or(r.name = 'workspace_owner' AND rp.id IS NOT NULL) THEN 'YES' ELSE 'NO' END as owner, CASE WHEN bool_or(r.name = 'workspace_admin' AND rp.id IS NOT NULL) THEN 'YES' ELSE 'NO' END as admin, CASE WHEN bool_or(r.name = 'editor' AND rp.id IS NOT NULL) THEN 'YES' ELSE 'NO' END as editor, CASE WHEN bool_or(r.name = 'viewer' AND rp.id IS NOT NULL) THEN 'YES' ELSE 'NO' END as viewer FROM permissions p CROSS JOIN roles r LEFT JOIN role_permissions rp ON rp.permission_id = p.id AND rp.role_id = r.id WHERE r.name IN ('workspace_owner', 'workspace_admin', 'editor', 'viewer') AND p.resource IN ('workspace', 'subscription', 'billing', 'usage', 'content', 'topic', 'knowledge', 'media', 'member', 'license') GROUP BY p.id, p.name, p.resource, p.action ORDER BY p.resource, p.action) TO '/tmp/permission_matrix.csv' CSV HEADER;

\echo ''
\echo '✅ CSV exported to /tmp/permission_matrix.csv'
\echo ''
