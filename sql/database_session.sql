-- Gives user 1014 (Matt) Pro for one more year in the TEST database.
-- Run this only on the test database. It is safe to run more than once.
-- Pro is stored as User.proUntil, the last day of Pro access (see sql/erd_schema.sql).

USE construction_db_test;

UPDATE `User`
SET proUntil = DATE_ADD(CURDATE(), INTERVAL 1 YEAR)
WHERE Id = 1014;
