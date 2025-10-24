#!/bin/bash
#
# Security Fixes Phase 1 Validation Script
#
# This script validates that all Phase 1 critical security fixes are working correctly:
# - CRITICAL-1: Payment health endpoints require admin
# - CRITICAL-2: Admin customer routes require admin
# - CRITICAL-3: Permission listing requires permission.read
# - HIGH-1: Role listing requires role.read
#
# Usage: ./scripts/validate_phase1_security_fixes.sh
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Base URL
BASE_URL="${BASE_URL:-http://localhost:2024/api/v1}"

# Test results
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

# Function to print section headers
print_section() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

# Function to print test results
print_test() {
    local test_name="$1"
    local expected="$2"
    local actual="$3"

    TESTS_TOTAL=$((TESTS_TOTAL + 1))

    if [ "$expected" = "$actual" ]; then
        echo -e "${GREEN}✓${NC} $test_name"
        echo -e "  Expected: $expected, Got: $actual"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        echo -e "${RED}✗${NC} $test_name"
        echo -e "  Expected: $expected, Got: ${RED}$actual${NC}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
}

# Function to make HTTP request and get status code
get_status_code() {
    local url="$1"
    local auth_header="$2"

    if [ -n "$auth_header" ]; then
        curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $auth_header" "$url"
    else
        curl -s -o /dev/null -w "%{http_code}" "$url"
    fi
}

# Function to login and get token
login_user() {
    local email="$1"
    local password="$2"

    local response=$(curl -s -X POST "$BASE_URL/user/login" \
        -H "Content-Type: application/json" \
        -d "{\"email\":\"$email\",\"password\":\"$password\"}")

    echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null || echo ""
}

# ============================================================================
# START VALIDATION
# ============================================================================

print_section "Security Fixes Phase 1 - Validation Script"

echo "Target: $BASE_URL"
echo "Date: $(date)"
echo ""

# ============================================================================
# SETUP: Login with different user roles
# ============================================================================

print_section "SETUP: Authenticating Test Users"

echo "Attempting to login test users..."
echo ""

# Try to login super_admin
echo -n "Super Admin: "
SUPER_ADMIN_TOKEN=$(login_user "superadmin@test.com" "Test@123")
if [ -n "$SUPER_ADMIN_TOKEN" ]; then
    echo -e "${GREEN}✓ Logged in${NC}"
else
    echo -e "${YELLOW}⚠ Not available (create test account)${NC}"
fi

# Try to login admin
echo -n "Admin: "
ADMIN_TOKEN=$(login_user "admin@test.com" "Test@123")
if [ -n "$ADMIN_TOKEN" ]; then
    echo -e "${GREEN}✓ Logged in${NC}"
else
    echo -e "${YELLOW}⚠ Not available (create test account)${NC}"
fi

# Try to login regular user
echo -n "Regular User: "
USER_TOKEN=$(login_user "user@test.com" "Test@123")
if [ -n "$USER_TOKEN" ]; then
    echo -e "${GREEN}✓ Logged in${NC}"
else
    echo -e "${YELLOW}⚠ Not available (create test account)${NC}"
fi

# Try to login editor
echo -n "Editor: "
EDITOR_TOKEN=$(login_user "editor@test.com" "Test@123")
if [ -n "$EDITOR_TOKEN" ]; then
    echo -e "${GREEN}✓ Logged in${NC}"
else
    echo -e "${YELLOW}⚠ Not available (create test account)${NC}"
fi

echo ""

# Check if we have required tokens
if [ -z "$ADMIN_TOKEN" ] && [ -z "$SUPER_ADMIN_TOKEN" ]; then
    echo -e "${RED}ERROR: No admin tokens available. Please create test accounts.${NC}"
    echo ""
    echo "To create test accounts, use the SQL in the SECURITY-GAPS-FIX-PLAN.md"
    exit 1
fi

if [ -z "$USER_TOKEN" ]; then
    echo -e "${YELLOW}WARNING: No regular user token. Some tests will be skipped.${NC}"
fi

# ============================================================================
# CRITICAL-1: Payment Health Endpoints
# ============================================================================

print_section "CRITICAL-1: Payment Health Endpoints Protection"

# Test 1.1: Unauthenticated access should fail
status=$(get_status_code "$BASE_URL/health/payment")
print_test "Payment health - Unauthenticated" "401" "$status"

