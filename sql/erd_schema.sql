-- Creates the BuildBetter.com ERD tables in the database you are connected to.
-- Test database: run  python sql/setup_test_database.py  (it empties the test database,
-- then runs this file and sql/erd_test_data.sql).
-- Production: run this file once, then sql/migrate_production_users.sql.
--
-- Tables and columns follow the ERD. Columns marked "-- added" are not on the ERD yet:
-- the website needs them (login, admin tools, Pro access, store, orders, AI planner).
-- The ERD does not give key types, so every Id is INT, and single-column Ids count up
-- automatically (AUTO_INCREMENT).
-- A user is an admin when they have a row in Administrator (no role column is needed).
-- Deleting a User also deletes their Administrator, Customer, Order and Payments rows
-- (ON DELETE CASCADE), which the "delete account" feature relies on.
-- `Order` is a reserved word in MySQL, so it is always written with backticks.
-- MySQL on Windows stores table names in lowercase (user, product, `order`, ...), but on
-- Linux (the production server) names are case-sensitive, so the code always writes them
-- exactly as they are created here: `User`, Administrator, Customer, Product, ...

CREATE TABLE `User` (
    Id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,                            -- added: sign-in name
    firstName VARCHAR(50),
    lastName VARCHAR(50),
    email VARCHAR(100) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,                                  -- was VARCHAR(20): holds an Argon2 hash (about 100 characters; older accounts a 60-character bcrypt hash), never the real password
    dob DATE,
    status ENUM('active', 'disabled') NOT NULL DEFAULT 'active',     -- added: admins can disable accounts
    date_created DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,        -- added: shown on the admin dashboard
    proUntil DATE                                                    -- added: Pro subscription end date; NULL = no Pro
);

-- One-to-zero-or-one with User: user_Id is both the key and the link to User.
CREATE TABLE Administrator (
    user_Id INT PRIMARY KEY,
    permissions INT,
    notes TEXT,
    FOREIGN KEY (user_Id) REFERENCES `User` (Id) ON DELETE CASCADE
);

-- One-to-zero-or-one with User: user_Id is both the key and the link to User.
CREATE TABLE Customer (
    user_Id INT PRIMARY KEY,
    address VARCHAR(100),
    FOREIGN KEY (user_Id) REFERENCES `User` (Id) ON DELETE CASCADE
);

CREATE TABLE Manufacturer (
    Id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50)
);

-- price is the current price; itemQty is the stock on hand.
-- manufacturer is shown in red on the ERD; it is kept here, but Manufacturer_products
-- is the table that links products to manufacturers.
CREATE TABLE Product (
    Id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100),
    category VARCHAR(50),                                            -- added: store category, e.g. 'lumber' (routes/products.py PRODUCT_CATEGORIES)
    subCategory VARCHAR(50),
    details TEXT,
    price DECIMAL(10, 2),
    dimensions VARCHAR(100),
    materials VARCHAR(100),
    itemQty INT,
    manufacturer VARCHAR(100),
    sku VARCHAR(80) UNIQUE,                                          -- added: stock code, shown and searched in the store
    keywords VARCHAR(512),                                           -- added: extra words for the store search
    unit VARCHAR(50) NOT NULL DEFAULT 'piece',                       -- added: what one item is (piece, sheet, box, bag...)
    packQuantity DECIMAL(14, 3) NOT NULL DEFAULT 1,                  -- added: how many are in one item, e.g. 350 screws in a box
    purchaseIncrement DECIMAL(12, 3) NOT NULL DEFAULT 1,             -- added: buy in steps of this many units
    isActive BOOLEAN NOT NULL DEFAULT TRUE                           -- added: FALSE hides a product without deleting order history
);

-- Which manufacturers make which products (many-to-many).
CREATE TABLE Manufacturer_products (
    manId INT,
    productId INT,
    PRIMARY KEY (manId, productId),
    FOREIGN KEY (manId) REFERENCES Manufacturer (Id) ON DELETE CASCADE,
    FOREIGN KEY (productId) REFERENCES Product (Id) ON DELETE CASCADE
);

CREATE TABLE `Order` (
    Id INT AUTO_INCREMENT PRIMARY KEY,
    user_Id INT,
    date_created DATE,
    date_completed DATE,
    totalCost DECIMAL(10, 2),
    status ENUM('pending', 'paid', 'shipped', 'completed', 'cancelled')
        NOT NULL DEFAULT 'pending',                                  -- added: shown on the Orders pages
    shippingAddress VARCHAR(255),                                    -- added: where this order is sent
    FOREIGN KEY (user_Id) REFERENCES `User` (Id) ON DELETE CASCADE
);

-- The products in each order; one row per order and product.
CREATE TABLE Order_item (
    order_id INT,
    product_id INT,
    quantity DECIMAL(12, 3) NOT NULL,                                -- added: how many were ordered
    unitPrice DECIMAL(10, 2) NOT NULL,                               -- added: price when ordered (Product.price can change later)
    PRIMARY KEY (order_id, product_id),
    FOREIGN KEY (order_id) REFERENCES `Order` (Id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES Product (Id)
);

-- "Payments (store or not)" on the ERD. Full card numbers are never stored: only the
-- last 4 digits, so the page can show "card ending 4242".
CREATE TABLE Payments (
    Id INT AUTO_INCREMENT PRIMARY KEY,
    transType INT,
    cardLast4 CHAR(4),                                               -- was cardNumber INT: too small for a card number, and full numbers must not be stored
    date_charged DATE,
    user_id INT,
    order_id INT,                                                    -- added: the order this payment is for
    amount DECIMAL(10, 2) NOT NULL,                                  -- added: how much was charged
    status ENUM('pending', 'paid', 'failed', 'refunded')
        NOT NULL DEFAULT 'pending',                                  -- added
    FOREIGN KEY (user_id) REFERENCES `User` (Id) ON DELETE CASCADE,
    FOREIGN KEY (order_id) REFERENCES `Order` (Id) ON DELETE CASCADE
);
