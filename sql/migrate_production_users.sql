-- Moves the production accounts into the ERD tables. Run on PRODUCTION, in this order:
--   1. sql/erd_schema.sql            (creates User, Administrator, Customer, Product, ...)
--   2. this file                     (copies every account from the old users table)
-- Deploy the new website code right after step 2: the new code only reads the ERD tables.
--
-- Nothing is deleted. The old users table stays as a backup; drop it later once
-- logins work:  DROP TABLE users;
-- Accounts keep the same Id, username, email, password hash and status, so everyone signs
-- in exactly as before, and saved AI plans (which store the user Id) still belong to them.
-- Their old bcrypt hashes still work; the website replaces each one with an Argon2 hash
-- the next time that user signs in (routes/auth.py login).
-- An email longer than 100 characters (User.email's size) would make step 2 fail; check first:
--   SELECT id, email FROM users WHERE CHAR_LENGTH(email) > 100;

START TRANSACTION;

INSERT INTO `User` (Id, username, email, password, status, date_created)
SELECT id, username, email, password_hash, status, created_at
FROM users;

-- Admins get a row in Administrator; everyone else gets a row in Customer.
INSERT INTO Administrator (user_Id)
SELECT id FROM users WHERE permission_level = 'admin';

INSERT INTO Customer (user_Id)
SELECT id FROM users WHERE permission_level <> 'admin';

COMMIT;

-- Check: both counts should be the same.
SELECT (SELECT COUNT(*) FROM users) AS old_accounts, (SELECT COUNT(*) FROM `User`) AS new_accounts;
