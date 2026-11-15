-- Crews that were paid for in an order. Placing an order copies each crew
-- from crew_cart into this table, so the receipt and order history can show it.
CREATE TABLE IF NOT EXISTS Order_crew (
    id INT NOT NULL AUTO_INCREMENT,
    orderId INT NOT NULL,
    label VARCHAR(255) NOT NULL,
    workers INT NOT NULL,
    days VARCHAR(100) NOT NULL,
    priceCents BIGINT NOT NULL,
    PRIMARY KEY (id),
    KEY orderId (orderId),
    CONSTRAINT Order_crew_order FOREIGN KEY (orderId) REFERENCES `Order` (id) ON DELETE CASCADE
);
