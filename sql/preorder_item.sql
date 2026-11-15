-- Pre-order items: planner materials we don't sell, or don't have enough stock of.
-- A row with orderId = NULL is still in the user's cart.
-- Placing an order fills in orderId.
CREATE TABLE IF NOT EXISTS Preorder_item (
    id INT NOT NULL AUTO_INCREMENT,
    userId INT NOT NULL,
    orderId INT DEFAULT NULL,
    productId INT DEFAULT NULL,          -- set when the material matched a store product
    name VARCHAR(255) NOT NULL,
    unit VARCHAR(50) NOT NULL,
    quantity DECIMAL(12,2) NOT NULL,
    unitPrice DECIMAL(12,2) DEFAULT NULL, -- store price or estimate; old NULL rows get a rough guess in code
    PRIMARY KEY (id),
    KEY userId (userId),
    KEY orderId (orderId),
    KEY productId (productId),
    CONSTRAINT Preorder_item_user FOREIGN KEY (userId) REFERENCES User (id) ON DELETE CASCADE,
    CONSTRAINT Preorder_item_order FOREIGN KEY (orderId) REFERENCES `Order` (id) ON DELETE CASCADE,
    CONSTRAINT Preorder_item_product FOREIGN KEY (productId) REFERENCES Product (id) ON DELETE SET NULL,
    CONSTRAINT Preorder_item_qty CHECK (quantity > 0),
    CONSTRAINT Preorder_item_price CHECK (unitPrice >= 0)
);
