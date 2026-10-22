
CREATE TABLE `User` (
    id INT AUTO_INCREMENT PRIMARY KEY,
    firstName VARCHAR(50) NOT NULL,
    lastName VARCHAR(50) NOT NULL DEFAULT '',
    email VARCHAR(100) NOT NULL UNIQUE,
    passkey VARCHAR(255) NOT NULL,
    permissions ENUM('user', 'admin') NOT NULL DEFAULT 'user',
    dateCreated DATE NOT NULL
);

CREATE TABLE Administrator (
    userId INT PRIMARY KEY,
    notes TEXT,
    FOREIGN KEY (userId) REFERENCES `User` (id) ON DELETE CASCADE
);

-- Administrators also have a customer profile: they can shop and use Pro.
CREATE TABLE Customer (
    userId INT PRIMARY KEY,
    streetAddress VARCHAR(100),
    city VARCHAR(50),
    state VARCHAR(50),
    zipcode INT,
    accountStatus VARCHAR(20) NOT NULL DEFAULT 'active',
    proDate DATE,
    CHECK (zipcode IS NULL OR zipcode BETWEEN 0 AND 99999),
    CHECK (accountStatus IN ('active', 'disabled')),
    FOREIGN KEY (userId) REFERENCES `User` (id) ON DELETE CASCADE
);

CREATE TABLE Manufacturer (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL
);

CREATE TABLE Product (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    subCategory ENUM(
        'Accessories', 'Anchors', 'Blocks', 'Bolts', 'Boxes', 'Compaction',
        'Compaction tools', 'Concrete tools', 'Connectors', 'Decking',
        'Demolition tools', 'Doors', 'Ductwork', 'Earthmoving', 'Fencing',
        'Filters', 'Finishing', 'Fittings', 'Flashing', 'Forms', 'Framing',
        'Hand tools', 'Hauling', 'Installation', 'Insulation', 'Laminate',
        'Lifting', 'Lighting', 'Loading', 'Mix', 'Mortar', 'Nails', 'Outlets',
        'Paint', 'Panels', 'Pipe', 'Posts', 'Power tools', 'Primer', 'Rebar',
        'Registers', 'Reinforcement', 'Screws', 'Sealants', 'Sheathing',
        'Shingles', 'Subfloor', 'Switches', 'Tile', 'Trim', 'Underlayment',
        'Ventilation', 'Vinyl', 'Windows', 'Wire'
    ) NOT NULL,
    details TEXT,
    price DECIMAL(12, 2) NOT NULL,
    dimensions VARCHAR(100),
    materials VARCHAR(100),
    itemQty INT NOT NULL DEFAULT 1,
    stockQty INT NOT NULL DEFAULT 0,
    -- Added to the ERD: used by category pages, planner unit matching, search and hiding retired products.
    category ENUM('lumber', 'fasteners', 'concrete', 'tools', 'electrical',
                  'drywall', 'roofing', 'plumbing', 'hvac', 'flooring', 'paint',
                  'doors-windows', 'heavy-machinery') NOT NULL,
    unit VARCHAR(50) NOT NULL DEFAULT 'piece',
    sku VARCHAR(80) UNIQUE,
    keywords VARCHAR(512),
    isActive BOOLEAN NOT NULL DEFAULT TRUE,
    CHECK (price >= 0),
    CHECK (itemQty > 0),
    CHECK (stockQty >= 0),
    CHECK (isActive IN (0, 1))
);

CREATE TABLE Manufacturer_products (
    manid INT NOT NULL,
    productId INT NOT NULL,
    PRIMARY KEY (manid, productId),
    FOREIGN KEY (manid) REFERENCES Manufacturer (id) ON DELETE CASCADE,
    FOREIGN KEY (productId) REFERENCES Product (id) ON DELETE CASCADE
);

-- Added to the ERD: the working shopping cart. Order/Order_item record purchases at
-- the price paid, so a cart cannot be stored there. See docs/database_erd.md.
CREATE TABLE Cart_item (
    userId INT NOT NULL,
    productId INT NOT NULL,
    itemQty INT NOT NULL,
    PRIMARY KEY (userId, productId),
    CHECK (itemQty > 0),
    FOREIGN KEY (userId) REFERENCES `User` (id) ON DELETE CASCADE,
    FOREIGN KEY (productId) REFERENCES Product (id) ON DELETE CASCADE
);

CREATE TABLE `Order` (
    id INT AUTO_INCREMENT PRIMARY KEY,
    userId INT NOT NULL,
    dateCreated DATE NOT NULL,
    dateCompleted DATE,
    totalCost DECIMAL(12, 2) NOT NULL,
    orderStatus ENUM('pending', 'paid', 'shipped', 'completed', 'cancelled')
        NOT NULL DEFAULT 'pending',
    shippingAddress VARCHAR(255),
    CHECK (totalCost >= 0),
    FOREIGN KEY (userId) REFERENCES `User` (id) ON DELETE CASCADE
);

CREATE TABLE Order_item (
    orderId INT NOT NULL,
    productId INT NOT NULL,
    itemQty INT NOT NULL,
    unitPrice DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (orderId, productId),
    CHECK (itemQty > 0),
    CHECK (unitPrice >= 0),
    FOREIGN KEY (orderId) REFERENCES `Order` (id) ON DELETE CASCADE,
    FOREIGN KEY (productId) REFERENCES Product (id)
);

CREATE TABLE Payments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    dateCharged DATE NOT NULL,
    userId INT NOT NULL,
    payStatus ENUM('pending', 'paid', 'failed', 'refunded') NOT NULL DEFAULT 'pending',
    -- Safe display information only; never store a raw card number.
    cardLast4 CHAR(4),
    orderId INT,
    amount DECIMAL(12, 2) NOT NULL,
    CHECK (amount >= 0),
    FOREIGN KEY (userId) REFERENCES `User` (id) ON DELETE CASCADE,
    FOREIGN KEY (orderId) REFERENCES `Order` (id) ON DELETE CASCADE
);
