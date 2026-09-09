"""
Billing Email Templates

Templates for subscription and billing-related emails.
"""

from .subscription_created import render_subscription_created_email
from .payment_succeeded import render_payment_succeeded_email
from .payment_failed import render_payment_failed_email
from .subscription_cancelled import render_subscription_cancelled_email
from .trial_ending import render_trial_ending_email
from .trial_reminder_3_days import render_trial_reminder_3_days_email
from .trial_reminder_1_day import render_trial_reminder_1_day_email
from .trial_reminder_expiring_today import render_trial_reminder_expiring_today_email
from .trial_expired import render_trial_expired_email
from .subscription_renewed import render_subscription_renewed_email
from .subscription_expiring_soon import render_subscription_expiring_soon_email
from .upgrade_successful import render_upgrade_successful_email
from .downgrade_scheduled import render_downgrade_scheduled_email
from .usage_limit_warning import render_usage_limit_warning_email
from .usage_limit_exceeded import render_usage_limit_exceeded_email
from .payment_dunning_1_day import render_payment_dunning_1_day_email
from .payment_dunning_3_days import render_payment_dunning_3_days_email
from .payment_dunning_6_days import render_payment_dunning_6_days_email
from .subscription_suspended import render_subscription_suspended_email
from .payment_recovered import render_payment_recovered_email
from .subscription_upgraded import render_subscription_upgraded_email
from .subscription_downgraded import render_subscription_downgraded_email
from .refund_issued import render_refund_issued_email
from .refund_request_status import (
    render_refund_approved_email,
    render_refund_rejected_email,
    render_refund_request_received_email,
)
from .refund_requested_admin import render_refund_requested_admin_email

__all__ = [
    'render_subscription_created_email',
    'render_payment_succeeded_email',
    'render_payment_failed_email',
    'render_subscription_cancelled_email',
    'render_trial_ending_email',
    'render_trial_reminder_3_days_email',
    'render_trial_reminder_1_day_email',
    'render_trial_reminder_expiring_today_email',
    'render_trial_expired_email',
    'render_subscription_renewed_email',
    'render_subscription_expiring_soon_email',
    'render_upgrade_successful_email',
    'render_downgrade_scheduled_email',
    'render_usage_limit_warning_email',
    'render_usage_limit_exceeded_email',
    'render_payment_dunning_1_day_email',
    'render_payment_dunning_3_days_email',
    'render_payment_dunning_6_days_email',
    'render_subscription_suspended_email',
    'render_payment_recovered_email',
    'render_subscription_upgraded_email',
    'render_subscription_downgraded_email',
    'render_refund_issued_email',
    'render_refund_approved_email',
    'render_refund_rejected_email',
    'render_refund_request_received_email',
    'render_refund_requested_admin_email',
]
