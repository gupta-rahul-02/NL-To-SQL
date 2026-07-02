# Sales Database Schema

This document describes the core tables in the Sales database.

## Orders
Stores one row per customer order.

| Column        | Type        | Notes                         |
|---------------|-------------|-------------------------------|
| order_id      | INT         | Primary key, auto-increment   |
| customer_id   | INT         | FK → Customers.customer_id    |
| order_date    | DATETIME    | UTC timestamp of order        |
| status        | VARCHAR(20) | pending, shipped, delivered   |
| total_amount  | DECIMAL     | Sum of all line items         |
| region        | VARCHAR(50) | Geographic sales region       |

## OrderItems
Line items belonging to an order.

| Column        | Type        | Notes                         |
|---------------|-------------|-------------------------------|
| item_id       | INT         | Primary key                   |
| order_id      | INT         | FK → Orders.order_id          |
| product_id    | INT         | FK → Products.product_id      |
| quantity      | INT         | Units ordered                 |
| unit_price    | DECIMAL     | Price at time of order        |

## Customers
Customer master data.

| Column        | Type        | Notes                         |
|---------------|-------------|-------------------------------|
| customer_id   | INT         | Primary key                   |
| name          | VARCHAR(100)|                               |
| email         | VARCHAR(200)|                               |
| country       | VARCHAR(60) |                               |
| signup_date   | DATE        |                               |

## Products
Product catalogue.

| Column        | Type        | Notes                         |
|---------------|-------------|-------------------------------|
| product_id    | INT         | Primary key                   |
| name          | VARCHAR(200)|                               |
| category      | VARCHAR(80) | e.g. Electronics, Apparel     |
| price         | DECIMAL     | Current list price            |
| stock         | INT         | Units in inventory            |

## Key Business Rules
- "Q1" means January–March (DATEPART(QUARTER, ...) = 1).
- "Revenue" is calculated as SUM(quantity * unit_price) from OrderItems.
- Cancelled orders have status = 'cancelled' and should be excluded from revenue reports.
- "Active customers" means customers who have placed at least one non-cancelled order.
