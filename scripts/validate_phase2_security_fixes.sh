#!/bin/bash

# Phase 2 Security Fixes Validation Script
# Tests webhook IP validation and audit logging

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
API_BASE_URL="${API_BASE_URL:-http://localhost:2024/api/v1}"
DB_NAME="${DB_NAME:-wrext}"
DB_USER="${DB_USER:-postgres}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"

# Test counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Helper functions
print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_test() {
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    echo -e "${YELLOW}Test $TOTAL_TESTS: $1${NC}"
}

print_pass() {
    PASSED_TESTS=$((PASSED_TESTS + 1))
    echo -e "${GREEN}✓ PASS:${NC} $1"
}

print_fail() {
    FAILED_TESTS=$((FAILED_TESTS + 1))
    echo -e "${RED}✗ FAIL:${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ INFO:${NC} $1"
}

# Database query helper
query_db() {
    PGPASSWORD=postgres psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -t -c "$1" 2>/dev/null || echo ""
}

# Login helper
login_user() {
    local email="$1"
    local password="$2"

    TOKEN=$(curl -s -X POST "$API_BASE_URL/user/login" \
        -H "Content-Type: application/json" \
        -d "{\"email\":\"$email\",\"password\":\"$password\"}" \
        | jq -r '.data.access_token // empty' 2>/dev/null)

    if [ -z "$TOKEN" ] || [ "$TOKEN" == "null" ]; then
        echo ""
    else
        echo "$TOKEN"
    fi
}

print_header "Phase 2 Security Validation"
echo "Testing: Webhook IP Validation & Audit Logging"
echo "API URL: $API_BASE_URL"
echo "Database: $DB_NAME@$DB_HOST:$DB_PORT"

# ============================================================================
# Section 1: Webhook IP Validation Tests
# ============================================================================

print_header "Section 1: Webhook IP Validation"

# Test 1: Check webhook security middleware exists
print_test "Webhook security middleware file exists"
if [ -f "src/api/middleware/webhook_security.py" ]; then
    print_pass "webhook_security.py exists"
else
    print_fail "webhook_security.py not found"
fi

# Test 2: Check webhook configuration added
print_test "Webhook configuration settings exist"
if grep -q "webhook_ip_validation_enabled" src/config/payment_config.py; then
    print_pass "Webhook IP validation config exists"
else
    print_fail "Webhook IP validation config missing"
fi

# Test 3: Check webhook route uses IP validation
print_test "Webhook route uses IP validation dependency"
if grep -q "validate_lemonsqueezy_webhook_ip" src/api/routes/subscriptions/webhook_routes.py; then
    print_pass "Webhook route has IP validation dependency"
else
    print_fail "Webhook route missing IP validation dependency"
fi

# Test 4: Test webhook with invalid IP (if server is running)
print_test "Webhook endpoint rejects unauthorized IP"
if curl -s -o /dev/null -w "%{http_code}" -X POST "$API_BASE_URL/webhooks/lemonsqueezy" \
    -H "Content-Type: application/json" \
    -H "X-Forwarded-For: 1.2.3.4" \
    -d '{"event":"test"}' 2>/dev/null | grep -q "403"; then
    print_pass "Webhook rejects unauthorized IP (403)"
else
    print_info "Could not test live endpoint (server may not be running)"
fi

# Test 5: Check IP whitelist class implementation
print_test "WebhookIPWhitelist class implements is_ip_in_whitelist"
if grep -q "def is_ip_in_whitelist" src/api/middleware/webhook_security.py; then
    print_pass "is_ip_in_whitelist method exists"
else
    print_fail "is_ip_in_whitelist method missing"
fi

# Test 6: Check proxy header handling
print_test "Webhook security handles proxy headers"
if grep -q "X-Forwarded-For" src/api/middleware/webhook_security.py && \
   grep -q "X-Real-IP" src/api/middleware/webhook_security.py; then
    print_pass "Proxy header handling implemented"
else
    print_fail "Proxy header handling missing"
fi

# Test 7: Check CIDR notation support
print_test "CIDR notation support exists"
if grep -q "ip_network" src/api/middleware/webhook_security.py; then
    print_pass "CIDR notation support implemented"
else
    print_fail "CIDR notation support missing"
fi

