#!/usr/bin/env python3
"""Email Template Validation Script"""

import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

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
    render_subscription_unpaid_email,
    render_payment_recovered_email,
)


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    END = "\033[0m"


results = []


def test(name, func, **kwargs):
    try:
        html = func(**kwargs)
        if html and len(html) > 100:
            print(f"{Colors.GREEN}✓{Colors.END} {name} ({len(html)} chars)")
            results.append({"template": name, "status": "PASS", "length": len(html)})
            return True
        else:
            print(f"{Colors.RED}✗{Colors.END} {name} - Empty")
            results.append({"template": name, "status": "FAIL", "error": "Empty"})
            return False
    except Exception as e:
        print(f"{Colors.RED}✗{Colors.END} {name} - {e}")
        results.append({"template": name, "status": "FAIL", "error": str(e)})
        return False


print("\n" + "=" * 60)
print("EMAIL TEMPLATE VALIDATION")
print("=" * 60 + "\n")

trial_date = (datetime.now() + timedelta(days=3)).strftime("%B %d, %Y")

test(
    "subscription_created",
    render_subscription_created_email,
    user_name="Test",
    plan_name="Pro",
    plan_price="$29",
    billing_period="monthly",
    features=["A", "B"],
)

test(
    "payment_succeeded",
    render_payment_succeeded_email,
    user_name="Test",
    plan_name="Pro",
    amount="$29",
    payment_date="Dec 21",
    next_billing_date="Jan 21",
)

test(
    "payment_failed",
    render_payment_failed_email,
    user_name="Test",
    plan_name="Pro",
    amount="$29",
    failed_on="Dec 24",
    update_payment_url="https://x.com",
)

test(
    "subscription_cancelled",
    render_subscription_cancelled_email,
    user_name="Test",
    plan_name="Pro",
    end_date="Jan 21",
    reactivate_url="https://x.com",
    feedback_url="https://x.com",
)

test(
    "subscription_upgraded",
    render_subscription_upgraded_email,
    user_name="Test",
    old_plan_name="Basic",
    new_plan_name="Pro",
    old_price="$9",
    new_price="$29",
    billing_date="Dec 21",
)

test(
    "subscription_downgraded",
    render_subscription_downgraded_email,
    user_name="Test",
    old_plan_name="Pro",
    new_plan_name="Basic",
    old_price="$29",
    new_price="$9",
    effective_date="Jan 21",
)

test(
    "refund_issued",
    render_refund_issued_email,
    user_name="Test",
    refund_amount="$29",
    refund_date="Dec 21",
    order_id="ORD-123",
)

test(
    "trial_reminder_3_days",
    render_trial_reminder_3_days_email,
    user_name="Test",
    plan_name="Pro",
    trial_end_date=trial_date,
)

test(
    "trial_reminder_1_day",
    render_trial_reminder_1_day_email,
    user_name="Test",
    plan_name="Pro",
    trial_end_date=trial_date,
)

test(
    "trial_reminder_expiring_today",
    render_trial_reminder_expiring_today_email,
    user_name="Test",
    plan_name="Pro",
    trial_end_date=trial_date,
)

test("trial_expired", render_trial_expired_email, user_name="Test", plan_name="Pro")

test(
    "subscription_unpaid",
    render_subscription_unpaid_email,
    user_name="Test",
    plan_name="Pro",
    update_payment_url="https://x.com",
)

test(
    "payment_recovered",
    render_payment_recovered_email,
    user_name="Test",
    plan_name="Pro",
    amount="$29",
    recovery_date="Dec 21",
    next_billing_date="Jan 21",
)

total = len(results)
passed = sum(1 for r in results if r["status"] == "PASS")
rate = (passed / total * 100) if total > 0 else 0

print(f"\n{'=' * 60}")
print(f"SUMMARY: {passed}/{total} passed ({rate:.1f}%)")
print("=" * 60 + "\n")

output = Path(__file__).parent.parent / "docs/testing/email_validation_results.json"
output.parent.mkdir(parents=True, exist_ok=True)
with open(output, "w") as f:
    json.dump({"timestamp": datetime.now().isoformat(), "results": results}, f, indent=2)

print(f"Results saved: {output}")

if rate == 100:
    print(f"\n{Colors.GREEN}🎉 ALL TEMPLATES PASSED!{Colors.END}\n")
else:
    print(f"\n{Colors.YELLOW}⚠ {total - passed} templates need attention{Colors.END}\n")
