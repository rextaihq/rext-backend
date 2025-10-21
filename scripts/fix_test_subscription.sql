-- Fix test subscription after webhook URL misconfiguration
-- Phase 5 Task 5.1.2 - Manual subscription fix
-- Date: 2025-10-21

-- Show current state
\echo 'CURRENT STATE:'
SELECT
  sp.name as plan_name,
  sp.display_name,
  us.status,
  us.lemonsqueezy_subscription_id,
  us.lemonsqueezy_customer_id
FROM user_subscriptions us
JOIN subscription_plans sp ON us.plan_id = sp.id
WHERE us.user_id = (SELECT id FROM users WHERE email = 'test-checkout@example.com')
ORDER BY us.created_at DESC
LIMIT 1;

\echo ''
\echo 'UPDATING SUBSCRIPTION WITH LEMONSQUEEZY DATA...'

-- Update the subscription with LemonSqueezy data from webhook
UPDATE user_subscriptions
SET
  plan_id = (SELECT id FROM subscription_plans WHERE name = 'basic'),
  status = 'ACTIVE',
  billing_period = 'MONTHLY',
  lemonsqueezy_subscription_id = '1576999',
  lemonsqueezy_customer_id = '6953801',
  lemonsqueezy_order_id = '6647758',
  lemonsqueezy_product_id = '665157',
  lemonsqueezy_variant_id = '1049347',
  renews_at = '2025-11-21T03:55:32.000000Z'::timestamp,
  trial_end_date = NULL,
  updated_at = NOW()
WHERE user_id = (SELECT id FROM users WHERE email = 'test-checkout@example.com')
AND plan_id = (SELECT id FROM subscription_plans WHERE name = 'trial');

\echo ''
\echo 'UPDATED STATE:'
SELECT
  sp.name as plan_name,
  sp.display_name,
  us.status,
  us.billing_period,
  us.lemonsqueezy_subscription_id,
  us.lemonsqueezy_customer_id,
  us.lemonsqueezy_variant_id,
  us.renews_at
FROM user_subscriptions us
JOIN subscription_plans sp ON us.plan_id = sp.id
WHERE us.user_id = (SELECT id FROM users WHERE email = 'test-checkout@example.com')
ORDER BY us.created_at DESC
LIMIT 1;

\echo ''
\echo 'Subscription fixed! User should now see Basic Monthly plan.'