# Test 1.2: Regular user should be denied
if [ -n "$USER_TOKEN" ]; then
    status=$(get_status_code "$BASE_URL/health/payment" "$USER_TOKEN")
    print_test "Payment health - Regular User" "403" "$status"
else
    echo -e "${YELLOW}⚠${NC} Payment health - Regular User (skipped - no user token)"
fi

# Test 1.3: Admin should be allowed
if [ -n "$ADMIN_TOKEN" ]; then
    status=$(get_status_code "$BASE_URL/health/payment" "$ADMIN_TOKEN")
    print_test "Payment health - Admin" "200" "$status"
else
    echo -e "${YELLOW}⚠${NC} Payment health - Admin (skipped - no admin token)"
fi

# Test 1.4: Super Admin should be allowed
if [ -n "$SUPER_ADMIN_TOKEN" ]; then
    status=$(get_status_code "$BASE_URL/health/payment" "$SUPER_ADMIN_TOKEN")
    print_test "Payment health - Super Admin" "200" "$status"
else
    echo -e "${YELLOW}⚠${NC} Payment health - Super Admin (skipped - no super admin token)"
fi

# Test 1.5: Quick payment health - Unauthenticated
status=$(get_status_code "$BASE_URL/health/payment/quick")
print_test "Payment quick health - Unauthenticated" "401" "$status"

# Test 1.6: Quick payment health - Regular user
if [ -n "$USER_TOKEN" ]; then
    status=$(get_status_code "$BASE_URL/health/payment/quick" "$USER_TOKEN")
    print_test "Payment quick health - Regular User" "403" "$status"
else
    echo -e "${YELLOW}⚠${NC} Payment quick health - Regular User (skipped)"
fi

# Test 1.7: Quick payment health - Admin
if [ -n "$ADMIN_TOKEN" ]; then
    status=$(get_status_code "$BASE_URL/health/payment/quick" "$ADMIN_TOKEN")
    print_test "Payment quick health - Admin" "200" "$status"
else
    echo -e "${YELLOW}⚠${NC} Payment quick health - Admin (skipped)"
fi

# ============================================================================
# CRITICAL-2: Admin Customer Routes Protection
# ============================================================================

print_section "CRITICAL-2: Admin Customer Routes Protection"

# Test 2.1: List customers - Unauthenticated
status=$(get_status_code "$BASE_URL/customers")
print_test "List customers - Unauthenticated" "401" "$status"

# Test 2.2: List customers - Regular user
if [ -n "$USER_TOKEN" ]; then
    status=$(get_status_code "$BASE_URL/customers" "$USER_TOKEN")
    print_test "List customers - Regular User" "403" "$status"
else
    echo -e "${YELLOW}⚠${NC} List customers - Regular User (skipped)"
fi

# Test 2.3: List customers - Editor
if [ -n "$EDITOR_TOKEN" ]; then
    status=$(get_status_code "$BASE_URL/customers" "$EDITOR_TOKEN")
    print_test "List customers - Editor" "403" "$status"
else
    echo -e "${YELLOW}⚠${NC} List customers - Editor (skipped)"
fi

# Test 2.4: List customers - Admin
if [ -n "$ADMIN_TOKEN" ]; then
    status=$(get_status_code "$BASE_URL/customers" "$ADMIN_TOKEN")
    print_test "List customers - Admin" "200" "$status"
else
    echo -e "${YELLOW}⚠${NC} List customers - Admin (skipped)"
fi

# Test 2.5: List customers - Super Admin
if [ -n "$SUPER_ADMIN_TOKEN" ]; then
    status=$(get_status_code "$BASE_URL/customers" "$SUPER_ADMIN_TOKEN")
    print_test "List customers - Super Admin" "200" "$status"
else
    echo -e "${YELLOW}⚠${NC} List customers - Super Admin (skipped)"
fi

# Test customer detail endpoint (if we have a user ID)
# Note: Using a fake UUID for testing - will return 404 but should check auth first
TEST_USER_ID="00000000-0000-0000-0000-000000000000"

# Test 2.6: Customer detail - Regular user
if [ -n "$USER_TOKEN" ]; then
    status=$(get_status_code "$BASE_URL/customers/$TEST_USER_ID" "$USER_TOKEN")
    # Should be 403 (permission denied) not 404 (not found)
    if [ "$status" = "403" ]; then
        print_test "Customer detail - Regular User" "403" "$status"
    elif [ "$status" = "404" ]; then
        # 404 means auth passed but resource not found - this is wrong!
        print_test "Customer detail - Regular User" "403" "404 (AUTH BYPASSED!)"
    else
        print_test "Customer detail - Regular User" "403" "$status"
    fi
