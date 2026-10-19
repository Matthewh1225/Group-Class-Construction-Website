
erDiagram
    users {
        int id PK
        varchar username
        varchar email
        enum status
        datetime created_at
    }
    account_tokens {
        int token_id PK
        int user_id FK
        enum purpose
        datetime created_at
    }
    auth_identities {
        int identity_id PK
        int user_id FK
        enum provider
    }
    user_addresses {
        int address_id PK
        int user_id FK
        varchar label
        datetime created_at
    }
    notification_preferences {
        int user_id PK
    }
    notification_outbox {
        int notification_id PK
        int user_id FK
        int project_id FK
        varchar template_key
        enum status
    }
    saved_payment_methods {
        int method_id PK
        int user_id FK
        varchar provider
    }
    subscriptions {
        int subscription_id PK
        int user_id FK
        varchar plan_name
        enum status
        varchar provider
        datetime created_at
    }
    subscription_invoices {
        int invoice_id PK
        int subscription_id FK
        decimal amount
        enum status
    }
    projects {
        int project_id PK
    }
    users ||..o{ account_tokens : "user_id"
    users ||..o{ auth_identities : "user_id"
    users ||..o{ notification_outbox : "user_id"
    projects o|..o{ notification_outbox : "project_id, user_id"
    users ||--o| notification_preferences : "user_id"
    users ||..o{ saved_payment_methods : "user_id"
    subscriptions ||..o{ subscription_invoices : "subscription_id"
    users ||..o{ subscriptions : "user_id"
    users ||..o{ user_addresses : "user_id"
```

## Product catalog

```mermaid
erDiagram
    categories {
        int category_id PK
        varchar category_name
    }
    subcategories {
        int subcategory_id PK
        int category_id FK
        varchar subcategory_name
    }
    manufacturers {
        int manufacturer_id PK
        varchar manufacturer_name
    }
    suppliers {
        int supplier_id PK
        varchar supplier_name
    }
    products {
        int product_id PK
        int category_id FK
        int subcategory_id FK
        int manufacturer_id FK
        varchar product_name
        varchar sku
        datetime created_at
    }
    product_inventory {
        int product_id PK
        decimal unit_price
    }
    product_images {
        int image_id PK
        int product_id FK
    }
    product_suppliers {
        int product_id PK
        int supplier_id PK
    }
    product_reviews {
        int review_id PK
        int user_id FK
        int product_id FK
        tinyint rating
        enum status
        datetime created_at
    }
    users {
        int id PK
    }
    products ||..o{ product_images : "product_id"
    products ||--o| product_inventory : "product_id"
    users ||..o{ product_reviews : "user_id"
    products ||..o{ product_reviews : "product_id"
    products ||--o{ product_suppliers : "product_id"
    suppliers ||--o{ product_suppliers : "supplier_id"
    categories ||..o{ products : "category_id"
    subcategories o|..o{ products : "subcategory_id, category_id"
    manufacturers o|..o{ products : "manufacturer_id"
    categories ||..o{ subcategories : "category_id"
```

## Cart, orders, and payments

```mermaid
erDiagram
    carts {
        int cart_id PK
        int user_id FK
        datetime created_at
    }
    cart_items {
        int cart_item_id PK
        int cart_id FK
        int product_id FK
        decimal quantity
    }
    orders {
        int order_id PK
        int user_id FK
        enum status
        decimal total_amount
        datetime created_at
    }
    order_items {
        int order_item_id PK
        int order_id FK
        int product_id FK
        decimal quantity
        decimal unit_price
    }
    payments {
        int payment_id PK
        int order_id FK
        varchar provider
        enum status
        decimal amount
        datetime created_at
    }
    payment_refunds {
        int refund_id PK
        int payment_id FK
        decimal amount
        enum status
        datetime created_at
    }
    discount_codes {
        int discount_id PK
        varchar code
        decimal amount
    }
    discount_redemptions {
        int redemption_id PK
        int discount_id FK
        int order_id FK
    }
    inventory_reservations {
        int reservation_id PK
        int product_id FK
        int order_id FK
        decimal quantity
        enum status
        datetime created_at
    }
    product_inventory {
        int product_id PK
    }
    products {
        int product_id PK
    }
    users {
        int id PK
    }
    carts ||..o{ cart_items : "cart_id"
    products ||..o{ cart_items : "product_id"
    users ||..o| carts : "user_id"
    discount_codes ||..o{ discount_redemptions : "discount_id"
    orders ||..o{ discount_redemptions : "order_id"
    product_inventory ||..o{ inventory_reservations : "product_id"
    orders ||..o{ inventory_reservations : "order_id"
    orders ||..o{ order_items : "order_id"
    products o|..o{ order_items : "product_id"
    users ||..o{ orders : "user_id"
    payments ||..o{ payment_refunds : "payment_id"
    orders ||..o{ payments : "order_id"
```

## Projects and materials

```mermaid
erDiagram
    projects {
        int project_id PK
        int user_id FK
        varchar title
        varchar project_type
        enum status
        datetime created_at
    }
    planner_results {
        int result_id PK
        int project_id FK
        int user_id FK
        enum tier
        enum status
        datetime created_at
    }
    project_crews {
        int crew_id PK
        int project_id FK
        int user_id FK
        varchar label
        enum source
        datetime created_at
    }
    project_crew_members {
        int member_id PK
        int crew_id FK
        varchar specialty
    }
    material_lists {
        int material_list_id PK
        int project_id FK
        int user_id FK
        varchar title
        enum source
        enum tier
        datetime created_at
    }
    material_list_items {
        int material_item_id PK
        int material_list_id FK
        int product_id FK
        varchar purpose
        decimal quantity
        datetime created_at
    }
    material_acquisitions {
        int acquisition_id PK
        int material_item_id FK
        int order_item_id FK
        decimal quantity
        enum source
    }
    project_showcases {
        int showcase_id PK
        int project_id FK
        varchar title
        enum status
    }
    showcase_images {
        int image_id PK
        int showcase_id FK
    }
    order_items {
        int order_item_id PK
    }
    products {
        int product_id PK
    }
    users {
        int id PK
    }
    material_list_items ||..o{ material_acquisitions : "material_item_id"
    order_items o|..o{ material_acquisitions : "order_item_id"
    material_lists ||..o{ material_list_items : "material_list_id"
    products o|..o{ material_list_items : "product_id"
    projects ||..o{ material_lists : "project_id, user_id"
    projects ||..o{ planner_results : "project_id, user_id"
    project_crews ||..o{ project_crew_members : "crew_id"
    projects ||..o{ project_crews : "project_id, user_id"
    projects ||..o| project_showcases : "project_id"
    users ||..o{ projects : "user_id"
    project_showcases ||..o{ showcase_images : "showcase_id"
```

## Service bookings

```mermaid
erDiagram
    service_providers {
        int provider_id PK
        varchar name
    }
    service_offerings {
        int offering_id PK
        int provider_id FK
        int product_id FK
        varchar title
        enum offering_type
        varchar specialty
        decimal unit_price
    }
    service_bookings {
        int booking_id PK
        int user_id FK
        int project_id FK
        int offering_id FK
        int quantity
        enum status
    }
    products {
        int product_id PK
    }
    projects {
        int project_id PK
    }
    users {
        int id PK
    }
    users ||..o{ service_bookings : "user_id"
    projects o|..o{ service_bookings : "project_id, user_id"
    service_offerings ||..o{ service_bookings : "offering_id"
    service_providers ||..o{ service_offerings : "provider_id"
    products o|..o{ service_offerings : "product_id"
```

## Planner job store (SQLite)

The application creates these two tables in `planning/jobs.py`. Their `owner` values contain a MySQL user ID as text, and `saved_projects.job_id` identifies a planner job. SQLite does not declare foreign keys for either link, so the dashed connections below show application-level references only. `saved_projects.plan` and `crew`, and `planner_jobs.data`, contain JSON text.

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
        INTEGER plan_version
        TEXT crew
        INTEGER completed
        REAL created
        REAL updated
    }
    mysql_users {
        int id PK
    }
    mysql_users ||..o{ planner_jobs : "owner (application link)"
    mysql_users ||..o{ saved_projects : "owner (application link)"
    planner_jobs ||..o| saved_projects : "job_id (application link)"
```

SQLite enforces `UNIQUE(owner, submission_key)` on `planner_jobs` and `UNIQUE(owner, job_id)` on `saved_projects`. The MySQL `projects.source_job_id`, `planner_results.source_job_id`, and `material_lists.source_job_id` also refer to planner jobs by value without cross-database foreign keys.
