-- Run once in the database used by the website. Existing data is kept.
CREATE TABLE IF NOT EXISTS Cart_item (
    user_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL,
    PRIMARY KEY (user_id, product_id),
    CHECK (quantity > 0),
    FOREIGN KEY (user_id) REFERENCES `User` (Id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES Product (Id) ON DELETE CASCADE
);
