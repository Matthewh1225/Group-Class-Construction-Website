-- Complete BuildBetter MySQL setup.
-- Change Construction_db in both statements below if a different database name is needed.
-- Keep table name casing exact: Linux can treat User and user differently.
-- An Administrator row gives a user admin access.

CREATE DATABASE IF NOT EXISTS Construction_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE Construction_db;

CREATE TABLE IF NOT EXISTS `User` (
    Id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    firstName VARCHAR(50),
    lastName VARCHAR(50),
    email VARCHAR(100) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,                                  -- Argon2 password hash
    dob DATE,
    status ENUM('active', 'disabled') NOT NULL DEFAULT 'active',
    date_created DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    proUntil DATE                                                    -- Last day of Pro access; NULL means none
);

CREATE TABLE IF NOT EXISTS Administrator (
    user_Id INT PRIMARY KEY,
    permissions INT,
    notes TEXT,
    FOREIGN KEY (user_Id) REFERENCES `User` (Id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Customer (
    user_Id INT PRIMARY KEY,
    address VARCHAR(100),
    FOREIGN KEY (user_Id) REFERENCES `User` (Id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Manufacturer (
    Id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50)
);

-- Manufacturer_products links products to their manufacturers.
CREATE TABLE IF NOT EXISTS Product (
    Id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100),
    category VARCHAR(50),                                            -- Filter key used in routes/products.py
    subCategory VARCHAR(50),
    details TEXT,
    price DECIMAL(10, 2),
    dimensions VARCHAR(100),
    materials VARCHAR(100),
    itemQty INT,
    manufacturer VARCHAR(100),
    sku VARCHAR(80) UNIQUE,
    keywords VARCHAR(512),
    unit VARCHAR(50) NOT NULL DEFAULT 'piece',                       -- Unit sold, such as piece or box
    packQuantity DECIMAL(14, 3) NOT NULL DEFAULT 1,                  -- Amount in one item, such as 350 screws per box
    purchaseIncrement DECIMAL(12, 3) NOT NULL DEFAULT 1,             -- Smallest purchase step in the chosen unit
    isActive BOOLEAN NOT NULL DEFAULT TRUE                           -- Hide a product without deleting its order history
);

CREATE TABLE IF NOT EXISTS Cart_item (
    user_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL,
    PRIMARY KEY (user_id, product_id),
    CHECK (quantity > 0),
    FOREIGN KEY (user_id) REFERENCES `User` (Id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES Product (Id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Manufacturer_products (
    manId INT,
    productId INT,
    PRIMARY KEY (manId, productId),
    FOREIGN KEY (manId) REFERENCES Manufacturer (Id) ON DELETE CASCADE,
    FOREIGN KEY (productId) REFERENCES Product (Id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS `Order` (
    Id INT AUTO_INCREMENT PRIMARY KEY,
    user_Id INT,
    date_created DATE,
    date_completed DATE,
    totalCost DECIMAL(10, 2),
    status ENUM('pending', 'paid', 'shipped', 'completed', 'cancelled')
        NOT NULL DEFAULT 'pending',
    shippingAddress VARCHAR(255),
    FOREIGN KEY (user_Id) REFERENCES `User` (Id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Order_item (
    order_id INT,
    product_id INT,
    quantity DECIMAL(12, 3) NOT NULL,
    unitPrice DECIMAL(10, 2) NOT NULL,                               -- Keep the price at the time of the order
    PRIMARY KEY (order_id, product_id),
    FOREIGN KEY (order_id) REFERENCES `Order` (Id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES Product (Id)
);

-- Store only the last four card digits, never the full number.
CREATE TABLE IF NOT EXISTS Payments (
    Id INT AUTO_INCREMENT PRIMARY KEY,
    transType INT,
    cardLast4 CHAR(4),
    date_charged DATE,
    user_id INT,
    order_id INT,
    amount DECIMAL(10, 2) NOT NULL,
    status ENUM('pending', 'paid', 'failed', 'refunded')
        NOT NULL DEFAULT 'pending',
    FOREIGN KEY (user_id) REFERENCES `User` (Id) ON DELETE CASCADE,
    FOREIGN KEY (order_id) REFERENCES `Order` (Id) ON DELETE CASCADE
);
