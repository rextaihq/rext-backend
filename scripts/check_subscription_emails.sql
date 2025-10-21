-- Check all users and their subscriptions
-- This helps diagnose the email mismatch issue

SELECT
  u.email,
  u.id as user_id,
  us.id as subscription_id,
  sp.name as plan_name,
  us.status,
  us.billing_period,
  us.lemonsqueezy_subscription_id,
  us.created_at
FROM users u
LEFT JOIN user_subscriptions us ON u.id = us.user_id
LEFT JOIN subscription_plans sp ON us.plan_id = sp.id
WHERE u.email IN ('mobeen4@yopmail.com', 'mobeenabdullah@gmail.com', 'mobeen3@yopmail.com', 'test-checkout@example.com')
ORDER BY us.created_at DESC NULLS LAST;

-- Also show the most recent active subscriptions
SELECT
  u.email,
  u.id as user_id,
  us.id as subscription_id,
  sp.name as plan_name,
  us.status,
  us.created_at
FROM user_subscriptions us
JOIN users u ON us.user_id = u.id
JOIN subscription_plans sp ON us.plan_id = sp.id
WHERE us.status IN ('ACTIVE', 'TRIAL')
ORDER BY us.created_at DESC
LIMIT 10;
