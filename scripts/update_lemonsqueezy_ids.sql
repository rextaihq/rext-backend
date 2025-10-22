-- Update subscription_plans table with LemonSqueezy Product IDs
-- Phase 5 Task 5.1.1: Set up LemonSqueezy sandbox products
-- Created: 2025-10-21

-- Show current state
\echo ''
\echo '==================== BEFORE UPDATE ===================='
\echo ''
SELECT
  name,
  display_name,
  lemonsqueezy_product_id,
  lemonsqueezy_variant_id_monthly,
  lemonsqueezy_variant_id_yearly
FROM subscription_plans
WHERE name IN ('free', 'basic', 'pro', 'professional', 'enterprise')
ORDER BY name;

\echo ''
\echo '==================== UPDATING PLANS ===================='
\echo ''

-- Update Basic Plan
UPDATE subscription_plans
SET
  lemonsqueezy_product_id = '665157',
  lemonsqueezy_variant_id_monthly = '1049347',
  lemonsqueezy_variant_id_yearly = '1045158'
WHERE name = 'basic';

\echo 'Updated Basic plan'

-- Update Pro Plan
UPDATE subscription_plans
SET
  lemonsqueezy_product_id = '667795',
  lemonsqueezy_variant_id_monthly = '1049346',
  lemonsqueezy_variant_id_yearly = '1049351'
WHERE name = 'pro';

\echo 'Updated Pro plan'

-- Enterprise Plan (when created in LemonSqueezy)
-- UPDATE subscription_plans
-- SET
--   lemonsqueezy_product_id = 'XXXXX',
--   lemonsqueezy_variant_id_monthly = 'XXXXX',
--   lemonsqueezy_variant_id_yearly = 'XXXXX'
-- WHERE name = 'enterprise';

\echo ''
\echo '==================== AFTER UPDATE ===================='
\echo ''

-- Show updated state
SELECT
  name,
  display_name,
  lemonsqueezy_product_id,
  lemonsqueezy_variant_id_monthly,
  lemonsqueezy_variant_id_yearly
FROM subscription_plans
WHERE name IN ('free', 'basic', 'pro', 'professional', 'enterprise')
ORDER BY name;

\echo ''
\echo 'Update complete!'
\echo ''
