-- Gives user 1014 (Matt) an active Pro subscription in the TEST database.
-- Run this only on the test database. It is safe to run more than once:
-- a row is added only if the user does not already have an active subscription.

USE construction_db_test;

INSERT INTO subscriptions
    (user_id, plan_name, status, billing_interval, provider,
     provider_customer_id, provider_subscription_id, started_at, current_period_end, cancel_at_period_end)
SELECT
    1014, 'Pro', 'active', 'month', 'test',
    'test_cus_1014', 'test_sub_1014', NOW(), DATE_ADD(NOW(), INTERVAL 1 YEAR), 0
FROM DUAL
WHERE NOT EXISTS (
    SELECT 1 FROM subscriptions WHERE user_id = 1014 AND status = 'active'
);
