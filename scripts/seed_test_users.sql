-- RBAC Test Users Seed Script
-- Creates 5 test users with different roles for automated testing
--
-- Test Credentials (all users):
-- Password: TestPassword123!
-- Password Hash: (bcrypt hash of "TestPassword123!")

-- Note: You need to generate the password hash using bcrypt
-- In Python: from bcrypt import hashpw, gensalt; hashpw(b"TestPassword123!", gensalt()).decode()
-- Hash: $2b$12$rr7E8YPxZqc5JkBfgUF3cuY0I4c.Qix46/Hv6gv.KyrJVCCa50rca

BEGIN;

-- Step 1: Create test users first (to satisfy foreign key constraints)
-- Owner
INSERT INTO users (id, email, username, password_hash, first_name, last_name, display_name, status, email_verified, created_at, updated_at)
VALUES (
    '00000000-0000-0000-0000-000000000010'::uuid,
    'owner@test.com',
    'testowner',
    '$2b$12$rr7E8YPxZqc5JkBfgUF3cuY0I4c.Qix46/Hv6gv.KyrJVCCa50rca',
    'Test',
    'Owner',
    'Test Owner',
    'active',
    true,
    NOW(),
    NOW()
)
ON CONFLICT (email) DO UPDATE SET updated_at = NOW();

-- Admin
INSERT INTO users (id, email, username, password_hash, first_name, last_name, display_name, status, email_verified, created_at, updated_at)
VALUES (
    '00000000-0000-0000-0000-000000000011'::uuid,
    'admin@test.com',
    'testadmin',
    '$2b$12$rr7E8YPxZqc5JkBfgUF3cuY0I4c.Qix46/Hv6gv.KyrJVCCa50rca',
    'Test',
    'Admin',
    'Test Admin',
    'active',
    true,
    NOW(),
    NOW()
)
ON CONFLICT (email) DO UPDATE SET updated_at = NOW();

-- Editor
INSERT INTO users (id, email, username, password_hash, first_name, last_name, display_name, status, email_verified, created_at, updated_at)
VALUES (
    '00000000-0000-0000-0000-000000000012'::uuid,
    'editor@test.com',
    'testeditor',
    '$2b$12$rr7E8YPxZqc5JkBfgUF3cuY0I4c.Qix46/Hv6gv.KyrJVCCa50rca',
    'Test',
    'Editor',
    'Test Editor',
    'active',
    true,
    NOW(),
    NOW()
)
ON CONFLICT (email) DO UPDATE SET updated_at = NOW();

-- Viewer
INSERT INTO users (id, email, username, password_hash, first_name, last_name, display_name, status, email_verified, created_at, updated_at)
VALUES (
    '00000000-0000-0000-0000-000000000013'::uuid,
    'viewer@test.com',
    'testviewer',
    '$2b$12$rr7E8YPxZqc5JkBfgUF3cuY0I4c.Qix46/Hv6gv.KyrJVCCa50rca',
    'Test',
    'Viewer',
    'Test Viewer',
    'active',
    true,
    NOW(),
    NOW()
)
ON CONFLICT (email) DO UPDATE SET updated_at = NOW();

-- Super Admin
INSERT INTO users (id, email, username, password_hash, first_name, last_name, display_name, status, email_verified, created_at, updated_at)
VALUES (
    '00000000-0000-0000-0000-000000000014'::uuid,
    'superadmin@test.com',
    'testsuperadmin',
    '$2b$12$rr7E8YPxZqc5JkBfgUF3cuY0I4c.Qix46/Hv6gv.KyrJVCCa50rca',
    'Test',
    'SuperAdmin',
    'Test Super Admin',
    'active',
    true,
    NOW(),
    NOW()
)
ON CONFLICT (email) DO UPDATE SET updated_at = NOW();

-- Step 2: Create test workspace (after users exist)
INSERT INTO workspace (id, slug, name, user_id, created_at, updated_at)
VALUES (
    '00000000-0000-0000-0000-000000000001'::uuid,
    'test-workspace',
    'Test Workspace',
    '00000000-0000-0000-0000-000000000010'::uuid,  -- owner user ID (created above)
    NOW(),
    NOW()
)
ON CONFLICT (slug) DO NOTHING;

-- Step 3: Assign roles to users
-- workspace_owner role
INSERT INTO user_roles (id, user_id, role_id, workspace_id, is_primary, assigned_at)
SELECT
    gen_random_uuid(),
    '00000000-0000-0000-0000-000000000010'::uuid,
    r.id,
    '00000000-0000-0000-0000-000000000001'::uuid,
    true,
    NOW()
FROM roles r
WHERE r.name = 'workspace_owner'
ON CONFLICT DO NOTHING;

-- workspace_admin role
INSERT INTO user_roles (id, user_id, role_id, workspace_id, is_primary, assigned_at)
SELECT
    gen_random_uuid(),
    '00000000-0000-0000-0000-000000000011'::uuid,
    r.id,
    '00000000-0000-0000-0000-000000000001'::uuid,
    true,
    NOW()
FROM roles r
WHERE r.name = 'workspace_admin'
ON CONFLICT DO NOTHING;

-- editor role
INSERT INTO user_roles (id, user_id, role_id, workspace_id, is_primary, assigned_at)
SELECT
    gen_random_uuid(),
    '00000000-0000-0000-0000-000000000012'::uuid,
    r.id,
    '00000000-0000-0000-0000-000000000001'::uuid,
    true,
    NOW()
FROM roles r
WHERE r.name = 'editor'
ON CONFLICT DO NOTHING;

-- viewer role
INSERT INTO user_roles (id, user_id, role_id, workspace_id, is_primary, assigned_at)
SELECT
    gen_random_uuid(),
    '00000000-0000-0000-0000-000000000013'::uuid,
    r.id,
    '00000000-0000-0000-0000-000000000001'::uuid,
    true,
    NOW()
