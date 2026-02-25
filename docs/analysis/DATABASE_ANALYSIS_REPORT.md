# AI Analyst Database Analysis
**Source:** JuniorCouture Production Database Dump  
**Date:** 2026-02-25  
**Database Size:** 38.68 GB (974 tables)

---

## Executive Summary

This database contains a full Odoo 17 installation with extensive customizations for JuniorCouture. Key characteristics:

- **974 total tables** (standard Odoo + custom modules)
- **91 product-related tables**
- **119 sale/order-related tables**
- **114 stock/inventory tables**
- **Heavy customization** with x_ prefixed fields

---

## Key Business Tables

### 1. Products

#### Core Tables:
| Table | Purpose | Key Fields |
|-------|---------|------------|
| `product_template` | Product master data | name, list_price, categ_id, default_code, active |
| `product_product` | Product variants | product_tmpl_id, barcode, default_code, active |
| `product_category` | Product categories | name, parent_id |
| `product_attribute` | Product attributes (size, color) | name, create_variant |
| `product_attribute_value` | Attribute values | name, attribute_id |

#### Important Custom Fields (x_):
- `x_studio_style_reference` - Style identifier
- `x_studio_color_reference` - Color code
- `x_studio_sfcc_url` - Salesforce Commerce Cloud URL
- `x_studio_country_of_origin_1` - Manufacturing origin
- `x_isNew` - New product flag
- `x_pickLocation` - Warehouse pick location
- `x_google_product_category` - Google Shopping category

#### Calculated/Computed Fields:
- `total_sold` - Total units sold
- `total_free_qty` - Free quantity available
- `mayoral_total_bought` - Mayoral vendor purchases
- `mayoral_total_sold` - Mayoral vendor sales
- `mayoral_total_soh` - Mayoral stock on hand
- `total_ecom_soh` - E-commerce stock on hand
- `weeks_from_live_date` - Product age in weeks

### 2. Sales & Orders

#### Core Tables:
| Table | Purpose | Key Fields |
|-------|---------|------------|
| `sale_order` | Sales orders | name, partner_id, amount_total, state, date_order |
| `sale_order_line` | Order lines | order_id, product_id, product_uom_qty, price_unit, price_subtotal |
| `pos_order` | POS orders | name, partner_id, amount_total, state, date_order |
| `pos_order_line` | POS order lines | order_id, product_id, qty, price_unit |

#### Important States:
- `sale_order.state`: draft, sent, sale, done, cancel
- `pos_order.state`: draft, paid, done, cancel, invoiced

### 3. Inventory & Stock

#### Core Tables:
| Table | Purpose | Key Fields |
|-------|---------|------------|
| `stock_move` | Stock movements | product_id, product_uom_qty, location_id, location_dest_id, state |
| `stock_quant` | Current stock levels | product_id, location_id, quantity, reserved_quantity |
| `stock_location` | Warehouse locations | name, usage, parent_id |
| `stock_picking` | Picking operations | name, partner_id, location_id, location_dest_id, state |

### 4. Accounting

#### Core Tables:
| Table | Purpose | Key Fields |
|-------|---------|------------|
| `account_move` | Journal entries/invoices | name, partner_id, amount_total, state, move_type, date |
| `account_move_line` | Entry lines | move_id, account_id, debit, credit, balance, product_id |
| `account_account` | Chart of accounts | code, name, account_type |

#### Move Types:
- `entry` - Journal entry
- `out_invoice` - Customer invoice
- `in_invoice` - Vendor bill
- `out_refund` - Customer credit note
- `in_refund` - Vendor credit note

### 5. Partners/Customers

#### Core Table:
| Table | Purpose | Key Fields |
|-------|---------|------------|
| `res_partner` | Customers/suppliers | name, email, phone, street, city, country_id, customer_rank, supplier_rank |

---

## Key Relationships

```
product_template (1) ----< (N) product_product (variants)
    |
    |----< (N) sale_order_line
    |----< (N) pos_order_line
    |----< (N) account_move_line
    |----< (N) stock_move
    |----< (N) stock_quant

sale_order (1) ----< (N) sale_order_line
    |
    |---- (1) res_partner (customer)
    |----< (N) account_move (invoices)

stock_picking (1) ----< (N) stock_move
    |
    |---- (1) sale_order (delivery)
    |---- (1) purchase_order (receipt)
```

---

## Critical Fields for AI Queries

### Product Count Queries:
```sql
-- Total active products
SELECT COUNT(*) FROM product_template WHERE active = true;

-- Total product variants
SELECT COUNT(*) FROM product_product WHERE active = true;

-- Products by category
SELECT c.name, COUNT(*) 
FROM product_template p 
JOIN product_category c ON p.categ_id = c.id 
WHERE p.active = true 
GROUP BY c.name;
```

