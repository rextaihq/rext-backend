"""The billing emails promise only what the app does (G34, revnix/rext-control#369).

The plans are the trial and the paid plans of the catalogue: credits each month,
and workspaces and members by plan. There is no free plan to fall back to, no
priority support, no topics, knowledge items or API-call quota, and the yearly
price is not 20 % off. When a plan or a trial ends, the account and its content
stay; writing needs a plan again. Each email is rendered here and read for the
claims the old copy made.
"""

import re

import pytest

from emails.templates.billing.payment_recovered import render_payment_recovered_email
from emails.templates.billing.subscription_cancelled import render_subscription_cancelled_email
from emails.templates.billing.subscription_expiring_soon import (
    render_subscription_expiring_soon_email,
)
from emails.templates.billing.trial_ending import render_trial_ending_email
from emails.templates.billing.trial_expired import render_trial_expired_email
from emails.templates.billing.trial_reminder_1_day import render_trial_reminder_1_day_email
from emails.templates.billing.trial_reminder_3_days import render_trial_reminder_3_days_email
from emails.templates.billing.trial_reminder_expiring_today import (
    render_trial_reminder_expiring_today_email,
)
from emails.templates.billing.usage_limit_exceeded import render_usage_limit_exceeded_email
from emails.templates.billing.usage_limit_warning import render_usage_limit_warning_email

PERSON = {"user_name": "Sam", "plan_name": "Growth"}
TRIAL = {"user_name": "Sam", "plan_name": "Trial", "trial_end_date": "October 14, 2026"}

EMAILS = {
    "subscription_cancelled": lambda: render_subscription_cancelled_email(
        **PERSON, end_date="November 6, 2026"
    ),
    "subscription_expiring_soon": lambda: render_subscription_expiring_soon_email(
        **PERSON, expiry_date="November 6, 2026", days_remaining=7
    ),
    "trial_ended_through_expiring_soon": lambda: render_subscription_expiring_soon_email(
        user_name="Sam", plan_name="Trial", expiry_date="October 14, 2026", days_remaining=0
    ),
    "trial_ending": lambda: render_trial_ending_email(**TRIAL, days_remaining=3),
    "trial_reminder_3_days": lambda: render_trial_reminder_3_days_email(**TRIAL),
    "trial_reminder_1_day": lambda: render_trial_reminder_1_day_email(**TRIAL),
    "trial_reminder_expiring_today": lambda: render_trial_reminder_expiring_today_email(**TRIAL),
    "trial_expired": lambda: render_trial_expired_email(user_name="Sam", plan_name="Trial"),
    "payment_recovered": lambda: render_payment_recovered_email(
        **PERSON,
        amount="$89.00",
        recovery_date="October 9, 2026",
        next_billing_date="November 9, 2026",
    ),
    "usage_limit_warning": lambda: render_usage_limit_warning_email(
        user_name="Sam",
        resource_type="credits",
        current_usage=480,
        usage_limit=600,
        percentage_used=80,
        plan_name="Growth",
    ),
    "usage_limit_exceeded": lambda: render_usage_limit_exceeded_email(
        user_name="Sam",
        resource_type="credits",
        current_usage=600,
        usage_limit=600,
        plan_name="Growth",
        restrictions=["New articles wait until your credits renew"],
    ),
}

RETIRED_CLAIMS = [
    r"free plan",
    r"priority support",
    r"unlimited",
    r"topics?\b",
    r"knowledge",
    r"api (calls|access)",
    r"save 20",
    r"export capabilit",
    r"losing access to your premium features and data",
]


@pytest.mark.parametrize("name", EMAILS)
def test_the_email_makes_none_of_the_retired_claims(name):
    text = re.sub(r"<[^>]+>", " ", EMAILS[name]()).lower()
    found = [claim for claim in RETIRED_CLAIMS if re.search(claim, text)]
    assert not found, f"{name} still says: {found}"


@pytest.mark.parametrize(
    "name",
    ["subscription_cancelled", "trial_ended_through_expiring_soon", "trial_expired"],
)
def test_the_email_says_the_account_and_its_content_stay(name):
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", EMAILS[name]()))
    assert "workspaces, articles and keyword library" in text


def test_an_ended_plan_reads_as_ended_and_points_to_the_plans():
    html = EMAILS["trial_ended_through_expiring_soon"]()
    assert "Your Plan Has Ended" in html
    assert "0 day" not in html
    assert "Choose a Plan" in html


def test_one_day_left_is_singular():
    html = render_trial_ending_email(**TRIAL, days_remaining=1)
    assert "1 day</strong>" in html
    assert "1 days" not in html
