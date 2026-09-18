#!/usr/bin/env python3
"""
Email Notification Testing Script - Fixed Version

Tests all billing-related email templates with correct parameters.

Usage:
    python scripts/test_email_notifications_fixed.py
"""

import sys
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ANSI color codes
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"


class EmailTestRunner:
    """Test runner for email notifications"""

    def __init__(self):
        self.results = []

    def log(self, message: str, level: str = "INFO"):
        """Log a message with timestamp and color"""
        timestamp = datetime.now().strftime("%H:%M:%S")

        if level == "SUCCESS":
            color, symbol = Colors.GREEN, "✓"
        elif level == "ERROR":
            color, symbol = Colors.RED, "✗"
        elif level == "WARNING":
            color, symbol = Colors.YELLOW, "⚠"
        else:
            color, symbol = Colors.BLUE, "ℹ"

        print(f"{color}[{timestamp}] {symbol} {message}{Colors.END}")

    async def test_template(self, name: str, render_func, **kwargs) -> bool:
        """Test that an email template renders without errors"""
        self.log(f"Testing: {name}", "INFO")

        try:
            html_content = billing.render_func(**kwargs)

            if not html_content or len(html_content) < 100:
                raise ValueError(f"Content too short: {len(html_content)} chars")

            self.log(f"{name}: OK ({len(html_content)} chars)", "SUCCESS")
            self.results.append({"template": name, "status": "PASS", "length": len(html_content)})
            return True

        except Exception as e:
            self.log(f"{name}: FAILED - {str(e)}", "ERROR")
            self.results.append({"template": name, "status": "FAIL", "error": str(e)})
            return False

    async def run_all_tests(self):
        """Run all email template tests"""
        self.log(f"\n{Colors.BOLD}{'=' * 60}{Colors.END}", "INFO")
        self.log(f"{Colors.BOLD}EMAIL TEMPLATE VALIDATION{Colors.END}", "INFO")
        self.log(f"{Colors.BOLD}{'=' * 60}{Colors.END}\n", "INFO")

        from emails.templates import billing

        # Test 1: Subscription Created
        await self.test_template(
            "subscription_created",
            billing.render_subscription_created_email,
            user_name="Test User",
            plan_name="Pro Plan",
            plan_price="$29.99",
            billing_period="monthly",
            features=["Feature 1", "Feature 2"],
            customer_portal_url="https://example.com/portal",
        )

        # Test 2: Payment Succeeded
        await self.test_template(
            "payment_succeeded",
            billing.render_payment_succeeded_email,
            user_name="Test User",
            plan_name="Pro Plan",
            amount="$29.99",  # Not amount_paid!
            payment_date="Dec 21, 2025",
            next_billing_date="Jan 21, 2026",
            invoice_url="https://example.com/invoice",
            card_brand="Visa",
            card_last_four="4242",
        )

        # Test 3: Payment Failed
        await self.test_template(
            "payment_failed",
            billing.render_payment_failed_email,
            user_name="Test User",
            plan_name="Pro Plan",
            amount="$29.99",
            retry_date="Dec 24, 2025",
            update_payment_url="https://example.com/billing",
        )

        # Test 4: Subscription Cancelled
        await self.test_template(
            "subscription_cancelled",
            billing.render_subscription_cancelled_email,
            user_name="Test User",
            plan_name="Pro Plan",
            end_date="Jan 21, 2026",
            reactivate_url="https://example.com/pricing",
            feedback_url="https://example.com/feedback",
        )

        # Test 5: Subscription Upgraded
        await self.test_template(
            "subscription_upgraded",
            billing.render_subscription_upgraded_email,
            user_name="Test User",
            old_plan_name="Basic Plan",
            new_plan_name="Pro Plan",
            new_plan_price="$29.99",
            effective_date="Dec 21, 2025",
            proration_amount="$15.00",
        )

        # Test 6: Subscription Downgraded
        await self.test_template(
            "subscription_downgraded",
            billing.render_subscription_downgraded_email,
            user_name="Test User",
            old_plan_name="Pro Plan",
            new_plan_name="Basic Plan",
            new_plan_price="$9.99",
            effective_date="Jan 21, 2026",
            credit_amount="$20.00",
        )

        # Test 7: Refund Issued
        await self.test_template(
            "refund_issued",
            billing.render_refund_issued_email,
            user_name="Test User",
            refund_amount="$29.99",
            refund_date="Dec 21, 2025",
            order_id="ORD-123456",
        )

        # Test 8-11: Trial Reminders
        trial_date = (datetime.now() + timedelta(days=3)).strftime("%B %d, %Y")

        await self.test_template(
            "trial_reminder_3_days",
            billing.render_trial_reminder_3_days_email,
            user_name="Test User",
            plan_name="Pro Plan",
            trial_end_date=trial_date,
        )

        await self.test_template(
            "trial_reminder_1_day",
            billing.render_trial_reminder_1_day_email,
            user_name="Test User",
            plan_name="Pro Plan",
            trial_end_date=trial_date,
        )

        await self.test_template(
            "trial_reminder_expiring_today",
            billing.render_trial_reminder_expiring_today_email,
            user_name="Test User",
            plan_name="Pro Plan",
        )

        await self.test_template(
            "trial_expired",
            billing.render_trial_expired_email,
            user_name="Test User",
            plan_name="Pro Plan",
        )

        # Test 12-14: Payment Dunning
        await self.test_template(
            "payment_dunning_1_day",
            billing.render_payment_dunning_1_day_email,
            user_name="Test User",
            plan_name="Pro Plan",
            amount="$29.99",
            grace_period_end_date="Dec 28, 2025",
            update_payment_url="https://example.com/portal",
        )

        await self.test_template(
            "payment_dunning_3_days",
            billing.render_payment_dunning_3_days_email,
            user_name="Test User",
            plan_name="Pro Plan",
            amount="$29.99",
            grace_period_end_date="Dec 24, 2025",
            update_payment_url="https://example.com/portal",
        )

        await self.test_template(
            "payment_dunning_6_days",
            billing.render_payment_dunning_6_days_email,
            user_name="Test User",
            plan_name="Pro Plan",
            amount="$29.99",
            grace_period_end_date="Dec 22, 2025",
            update_payment_url="https://example.com/portal",
        )

        # Test 15: Subscription Suspended
        await self.test_template(
            "subscription_suspended",
            billing.render_subscription_suspended_email,
            user_name="Test User",
            plan_name="Pro Plan",
            amount="$29.99",
            suspension_date="Dec 21, 2025",
            reactivate_url="https://example.com/pricing",
        )

        # Test 16: Payment Recovered
        await self.test_template(
            "payment_recovered",
            billing.render_payment_recovered_email,
            user_name="Test User",
            plan_name="Pro Plan",
            amount="$29.99",
            next_billing_date="Jan 21, 2026",
        )

        # Print summary
        self.print_summary()

    def print_summary(self):
        """Print test results summary"""
        self.log(f"\n{Colors.BOLD}{'=' * 60}{Colors.END}", "INFO")
        self.log(f"{Colors.BOLD}TEST SUMMARY{Colors.END}", "INFO")
        self.log(f"{Colors.BOLD}{'=' * 60}{Colors.END}\n", "INFO")

        total = len(self.results)
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")

        self.log(f"Total: {total} | Passed: {passed} | Failed: {failed}", "INFO")

        if failed > 0:
            self.log("\nFailed Templates:", "ERROR")
            for r in self.results:
                if r["status"] == "FAIL":
                    self.log(f"  - {r['template']}: {r.get('error', 'Unknown')}", "ERROR")

        pass_rate = (passed / total * 100) if total > 0 else 0
        self.log(f"\nPass Rate: {pass_rate:.1f}%", "SUCCESS" if pass_rate >= 90 else "WARNING")

        # Save results
        output = Path(__file__).parent.parent / "docs/testing/email_test_results.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w") as f:
            json.dump(
                {
                    "timestamp": datetime.now().isoformat(),
                    "total": total,
                    "passed": passed,
                    "failed": failed,
                    "pass_rate": pass_rate,
                    "results": self.results,
                },
                f,
                indent=2,
            )

        self.log(f"\nResults saved: {output}", "INFO")

        if pass_rate == 100:
            self.log("\n🎉 ALL TESTS PASSED!", "SUCCESS")
        elif pass_rate >= 90:
            self.log("\n✓ Most tests passed", "WARNING")
        else:
            self.log("\n✗ Multiple failures", "ERROR")


async def main():
    runner = EmailTestRunner()
    await runner.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
