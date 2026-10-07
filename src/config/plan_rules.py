"""
The rules every plan shares, defined once.

Prices, credits and limits are per plan and live in the `subscription_plans`
table; the credits each pipeline stage costs live in
`src/utils/credit_manager.py`; offers on new subscriptions live in the
`promotions` table. What is left is here: how long the trial lasts (applied at
signup).
"""

# Every new account starts on the trial plan for this many days (the founder,
# 2026-10-06: 7 days, as rext.ai says; a trial already running keeps its end).
TRIAL_DURATION_DAYS = 7
