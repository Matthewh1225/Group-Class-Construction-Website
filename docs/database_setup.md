Database setup
==============

Apply the SQL files in `sql/` to the MySQL database configured for the app before
running it. Run each file in your MySQL client:

```sql
SOURCE sql/preorder_item.sql;
SOURCE sql/order_crew.sql;
SOURCE sql/customer_review.sql;
```

These scripts create missing tables and preserve existing records. They require
the application's original tables, including `User`, `Product`, and `Order`.

`Order_crew` is required for checkout receipts and order details, including orders
without crews. If an order was saved but its receipt failed because this table
was missing, apply `sql/order_crew.sql` and reload the confirmation page.