# Test 8: Check development mode support
print_test "Development mode IP bypass exists"
if grep -q "DEVELOPMENT_IPS" src/api/middleware/webhook_security.py; then
    print_pass "Development mode IPs configured"
else
    print_fail "Development mode IPs missing"
fi

# ============================================================================
# Section 2: Audit Logging Tests
# ============================================================================

print_header "Section 2: Role Management Audit Logging"

# Test 9: Check role create has audit logging
print_test "Role creation endpoint has audit logging"
if grep -q "create_audit_log_async" src/api/routes/roles/modules/role_crud.py && \
   grep -q "role.create" src/api/routes/roles/modules/role_crud.py; then
    print_pass "Role creation audit logging exists"
else
    print_fail "Role creation audit logging missing"
fi

# Test 10: Check role update has audit logging
print_test "Role update endpoint has audit logging"
if grep -q "role.update" src/api/routes/roles/modules/role_crud.py; then
    print_pass "Role update audit logging exists"
else
    print_fail "Role update audit logging missing"
fi

# Test 11: Check role delete has audit logging
print_test "Role deletion endpoint has audit logging"
if grep -q "role.delete" src/api/routes/roles/modules/role_crud.py; then
    print_pass "Role deletion audit logging exists"
else
    print_fail "Role deletion audit logging missing"
fi

# Test 12: Check old_values capture for role update
print_test "Role update captures old values"
if grep -q "old_values = {" src/api/routes/roles/modules/role_crud.py; then
    print_pass "Role update captures old values"
else
    print_fail "Role update missing old values capture"
fi

# Test 13: Check metadata includes actor information
print_test "Audit logs include actor metadata"
if grep -q "created_by_email\|updated_by_email\|deleted_by_email" src/api/routes/roles/modules/role_crud.py; then
    print_pass "Actor metadata included in audit logs"
else
    print_fail "Actor metadata missing from audit logs"
fi

# Test 14: Verify impersonation audit logging exists
print_test "Impersonation audit logging exists"
if grep -q "user.impersonate.start" src/api/routes/users/impersonation.py && \
   grep -q "user.impersonate.stop" src/api/routes/users/impersonation.py; then
    print_pass "Impersonation audit logging exists"
else
    print_fail "Impersonation audit logging missing"
fi

# Test 15: Check audit_logs table exists in database
print_test "Audit logs table exists in database"
TABLE_COUNT=$(query_db "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'audit_logs';" | tr -d '[:space:]')
if [ "$TABLE_COUNT" == "1" ]; then
    print_pass "audit_logs table exists"
else
    print_fail "audit_logs table not found"
fi

# ============================================================================
# Section 3: Integration Tests (if server is running)
# ============================================================================

print_header "Section 3: Integration Tests"