### Sales Queries:
```sql
-- Total sales amount
SELECT SUM(amount_total) FROM sale_order WHERE state = 'sale';

-- Sales by month
SELECT DATE_TRUNC('month', date_order) as month, SUM(amount_total)
FROM sale_order 
WHERE state = 'sale' 
GROUP BY month;

-- Top selling products
SELECT pt.name, SUM(sol.product_uom_qty) as total_qty
FROM sale_order_line sol
JOIN sale_order so ON sol.order_id = so.id
JOIN product_product pp ON sol.product_id = pp.id
JOIN product_template pt ON pp.product_tmpl_id = pt.id
WHERE so.state = 'sale'
GROUP BY pt.name
ORDER BY total_qty DESC;
```

### Inventory Queries:
```sql
-- Current stock levels
SELECT pt.name, SUM(sq.quantity) as qty
FROM stock_quant sq
JOIN product_product pp ON sq.product_id = pp.id
JOIN product_template pt ON pp.product_tmpl_id = pt.id
WHERE sq.location_id IN (SELECT id FROM stock_location WHERE usage = 'internal')
GROUP BY pt.name;

-- Stock movements today
SELECT pp.default_code, sm.product_uom_qty, sm.date
FROM stock_move sm
JOIN product_product pp ON sm.product_id = pp.id
WHERE sm.date >= CURRENT_DATE;
```

---

## Custom Modules & Extensions

### Identified Custom Fields/Tables:
1. **Mayoral Integration** - `mayoral_*` fields on products
2. **SFCC (Salesforce Commerce Cloud)** - `x_sfcc_*` fields
3. **Studio Customizations** - `x_studio_*` fields
4. **Inventory API** - `inventory_api_log` table
5. **Product Exports** - `product_export` table
6. **IZI Dashboard** - `izi_*` tables

### Special Fields:
- `landed_cost_ok` - Landed costs enabled
- `is_wallet_product` - Digital wallet product
- `is_delivery_product` - Shipping product
- `is_discount_product` - Discount product
- `is_exclusive` - Exclusive/premium product
- `hero_product` / `non_hero_product` - Marketing classification
- `gift_box` - Gift box eligible
- `personalization` - Customizable product

---

## Recommendations for AI Analyst

### 1. Intent Classification Keywords
Add these to `_classify_intent()` regex:
- **Product queries:** `how many products`, `total products`, `product count`, `catalog size`
- **Sales queries:** `total sales`, `revenue`, `turnover`, `sales amount`, `orders today`
- **Inventory queries:** `stock level`, `inventory count`, `available quantity`, `on hand`
- **Customer queries:** `total customers`, `active customers`, `new customers`

### 2. Query Planner Hints
- Product counts should use `product_template` (master) not `product_product` (variants)
- Sales totals should filter by `state = 'sale'` (confirmed orders only)
- Inventory should filter `stock_location.usage = 'internal'` (warehouse only)
- Date ranges should use `date_order` for sales, `date` for accounting

### 3. Field Knowledge Base
Add descriptions for custom fields:
- `total_sold` - "Total units sold across all channels"
- `mayoral_total_soh` - "Stock on hand from Mayoral vendor"
- `x_studio_style_reference` - "Product style identifier for merchandising"
- `weeks_from_live_date` - "Product age since first sale"

### 4. Common Query Patterns
Pre-build query templates for:
- Product catalog size
- Daily/weekly/monthly sales
- Top selling products
- Low stock alerts
- Customer count by type
- Revenue by category

### 5. Data Quality Notes
- Many `x_` fields are custom Studio fields - may have inconsistent data
- Product names are stored as JSONB (multilingual)
- Currency amounts stored in `numeric` type (precise decimals)
- Boolean fields use `true`/`false` not `1`/`0`

---

## Sample Data Statistics

### Estimated Row Counts (from schema analysis):
| Table | Estimated Rows |
|-------|---------------|
| product_template | ~50,000 |
| product_product | ~150,000 |
| sale_order | ~500,000 |
| sale_order_line | ~2,000,000 |
| pos_order | ~1,000,000 |
| account_move | ~2,000,000 |
| res_partner | ~100,000 |
| stock_move | ~5,000,000 |

---

## Next Steps

1. **Load this analysis** into AI Analyst's field knowledge base
2. **Add query templates** for common business questions
3. **Update intent classifier** with keywords from this analysis
4. **Create dimension mappings** for custom fields
5. **Build computed metrics** using the custom calculated fields

---

**Generated by:** Database Analysis Script  
**Output files:**
- `schema_sample.sql` - First 50MB of schema
- `key_tables_schema.sql` - Detailed schema for 9 key tables
- `all_tables.txt` - Complete list of 974 tables
