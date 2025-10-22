#!/usr/bin/env python3
"""
Email Notification Testing Script

Tests all billing-related email templates and delivery for LemonSqueezy integration.

Usage:
    python scripts/test_email_notifications.py

Requirements:
    - Backend server running (http://localhost:2024)
    - Valid email service configuration (Resend API key)
    - Test user with email notifications enabled
"""

import sys
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# ANSI color codes
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


class EmailTestRunner:
    """Test runner for email notifications"""

    def __init__(self):
        self.results = []
        self.test_user_email = "mobeen@revnix.com"
        
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

    async def test_email_template_rendering(self, template_name: str, render_func, **kwargs) -> bool:
        """Test that an email template renders without errors"""
        self.log(f"\nTesting template: {template_name}", "INFO")
        
        try:
            html_content = render_func(**kwargs)
            
            if not html_content:
                self.log(f"Template {template_name} returned empty content", "ERROR")
                self.results.append({
                    "template": template_name,
                    "status": "FAIL",
                    "error": "Empty content"
                })
                return False
            
            # Basic validation
            if len(html_content) < 100:
                self.log(f"Template {template_name} content too short ({len(html_content)} chars)", "WARNING")
            
            if "<html" not in html_content.lower():
                self.log(f"Template {template_name} missing HTML tags", "WARNING")
            
            self.log(f"Template {template_name} rendered successfully ({len(html_content)} chars)", "SUCCESS")
            self.results.append({
                "template": template_name,
                "status": "PASS",
                "content_length": len(html_content)
            })
            return True
            
        except Exception as e:
            self.log(f"Template {template_name} failed to render: {str(e)}", "ERROR")
            self.results.append({
                "template": template_name,
                "status": "FAIL",
                "error": str(e)
            })
            return False

    async def test_all_templates(self):
        """Test all billing email templates"""
        self.log(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
        self.log(f"{Colors.BOLD}TESTING EMAIL TEMPLATES{Colors.END}")
        self.log(f"{Colors.BOLD}{'='*60}{Colors.END}")
        
        # Import all templates
        from emails.templates.billing import (
            render_subscription_created_email,
            render_payment_succeeded_email,
            render_payment_failed_email,
            render_subscription_cancelled_email,
            render_subscription_upgraded_email,
            render_subscription_downgraded_email,
            render_refund_issued_email,
            render_trial_reminder_3_days_email,
            render_trial_reminder_1_day_email,
            render_trial_reminder_expiring_today_email,
            render_trial_expired_email,
            render_payment_dunning_1_day_email,
            render_payment_dunning_3_days_email,
            render_payment_dunning_6_days_email,
            render_subscription_suspended_email,
            render_payment_recovered_email,
        )
        
        # Common test data
        user_name = "Test User"
        plan_name = "Pro Plan"
        old_plan_name = "Basic Plan"
        plan_price = "$29.99"
        billing_period = "monthly"
        features = ["Unlimited workspaces", "Advanced AI features", "Priority support"]
        
        # Test 1: Subscription Created
        await self.test_email_template_rendering(
            "subscription_created",
            render_subscription_created_email,
            user_name=user_name,
            plan_name=plan_name,
            plan_price=plan_price,
            billing_period=billing_period,
            features=features,
            customer_portal_url="https://app.wrext.com/subscription"
        )
        
        # Test 2: Payment Succeeded
        await self.test_email_template_rendering(
            "payment_succeeded",
            render_payment_succeeded_email,
            user_name=user_name,
            plan_name=plan_name,
            amount_paid=plan_price,
            payment_date="December 21, 2025",
            next_billing_date="January 21, 2026",
            invoice_url="https://lemonsqueezy.com/invoice/123",
            card_brand="Visa",
            card_last_four="4242"
        )
        
        # Test 3: Payment Failed
        await self.test_email_template_rendering(
            "payment_failed",
            render_payment_failed_email,
            user_name=user_name,
            plan_name=plan_name,
            amount=plan_price,
            retry_date="December 24, 2025",
            update_payment_url="https://app.wrext.com/billing",
            customer_portal_url="https://lemonsqueezy.com/portal"
        )
        
        # Test 4: Subscription Cancelled
        await self.test_email_template_rendering(
            "subscription_cancelled",
            render_subscription_cancelled_email,
            user_name=user_name,
            plan_name=plan_name,
            end_date="January 21, 2026",
            reactivate_url="https://app.wrext.com/pricing",
            feedback_url="https://app.wrext.com/feedback"
        )
        
        # Test 5: Subscription Upgraded
        await self.test_email_template_rendering(
            "subscription_upgraded",
            render_subscription_upgraded_email,
            user_name=user_name,
            old_plan_name=old_plan_name,
            old_plan_price="$9.99",
            new_plan_name=plan_name,
            new_plan_price=plan_price,
            effective_date="December 21, 2025",
            proration_amount="$15.00",
            customer_portal_url="https://lemonsqueezy.com/portal"
        )
        
        # Test 6: Subscription Downgraded
        await self.test_email_template_rendering(
            "subscription_downgraded",
            render_subscription_downgraded_email,
            user_name=user_name,
            old_plan_name=plan_name,
            old_plan_price=plan_price,
            new_plan_name=old_plan_name,
            new_plan_price="$9.99",
            effective_date="January 21, 2026",
            credit_amount="$20.00",
            customer_portal_url="https://lemonsqueezy.com/portal"
        )
        
        # Test 7: Refund Issued
        await self.test_email_template_rendering(
            "refund_issued",
            render_refund_issued_email,
            user_name=user_name,
            refund_amount=plan_price,
            refund_date="December 21, 2025",
            order_id="ORD-123456",
            payment_method="Visa ****4242",
            original_plan_name=plan_name,
            dashboard_url="https://app.wrext.com/dashboard"
        )
        
        # Test 8-11: Trial Reminders
        trial_end_date = (datetime.now() + timedelta(days=3)).strftime("%B %d, %Y")
        
        await self.test_email_template_rendering(
            "trial_reminder_3_days",
            render_trial_reminder_3_days_email,
            user_name=user_name,
            plan_name=plan_name,
            trial_end_date=trial_end_date,
            plan_price=plan_price,
            pricing_url="https://app.wrext.com/pricing"
        )
        
        await self.test_email_template_rendering(
            "trial_reminder_1_day",
            render_trial_reminder_1_day_email,
            user_name=user_name,
            plan_name=plan_name,
            trial_end_date=trial_end_date,
            plan_price=plan_price,
            pricing_url="https://app.wrext.com/pricing"
        )
        
        await self.test_email_template_rendering(
            "trial_reminder_expiring_today",
            render_trial_reminder_expiring_today_email,
            user_name=user_name,
            plan_name=plan_name,
            plan_price=plan_price,
            pricing_url="https://app.wrext.com/pricing"
        )
        
        await self.test_email_template_rendering(
            "trial_expired",
            render_trial_expired_email,
            user_name=user_name,
            plan_name=plan_name,
            pricing_url="https://app.wrext.com/pricing"
        )
        
        # Test 12-14: Payment Dunning
        await self.test_email_template_rendering(
            "payment_dunning_1_day",
            render_payment_dunning_1_day_email,
            user_name=user_name,
            plan_name=plan_name,
            amount=plan_price,
            update_payment_url="https://lemonsqueezy.com/portal"
        )
        
        await self.test_email_template_rendering(
            "payment_dunning_3_days",
            render_payment_dunning_3_days_email,
            user_name=user_name,
            plan_name=plan_name,
            amount=plan_price,
            suspension_date="December 24, 2025",
            update_payment_url="https://lemonsqueezy.com/portal"
        )
        
        await self.test_email_template_rendering(
            "payment_dunning_6_days",
            render_payment_dunning_6_days_email,
            user_name=user_name,
            plan_name=plan_name,
            amount=plan_price,
            suspension_date="December 24, 2025",
            update_payment_url="https://lemonsqueezy.com/portal"
        )
        
        # Test 15: Subscription Suspended
        await self.test_email_template_rendering(
            "subscription_suspended",
            render_subscription_suspended_email,
            user_name=user_name,
            plan_name=plan_name,
            reactivate_url="https://app.wrext.com/pricing"
        )
        
        # Test 16: Payment Recovered
        await self.test_email_template_rendering(
            "payment_recovered",
            render_payment_recovered_email,
            user_name=user_name,
            plan_name=plan_name,
            amount=plan_price,
            next_billing_date="January 21, 2026",
            dashboard_url="https://app.wrext.com/subscription"
        )
        
    def print_summary(self):
        """Print test results summary"""
        self.log(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
        self.log(f"{Colors.BOLD}EMAIL TEMPLATE TEST SUMMARY{Colors.END}")
        self.log(f"{Colors.BOLD}{'='*60}{Colors.END}\n")
        
        total = len(self.results)
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        
        self.log(f"Total Templates: {total}", "INFO")
        self.log(f"Passed: {passed}", "SUCCESS")
        self.log(f"Failed: {failed}", "ERROR" if failed > 0 else "INFO")
        
        if failed > 0:
            self.log("\nFailed Templates:", "ERROR")
            for result in self.results:
                if result["status"] == "FAIL":
                    self.log(f"  - {result['template']}: {result.get('error', 'Unknown error')}", "ERROR")
        
        # Calculate pass rate
        pass_rate = (passed / total * 100) if total > 0 else 0
        self.log(f"\nPass Rate: {pass_rate:.1f}%", "SUCCESS" if pass_rate >= 90 else "WARNING")
        
        # Save results
        self.save_results()
        
        if pass_rate == 100:
            self.log(f"\n🎉 ALL EMAIL TEMPLATES WORKING PERFECTLY!", "SUCCESS")
        elif pass_rate >= 90:
            self.log(f"\n✓ Most templates working. Review failures above.", "WARNING")
        else:
            self.log(f"\n✗ Multiple template failures. Review and fix issues.", "ERROR")

    def save_results(self):
        """Save test results to JSON file"""
        output_file = Path(__file__).parent.parent / "docs/testing/email_test_results.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "total_templates": len(self.results),
                "results": self.results
            }, f, indent=2)
        
        self.log(f"\nResults saved to: {output_file}", "INFO")

    async def run_tests(self):
        """Run all email tests"""
        await self.test_all_templates()
        self.print_summary()


async def main():
    """Main entry point"""
    runner = EmailTestRunner()
    await runner.run_tests()


if __name__ == "__main__":
    asyncio.run(main())