else
    echo -e "${YELLOW}⚠${NC} Customer detail - Regular User (skipped)"
fi

# ============================================================================
# CRITICAL-3: Permission Listing Protection
# ============================================================================

print_section "CRITICAL-3: Permission Listing Protection"

# Test 3.1: List permissions - Unauthenticated
status=$(get_status_code "$BASE_URL/permissions/")
print_test "List permissions - Unauthenticated" "401" "$status"

# Test 3.2: List permissions - Regular user
if [ -n "$USER_TOKEN" ]; then
    status=$(get_status_code "$BASE_URL/permissions/" "$USER_TOKEN")
    print_test "List permissions - Regular User" "403" "$status"
else
    echo -e "${YELLOW}⚠${NC} List permissions - Regular User (skipped)"
fi

# Test 3.3: List permissions - Editor
if [ -n "$EDITOR_TOKEN" ]; then
    status=$(get_status_code "$BASE_URL/permissions/" "$EDITOR_TOKEN")
    print_test "List permissions - Editor" "403" "$status"
else
    echo -e "${YELLOW}⚠${NC} List permissions - Editor (skipped)"
fi

# Test 3.4: List permissions - Admin
if [ -n "$ADMIN_TOKEN" ]; then
    status=$(get_status_code "$BASE_URL/permissions/" "$ADMIN_TOKEN")
    print_test "List permissions - Admin" "200" "$status"
else
    echo -e "${YELLOW}⚠${NC} List permissions - Admin (skipped)"
fi

# Test 3.5: List permissions - Super Admin
if [ -n "$SUPER_ADMIN_TOKEN" ]; then
    status=$(get_status_code "$BASE_URL/permissions/" "$SUPER_ADMIN_TOKEN")
    print_test "List permissions - Super Admin" "200" "$status"
else
    echo -e "${YELLOW}⚠${NC} List permissions - Super Admin (skipped)"
fi

# ============================================================================
# HIGH-1: Role Listing Protection
# ============================================================================

print_section "HIGH-1: Role Listing Protection"

# Test 4.1: List roles - Unauthenticated
status=$(get_status_code "$BASE_URL/roles/")
print_test "List roles - Unauthenticated" "401" "$status"

# Test 4.2: List roles - Regular user
if [ -n "$USER_TOKEN" ]; then
    status=$(get_status_code "$BASE_URL/roles/" "$USER_TOKEN")
    print_test "List roles - Regular User" "403" "$status"
else
    echo -e "${YELLOW}⚠${NC} List roles - Regular User (skipped)"
fi

# Test 4.3: List roles - Editor
if [ -n "$EDITOR_TOKEN" ]; then
    status=$(get_status_code "$BASE_URL/roles/" "$EDITOR_TOKEN")
    print_test "List roles - Editor" "403" "$status"
else
    echo -e "${YELLOW}⚠${NC} List roles - Editor (skipped)"
fi

# Test 4.4: List roles - Admin
if [ -n "$ADMIN_TOKEN" ]; then
    status=$(get_status_code "$BASE_URL/roles/" "$ADMIN_TOKEN")
    print_test "List roles - Admin" "200" "$status"
else
    echo -e "${YELLOW}⚠${NC} List roles - Admin (skipped)"
fi

# Test 4.5: List roles - Super Admin
if [ -n "$SUPER_ADMIN_TOKEN" ]; then
    status=$(get_status_code "$BASE_URL/roles/" "$SUPER_ADMIN_TOKEN")
    print_test "List roles - Super Admin" "200" "$status"
else
    echo -e "${YELLOW}⚠${NC} List roles - Super Admin (skipped)"
fi

# ============================================================================
# SUMMARY
# ============================================================================

print_section "Test Summary"

echo "Tests Passed:  ${GREEN}$TESTS_PASSED${NC}"
echo "Tests Failed:  ${RED}$TESTS_FAILED${NC}"
echo "Tests Total:   $TESTS_TOTAL"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    echo ""
    echo "Phase 1 security fixes are working correctly."
    exit 0
else
    echo -e "${RED}✗ Some tests failed!${NC}"
    echo ""
    echo "Please review the failed tests above and fix the issues."
    exit 1
fi