FROM roles r
WHERE r.name = 'viewer'
ON CONFLICT DO NOTHING;

-- super_admin role (global, no workspace)
INSERT INTO user_roles (id, user_id, role_id, workspace_id, is_primary, assigned_at)
SELECT
    gen_random_uuid(),
    '00000000-0000-0000-0000-000000000014'::uuid,
    r.id,
    NULL,  -- Global role
    true,
    NOW()
FROM roles r
WHERE r.name = 'super_admin'
ON CONFLICT DO NOTHING;

-- GLOBAL role assignments (workspace_id = NULL) for middleware permission checks
-- These give users their permissions in the JWT token for middleware to check

-- workspace_owner GLOBAL role (for middleware-level permission checks)
INSERT INTO user_roles (id, user_id, role_id, workspace_id, is_primary, assigned_at)
SELECT
    gen_random_uuid(),
    '00000000-0000-0000-0000-000000000010'::uuid,
    r.id,
    NULL,  -- Global role (included in JWT)
    true,  -- Primary global role
    NOW()
FROM roles r
WHERE r.name = 'workspace_owner'
ON CONFLICT DO NOTHING;

-- workspace_admin GLOBAL role
INSERT INTO user_roles (id, user_id, role_id, workspace_id, is_primary, assigned_at)
SELECT
    gen_random_uuid(),
    '00000000-0000-0000-0000-000000000011'::uuid,
    r.id,
    NULL,  -- Global role (included in JWT)
    true,  -- Primary global role
    NOW()
FROM roles r
WHERE r.name = 'workspace_admin'
ON CONFLICT DO NOTHING;

-- editor GLOBAL role
INSERT INTO user_roles (id, user_id, role_id, workspace_id, is_primary, assigned_at)
SELECT
    gen_random_uuid(),
    '00000000-0000-0000-0000-000000000012'::uuid,
    r.id,
    NULL,  -- Global role (included in JWT)
    true,  -- Primary global role
    NOW()
FROM roles r
WHERE r.name = 'editor'
ON CONFLICT DO NOTHING;

-- viewer GLOBAL role
INSERT INTO user_roles (id, user_id, role_id, workspace_id, is_primary, assigned_at)
SELECT
    gen_random_uuid(),
    '00000000-0000-0000-0000-000000000013'::uuid,
    r.id,
    NULL,  -- Global role (included in JWT)
    true,  -- Primary global role
    NOW()
FROM roles r
WHERE r.name = 'viewer'
ON CONFLICT DO NOTHING;

-- Step 4: Create workspace memberships for workspace roles
-- Owner membership
INSERT INTO workspace_members (id, workspace_id, user_id, status, is_default, joined_at)
VALUES (
    gen_random_uuid(),
    '00000000-0000-0000-0000-000000000001'::uuid,
    '00000000-0000-0000-0000-000000000010'::uuid,
    'active',
    true,
    NOW()
)
ON CONFLICT DO NOTHING;

-- Admin membership
INSERT INTO workspace_members (id, workspace_id, user_id, status, is_default, joined_at)
VALUES (
    gen_random_uuid(),
    '00000000-0000-0000-0000-000000000001'::uuid,
    '00000000-0000-0000-0000-000000000011'::uuid,
    'active',
    true,
    NOW()
)
ON CONFLICT DO NOTHING;

-- Editor membership
INSERT INTO workspace_members (id, workspace_id, user_id, status, is_default, joined_at)
VALUES (
    gen_random_uuid(),
    '00000000-0000-0000-0000-000000000001'::uuid,
    '00000000-0000-0000-0000-000000000012'::uuid,
    'active',
    true,
    NOW()
)
ON CONFLICT DO NOTHING;

-- Viewer membership
INSERT INTO workspace_members (id, workspace_id, user_id, status, is_default, joined_at)
VALUES (
    gen_random_uuid(),
    '00000000-0000-0000-0000-000000000001'::uuid,
    '00000000-0000-0000-0000-000000000013'::uuid,
    'active',
    true,
    NOW()
)
ON CONFLICT DO NOTHING;

COMMIT;

-- Verification: Show test users and their roles
SELECT
    u.email,
    u.display_name,
    r.name as role_name,
    CASE WHEN ur.workspace_id IS NULL THEN 'global' ELSE 'workspace:test-workspace' END as scope
FROM users u
JOIN user_roles ur ON ur.user_id = u.id
JOIN roles r ON r.id = ur.role_id
WHERE u.email LIKE '%@test.com'
ORDER BY u.email;

-- Summary
DO $$
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '========================================';
    RAISE NOTICE '✅ Test Users Created Successfully!';
    RAISE NOTICE '========================================';
    RAISE NOTICE '';
    RAISE NOTICE 'Test Workspace: test-workspace';
    RAISE NOTICE '';
    RAISE NOTICE 'Test Users:';
    RAISE NOTICE '  Email: owner@test.com      | Role: workspace_owner';
    RAISE NOTICE '  Email: admin@test.com      | Role: workspace_admin';
    RAISE NOTICE '  Email: editor@test.com     | Role: editor';
    RAISE NOTICE '  Email: viewer@test.com     | Role: viewer';
    RAISE NOTICE '  Email: superadmin@test.com | Role: super_admin';
    RAISE NOTICE '';
    RAISE NOTICE 'Password (all users): TestPassword123!';
    RAISE NOTICE '';
    RAISE NOTICE 'Ready for RBAC testing!';
    RAISE NOTICE '  1. cd rext-admin';
    RAISE NOTICE '  2. npm run test:rbac';
    RAISE NOTICE '  3. npm run test:rbac:e2e';
    RAISE NOTICE '';
END $$;
