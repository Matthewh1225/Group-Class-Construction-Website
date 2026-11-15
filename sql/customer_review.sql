-- Shared customer feedback for the business or a catalog product.
CREATE TABLE IF NOT EXISTS Customer_review (
    id INT NOT NULL AUTO_INCREMENT,
    userId INT NOT NULL,
    reviewType ENUM('general', 'product') NOT NULL,
    productId INT DEFAULT NULL,
    productName VARCHAR(160) DEFAULT NULL,
    rating TINYINT NOT NULL,
    title VARCHAR(100) NOT NULL,
    body TEXT NOT NULL,
    createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY review_created (createdAt, id),
    KEY review_type_rating (reviewType, rating),
    KEY review_product (productId),
    CONSTRAINT customer_review_user FOREIGN KEY (userId) REFERENCES `User` (id) ON DELETE CASCADE,
    CONSTRAINT customer_review_product FOREIGN KEY (productId) REFERENCES Product (id) ON DELETE SET NULL,
    CONSTRAINT customer_review_rating CHECK (rating BETWEEN 1 AND 5)
);
