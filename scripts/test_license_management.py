#!/usr/bin/env python3
"""
License Management Testing Script

Tests all license key operations for LemonSqueezy integration:
- License creation via order purchase
- License validation
- License activation (multiple devices)
- Activation limit enforcement
- License deactivation
- Error handling

Usage:
    python scripts/test_license_management.py

Requirements:
    - Backend server running (http://localhost:2024)
    - LemonSqueezy test product with license key generation
    - Valid test API credentials
"""

import sys
import json
import time
import requests
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configuration
BASE_URL = "http://localhost:2024"
API_BASE = f"{BASE_URL}/api/v1"

# ANSI color codes for output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

class LicenseTestRunner:
    """Test runner for license management operations"""

    def __init__(self):
        self.results = []
        self.auth_token = None
        self.test_user_email = "mobeen@revnix.com"
        self.test_user_password = "Mobeen@123"
        self.license_key = None
        self.license_id = None
        self.activation_ids = []

    def log(self, message: str, level: str = "INFO"):
        """Log a message with timestamp and color"""
        timestamp = datetime.now().strftime("%H:%M:%S")

        if level == "SUCCESS":
            color = Colors.GREEN
            symbol = "✓"
        elif level == "ERROR":
            color = Colors.RED
            symbol = "✗"
        elif level == "WARNING":
            color = Colors.YELLOW
            symbol = "⚠"
        else:
            color = Colors.BLUE
            symbol = "ℹ"

        print(f"{color}[{timestamp}] {symbol} {message}{Colors.END}")

    def login(self) -> bool:
        """Authenticate and get access token"""
        self.log("Authenticating test user...", "INFO")

        try:
            response = requests.post(
                f"{API_BASE}/user/login",
                json={
                    "email": self.test_user_email,
                    "password": self.test_user_password
                },
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                self.auth_token = data.get("access_token")
                self.log(f"Authentication successful for {self.test_user_email}", "SUCCESS")
                return True
            else:
                self.log(f"Authentication failed: {response.status_code} - {response.text}", "ERROR")
                return False

        except Exception as e:
            self.log(f"Authentication error: {str(e)}", "ERROR")
            return False

    def get_headers(self) -> Dict[str, str]:
        """Get authorization headers"""
        return {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json"
        }

    def test_list_user_licenses(self) -> bool:
        """Test 1: List user's licenses"""
        self.log("\n=== Test 1: List User Licenses ===", "INFO")

        try:
            response = requests.get(
                f"{API_BASE}/licenses",
                headers=self.get_headers(),
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                licenses = data.get("licenses", [])
                self.log(f"Found {len(licenses)} license(s)", "SUCCESS")

                if licenses:
                    # Store first license for testing
                    first_license = licenses[0]
                    self.license_key = first_license.get("license_key")
                    self.license_id = first_license.get("id")

                    self.log(f"License Key: {self.license_key}", "INFO")
                    self.log(f"Product: {first_license.get('product_name')}", "INFO")
                    self.log(f"Status: {first_license.get('status')}", "INFO")
                    self.log(f"Activation Limit: {first_license.get('activation_limit')}", "INFO")
                    self.log(f"Activations Used: {first_license.get('activation_usage')}", "INFO")
                else:
                    self.log("No licenses found. Please purchase a test license first.", "WARNING")
                    self.log("You can create a manual license for testing purposes.", "INFO")

                self.results.append({
                    "test": "list_user_licenses",
                    "status": "PASS",
                    "licenses_found": len(licenses)
                })
                return True
            else:
                self.log(f"Failed to list licenses: {response.status_code}", "ERROR")
                self.results.append({
                    "test": "list_user_licenses",
                    "status": "FAIL",
                    "error": response.text
                })
                return False

        except Exception as e:
            self.log(f"Error listing licenses: {str(e)}", "ERROR")
            self.results.append({
                "test": "list_user_licenses",
                "status": "FAIL",
                "error": str(e)
            })
            return False

    def test_validate_license(self) -> bool:
        """Test 2: Validate license key"""
        self.log("\n=== Test 2: Validate License Key ===", "INFO")

        if not self.license_key:
            self.log("No license key available for testing", "WARNING")
            return False

        try:
            # Test with valid instance_id
            instance_id = "test-device-001"

            response = requests.post(
                f"{API_BASE}/licenses/validate",
                json={
                    "license_key": self.license_key,
                    "instance_id": instance_id
                },
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                valid = data.get("valid", False)

                if valid:
                    self.log(f"License key validated successfully", "SUCCESS")
                    self.log(f"License ID: {data.get('license_id')}", "INFO")
                    self.log(f"Product: {data.get('product_name')}", "INFO")
                    self.log(f"Activations: {data.get('activation_usage')}/{data.get('activation_limit')}", "INFO")
                else:
                    self.log(f"License validation failed: {data.get('message')}", "WARNING")

                self.results.append({
                    "test": "validate_license",
                    "status": "PASS" if valid else "FAIL",
                    "valid": valid
                })
                return valid
            else:
                self.log(f"Validation request failed: {response.status_code}", "ERROR")
                self.results.append({
                    "test": "validate_license",
                    "status": "FAIL",
                    "error": response.text
                })
                return False

        except Exception as e:
            self.log(f"Error validating license: {str(e)}", "ERROR")
            self.results.append({
                "test": "validate_license",
                "status": "FAIL",
                "error": str(e)
            })
            return False

    def test_activate_license(self, instance_id: str, instance_name: str) -> bool:
        """Test 3: Activate license on a device"""
        self.log(f"\n=== Test: Activate License on {instance_name} ===", "INFO")

        if not self.license_id:
            self.log("No license ID available for testing", "WARNING")
            return False

        try:
            response = requests.post(
                f"{API_BASE}/licenses/{self.license_id}/activate",
                headers=self.get_headers(),
                json={
                    "instance_id": instance_id,
                    "instance_name": instance_name
                },
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                activation_id = data.get("activation", {}).get("id")

                self.log(f"License activated on {instance_name}", "SUCCESS")
                self.log(f"Activation ID: {activation_id}", "INFO")
                self.log(f"Instance ID: {instance_id}", "INFO")

                self.activation_ids.append(activation_id)

                self.results.append({
                    "test": f"activate_license_{instance_name}",
                    "status": "PASS",
                    "activation_id": activation_id
                })
                return True
            elif response.status_code == 400:
                # Check if limit exceeded
                error_data = response.json()
                if "limit" in error_data.get("detail", "").lower():
                    self.log(f"Activation limit reached (expected): {error_data.get('detail')}", "WARNING")
                    self.results.append({
                        "test": f"activate_license_{instance_name}",
                        "status": "EXPECTED_FAIL",
                        "reason": "Activation limit reached"
                    })
                    return False
                else:
                    self.log(f"Activation failed: {error_data.get('detail')}", "ERROR")
                    self.results.append({
                        "test": f"activate_license_{instance_name}",
                        "status": "FAIL",
                        "error": error_data.get('detail')
                    })
                    return False
            else:
                self.log(f"Activation request failed: {response.status_code}", "ERROR")
                self.results.append({
                    "test": f"activate_license_{instance_name}",
                    "status": "FAIL",
                    "error": response.text
                })
                return False

        except Exception as e:
            self.log(f"Error activating license: {str(e)}", "ERROR")
            self.results.append({
                "test": f"activate_license_{instance_name}",
                "status": "FAIL",
                "error": str(e)
            })
            return False

    def test_list_activations(self) -> bool:
        """Test: List all activations for a license"""
        self.log(f"\n=== Test: List License Activations ===", "INFO")

        if not self.license_id:
            self.log("No license ID available for testing", "WARNING")
            return False

        try:
            response = requests.get(
                f"{API_BASE}/licenses/{self.license_id}/activations",
                headers=self.get_headers(),
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                activations = data.get("activations", [])

                self.log(f"Found {len(activations)} activation(s)", "SUCCESS")

                for idx, activation in enumerate(activations, 1):
                    self.log(f"  {idx}. {activation.get('instance_name')} ({activation.get('instance_id')})", "INFO")
                    self.log(f"     Status: {activation.get('is_active')}, Activated: {activation.get('activated_at')}", "INFO")

                self.results.append({
                    "test": "list_activations",
                    "status": "PASS",
                    "activations_found": len(activations)
                })
                return True
            else:
                self.log(f"Failed to list activations: {response.status_code}", "ERROR")
                self.results.append({
                    "test": "list_activations",
                    "status": "FAIL",
                    "error": response.text
                })
                return False

        except Exception as e:
            self.log(f"Error listing activations: {str(e)}", "ERROR")
            self.results.append({
                "test": "list_activations",
                "status": "FAIL",
                "error": str(e)
            })
            return False

    def test_deactivate_license(self, activation_id: str, instance_name: str) -> bool:
        """Test: Deactivate a license activation"""
        self.log(f"\n=== Test: Deactivate License from {instance_name} ===", "INFO")

        if not self.license_id:
            self.log("No license ID available for testing", "WARNING")
            return False

        try:
            response = requests.post(
                f"{API_BASE}/licenses/{self.license_id}/deactivate",
                headers=self.get_headers(),
                json={
                    "activation_id": activation_id
                },
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()

                self.log(f"License deactivated from {instance_name}", "SUCCESS")
                self.log(f"Message: {data.get('message')}", "INFO")

                self.results.append({
                    "test": f"deactivate_license_{instance_name}",
                    "status": "PASS",
                    "activation_id": activation_id
                })
                return True
            else:
                self.log(f"Deactivation request failed: {response.status_code}", "ERROR")
                self.results.append({
                    "test": f"deactivate_license_{instance_name}",
                    "status": "FAIL",
                    "error": response.text
                })
                return False

        except Exception as e:
            self.log(f"Error deactivating license: {str(e)}", "ERROR")
            self.results.append({
                "test": f"deactivate_license_{instance_name}",
                "status": "FAIL",
                "error": str(e)
            })
            return False

    def test_invalid_license_key(self) -> bool:
        """Test: Validate invalid license key"""
        self.log(f"\n=== Test: Invalid License Key ===", "INFO")

        try:
            response = requests.post(
                f"{API_BASE}/licenses/validate",
                json={
                    "license_key": "INVALID-KEY-12345",
                    "instance_id": "test-device-999"
                },
                timeout=10
            )

            if response.status_code == 404 or response.status_code == 400:
                self.log(f"Invalid license key rejected correctly", "SUCCESS")
                self.results.append({
                    "test": "invalid_license_key",
                    "status": "PASS"
                })
                return True
            else:
                self.log(f"Unexpected response: {response.status_code}", "WARNING")
                self.results.append({
                    "test": "invalid_license_key",
                    "status": "FAIL",
                    "error": "Invalid key not rejected properly"
                })
                return False

        except Exception as e:
            self.log(f"Error testing invalid key: {str(e)}", "ERROR")
            self.results.append({
                "test": "invalid_license_key",
                "status": "FAIL",
                "error": str(e)
            })
            return False

    def run_all_tests(self):
        """Run complete test suite"""
        self.log(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
        self.log(f"{Colors.BOLD}LICENSE MANAGEMENT TEST SUITE{Colors.END}")
        self.log(f"{Colors.BOLD}{'='*60}{Colors.END}\n")

        # Step 1: Login
        if not self.login():
            self.log("Cannot proceed without authentication", "ERROR")
            return

        # Step 2: List licenses
        self.test_list_user_licenses()

        if not self.license_key:
            self.log("\n" + "="*60, "WARNING")
            self.log("NO LICENSE FOUND - MANUAL SETUP REQUIRED", "WARNING")
            self.log("="*60, "WARNING")
            self.log("\nTo complete this test, please:", "INFO")
            self.log("1. Log into LemonSqueezy test dashboard", "INFO")
            self.log("2. Create a product with license key generation enabled", "INFO")
            self.log("3. Purchase the product in test mode", "INFO")
            self.log("4. Verify license appears in the database", "INFO")
            self.log("5. Re-run this script\n", "INFO")
            return

        # Step 3: Validate license
        self.test_validate_license()

        # Step 4: Activate on Device 1
        self.test_activate_license("device-001-mac", "MacBook Pro")

        # Step 5: Activate on Device 2
        self.test_activate_license("device-002-windows", "Windows Desktop")

        # Step 6: Activate on Device 3
        self.test_activate_license("device-003-linux", "Ubuntu Server")

        # Step 7: List all activations
        self.test_list_activations()

        # Step 8: Try to activate on Device 4 (should fail - limit exceeded)
        self.test_activate_license("device-004-tablet", "iPad")

        # Step 9: Deactivate Device 2
        if len(self.activation_ids) >= 2:
            self.test_deactivate_license(self.activation_ids[1], "Windows Desktop")

        # Step 10: Activate on Device 4 again (should succeed now)
        self.test_activate_license("device-004-tablet", "iPad")

        # Step 11: List activations again
        self.test_list_activations()

        # Step 12: Test invalid license key
        self.test_invalid_license_key()

        # Print summary
        self.print_summary()

    def print_summary(self):
        """Print test results summary"""
        self.log(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
        self.log(f"{Colors.BOLD}TEST RESULTS SUMMARY{Colors.END}")
        self.log(f"{Colors.BOLD}{'='*60}{Colors.END}\n")

        total = len(self.results)
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        expected_fail = sum(1 for r in self.results if r["status"] == "EXPECTED_FAIL")

        self.log(f"Total Tests: {total}", "INFO")
        self.log(f"Passed: {passed}", "SUCCESS")
        self.log(f"Failed: {failed}", "ERROR" if failed > 0 else "INFO")
        self.log(f"Expected Failures: {expected_fail}", "WARNING" if expected_fail > 0 else "INFO")

        if failed > 0:
            self.log("\nFailed Tests:", "ERROR")
            for result in self.results:
                if result["status"] == "FAIL":
                    self.log(f"  - {result['test']}: {result.get('error', 'Unknown error')}", "ERROR")

        # Calculate pass rate
        pass_rate = (passed / total * 100) if total > 0 else 0

        self.log(f"\nPass Rate: {pass_rate:.1f}%", "SUCCESS" if pass_rate >= 80 else "WARNING")

        # Save results to JSON
        self.save_results()

        if pass_rate == 100:
            self.log(f"\n🎉 ALL TESTS PASSED! License management working perfectly!", "SUCCESS")
        elif pass_rate >= 80:
            self.log(f"\n✓ Most tests passed. Review failures above.", "WARNING")
        else:
            self.log(f"\n✗ Multiple test failures. Review and fix issues.", "ERROR")

    def save_results(self):
        """Save test results to JSON file"""
        output_file = Path(__file__).parent.parent / "docs/testing/license_test_results.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "total_tests": len(self.results),
                "results": self.results
            }, f, indent=2)

        self.log(f"\nResults saved to: {output_file}", "INFO")

def main():
    """Main entry point"""
    runner = LicenseTestRunner()
    runner.run_all_tests()

if __name__ == "__main__":
    main()