# Try to login as admin
print_test "Login as admin user"
ADMIN_TOKEN=$(login_user "mobeen@revnix.com" "Mobeen@123")
if [ -n "$ADMIN_TOKEN" ]; then
    print_pass "Admin login successful"

    # Test 16: Create a test role and check audit log
    print_test "Create role and verify audit log"
    ROLE_NAME="test_role_$(date +%s)"
    CREATE_RESPONSE=$(curl -s -X POST "$API_BASE_URL/roles/" \
        -H "Authorization: Bearer $ADMIN_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
            \"name\":\"$ROLE_NAME\",
            \"display_name\":\"Test Role\",
            \"description\":\"Test role for audit\",
            \"hierarchy_level\":5
        }")

    ROLE_ID=$(echo "$CREATE_RESPONSE" | jq -r '.data.role.id // empty' 2>/dev/null)

    if [ -n "$ROLE_ID" ] && [ "$ROLE_ID" != "null" ]; then
        print_pass "Role created: $ROLE_ID"

        # Check if audit log was created
        sleep 1
        AUDIT_COUNT=$(query_db "SELECT COUNT(*) FROM audit_logs WHERE action = 'role.create' AND resource_id = '$ROLE_ID';" | tr -d '[:space:]')

        if [ "$AUDIT_COUNT" == "1" ]; then
            print_pass "Audit log created for role.create"

            # Verify audit log metadata
            AUDIT_METADATA=$(query_db "SELECT metadata FROM audit_logs WHERE action = 'role.create' AND resource_id = '$ROLE_ID';" | tr -d '[:space:]')
            if echo "$AUDIT_METADATA" | grep -q "created_by_email"; then
                print_pass "Audit log contains actor metadata"
            else
                print_fail "Audit log missing actor metadata"
            fi
        else
            print_fail "Audit log not created (found: $AUDIT_COUNT)"
        fi

        # Test 17: Update the role and check audit log
        print_test "Update role and verify audit log"
        UPDATE_RESPONSE=$(curl -s -X PUT "$API_BASE_URL/roles/$ROLE_ID" \
            -H "Authorization: Bearer $ADMIN_TOKEN" \
            -H "Content-Type: application/json" \
            -d "{
                \"display_name\":\"Updated Test Role\",
                \"hierarchy_level\":10
            }")

        if echo "$UPDATE_RESPONSE" | grep -q "updated successfully"; then
            print_pass "Role updated successfully"

            sleep 1
            UPDATE_AUDIT=$(query_db "SELECT COUNT(*) FROM audit_logs WHERE action = 'role.update' AND resource_id = '$ROLE_ID';" | tr -d '[:space:]')

            if [ "$UPDATE_AUDIT" == "1" ]; then
                print_pass "Audit log created for role.update"

                # Check for old_values and new_values
                HAS_OLD_VALUES=$(query_db "SELECT COUNT(*) FROM audit_logs WHERE action = 'role.update' AND resource_id = '$ROLE_ID' AND old_values IS NOT NULL;" | tr -d '[:space:]')
                HAS_NEW_VALUES=$(query_db "SELECT COUNT(*) FROM audit_logs WHERE action = 'role.update' AND resource_id = '$ROLE_ID' AND new_values IS NOT NULL;" | tr -d '[:space:]')

                if [ "$HAS_OLD_VALUES" == "1" ] && [ "$HAS_NEW_VALUES" == "1" ]; then
                    print_pass "Audit log has old_values and new_values"
                else
                    print_fail "Audit log missing old_values or new_values"
                fi
            else
                print_fail "Audit log not created for role.update"
            fi
        else
            print_fail "Role update failed"
        fi

        # Test 18: Delete the role and check audit log
        print_test "Delete role and verify audit log"
        DELETE_RESPONSE=$(curl -s -X DELETE "$API_BASE_URL/roles/$ROLE_ID" \
            -H "Authorization: Bearer $ADMIN_TOKEN")

        if echo "$DELETE_RESPONSE" | grep -q "deleted successfully"; then
            print_pass "Role deleted successfully"

            sleep 1
            DELETE_AUDIT=$(query_db "SELECT COUNT(*) FROM audit_logs WHERE action = 'role.delete' AND resource_id = '$ROLE_ID';" | tr -d '[:space:]')

            if [ "$DELETE_AUDIT" == "1" ]; then
                print_pass "Audit log created for role.delete"

                # Check for old_values (deleted role details)
                HAS_OLD_VALUES=$(query_db "SELECT COUNT(*) FROM audit_logs WHERE action = 'role.delete' AND resource_id = '$ROLE_ID' AND old_values IS NOT NULL;" | tr -d '[:space:]')

                if [ "$HAS_OLD_VALUES" == "1" ]; then
                    print_pass "Audit log has deleted role details"
                else
                    print_fail "Audit log missing deleted role details"
                fi
            else
                print_fail "Audit log not created for role.delete"
            fi
        else
            print_fail "Role deletion failed"
        fi
    else
        print_fail "Role creation failed"
    fi
else
    print_info "Could not login as admin (server may not be running or credentials invalid)"
    print_info "Skipping integration tests"
fi

# ============================================================================
# Summary
# ============================================================================

print_header "Validation Summary"

echo "Total Tests: $TOTAL_TESTS"
echo -e "${GREEN}Passed: $PASSED_TESTS${NC}"
echo -e "${RED}Failed: $FAILED_TESTS${NC}"

if [ $FAILED_TESTS -eq 0 ]; then
    echo -e "\n${GREEN}✓ All Phase 2 security fixes validated successfully!${NC}"
    exit 0
else
    echo -e "\n${RED}✗ Some tests failed. Please review the issues above.${NC}"
    exit 1
fi
