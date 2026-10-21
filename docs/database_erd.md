# BuildBetter database

## MySQL tables (team ERD)


```mermaid
erDiagram
    User {
        int Id PK
        varchar firstName
        varchar lastName
        varchar email "unique"
        varchar password "Argon2 hash"
        date dob
        varchar username "added, unique"
        enum status "added: active or disabled"
        datetime date_created "added"
        date proUntil "added: last day of Pro, NULL = no Pro"
    }
    Administrator {
        int user_Id PK, FK
        int permissions
        text notes
    }
    Customer {
        int user_Id PK, FK
        varchar address
    }
    Manufacturer {
        int Id PK
        varchar name
    }
    Manufacturer_products {
        int manId PK, FK
        int productId PK, FK
    }
    Product {
        int Id PK
        varchar name
        varchar subCategory
        text details
        decimal price
        varchar dimensions
        varchar materials
        int itemQty "stock on hand"
        varchar manufacturer "red on the ERD"
        varchar category "added"
        varchar sku "added, unique"
        varchar keywords "added"
        varchar unit "added"
        decimal packQuantity "added"
        decimal purchaseIncrement "added"
        boolean isActive "added"
    }
    Order {
        int Id PK
        int user_Id FK
        date date_created
        date date_completed
        decimal totalCost
        enum status "added"
        varchar shippingAddress "added"
    }
    Order_item {
        int order_id PK, FK
        int product_id PK, FK
        decimal quantity "added"
        decimal unitPrice "added"
    }
    Payments {
        int Id PK
        int transType
        char cardLast4 "was cardNumber"
        date date_charged
        int user_id FK
        int order_id FK "added"
        decimal amount "added"
        enum status "added"
    }
    User ||--o| Administrator : "user_Id"
    User ||--o| Customer : "user_Id"
    User ||--o{ Order : "user_Id"
    User ||--o{ Payments : "user_id"
    Order ||--o{ Order_item : "order_id"
    Product ||--o{ Order_item : "product_id"
    Order |o--o{ Payments : "order_id"
    Manufacturer ||--o{ Manufacturer_products : "manId"
    Product ||--o{ Manufacturer_products : "productId"
```

## Planner job store (SQLite)

The application creates these two tables in `planning/jobs.py`. Their `owner` values contain a MySQL `User.Id` as text, and `saved_projects.job_id` identifies a planner job. SQLite does not declare foreign keys for either link, so the dashed connections below show application-level references only. `saved_projects.plan` and `crew`, and `planner_jobs.data`, contain JSON text.

```mermaid
erDiagram
    planner_jobs {
        TEXT id PK
        TEXT owner
        TEXT submission_key
        TEXT request_hash
        TEXT tier
        TEXT status
        TEXT phase
        REAL created
        REAL updated
        REAL lease_until
        TEXT worker
        TEXT data
    }
    saved_projects {
        INTEGER id PK
        TEXT owner
        TEXT job_id
        TEXT name
        TEXT plan
        TEXT crew
        INTEGER completed
        REAL created
        REAL updated
    }
    mysql_User {
        int Id PK
    }
    mysql_User ||..o{ planner_jobs : "owner (application link)"
    mysql_User ||..o{ saved_projects : "owner (application link)"
    planner_jobs ||..o| saved_projects : "job_id (application link)"
```

SQLite enforces `UNIQUE(owner, submission_key)` on `planner_jobs` and `UNIQUE(owner, job_id)` on `saved_projects`. The ERD has no MySQL tables for projects or material lists, so AI plans and saved projects live only in this SQLite file.

## Planner result JSON

`planner_jobs.data` stores each job's inputs and its result as JSON. `saved_projects.plan` stores a copy of the job's `tier`, `project`, `answers` and `result`. A job keeps one result, with no versions or stage snapshots. A failed job is never resumed: **Start again** creates a new job from the same `project` and `answers`.

The result uses the same shape at every step: each AI estimate stage returns it, `run_stage` validates it once on arrival (Pydantic models in `planning/schemas.py`), and after that it is a plain dictionary in storage and in the templates.

```json
{
  "planning_status": "partial",
  "summary": "12 x 16 ft pressure-treated deck, 3 ft above ground.",
  "materials": [
    {
      "material_name": "Pressure-treated deck board",
      "specification": "5/4 x 6 in x 16 ft",
      "quantity": 36,
      "unit": "piece",
      "waste_percent": 10,
      "round_up": true,
      "calculation": {"method": "count", "inputs": [{"name": "count", "value": 32, "unit": "piece"}]},
      "notes": "Boards run the 16 ft length; 32 rows plus waste.",
      "product_id": 1003
    },
    {
      "material_name": "Footing concrete",
      "specification": "Design-dependent",
      "quantity": null,
      "unit": "cu_ft",
      "waste_percent": 0,
      "round_up": false,
      "calculation": {"method": "manual", "inputs": []},
      "notes": "Unknown: footing size and count need a local design.",
      "product_id": null
    }
  ],
  "assumptions": ["Joists 16 in on center"],
  "warnings": ["Footings, beams and posts need local design approval."]
}
```

- `quantity` is the amount the project **needs**, in `unit`, with waste included. It is `null` when the details given are not enough to calculate it; `notes` then says what is missing. A quantity is never invented.
- Python recalculates `quantity` from `calculation` for every method except `manual` (`check_estimate`).
- `product_id` is `Product.Id`. It is `null` unless the ID belongs to an active product in the catalog the planner was given; any other ID is removed before the result is saved.
- `planning_status` is added by Python: `partial` when any quantity is `null`, otherwise `complete`.
- The purchase quantity is kept separate from the required quantity. It is never stored; the plan page works it out from database product data (`planning/presentation.py`). The page shows it only when the material's unit matches `Product.unit`, rounded up to `Product.purchaseIncrement`. When the units differ (for example `sq_ft` of decking and a `piece` of board), the page leaves the choice to the user.

### Product fields

The JSON stores only `product_id`. Everything else about a product is read from MySQL whenever a plan is shown (`services/products.py` `get_products_by_ids`). The queries rename the columns with `AS`, so the code can tell a product's name and price apart from a material's:

| Name in the code and pages | `Product` column |
| --- | --- |
| `product_id` | `Id` |
| `product_name` | `name` |
| `unit_price` | `price` |
| `available_quantity` | `itemQty` |
| `unit` | `unit` |
| `purchase_increment` | `purchaseIncrement` |
