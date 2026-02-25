# Deep Data Analysis Report
**Generated:** 2026-02-25 05:29
**Source:** JuniorCouture Production Database (41.5 GB dump)
**Method:** Streaming parse with sampling

## Sampling Methodology
- Streamed through zip without full extraction
- Parsed all COPY statements for target tables
- Small tables: captured all rows (sample_rate=1)
- Large tables: sampled every Nth row

| Table | Total Rows | Sampled | Rate |
|-------|-----------|---------|------|
| account_move | 1,271,040 | 31,776 | 1:40 |
| account_move_line | 2,923,146 | 36,539 | 1:80 |
| pos_order | 34,602 | 1,730 | 1:20 |
| pos_order_line | 105,524 | 2,638 | 1:40 |
| product_attribute | 5 | 5 | 1:1 |
| product_attribute_value | 321 | 321 | 1:1 |
| product_category | 10 | 10 | 1:1 |
| product_product | 332,799 | 200,000 | 1:1 |
| product_template | 54,867 | 54,867 | 1:1 |
| res_country | 250 | 250 | 1:1 |
| res_partner | 385,861 | 120,000 | 1:1 |
| sale_order | 143,751 | 14,375 | 1:10 |
| sale_order_line | 638,752 | 15,968 | 1:40 |
| stock_location | 33,535 | 5,000 | 1:1 |
| stock_move | 2,491,416 | 24,914 | 1:100 |
| stock_quant | 471,153 | 100,000 | 1:1 |

---
## 1. Product Data Analysis
**Total products:** 54,867
**Active:** 48,281 | **Inactive:** 6,586

### Price Statistics
- Min: 1.00
- Max: 210.00
- Average: 1.84
- Median: 1.00
- Products with price > 0: 2,095

### Product Types
- `product`: 54,506
- `consu`: 308
- `service`: 53

### Top Categories (by categ_id)
- Category #1: 54,824 products
- Category #5: 32 products
- Category #10: 5 products
- Category #4: 3 products
- Category #8: 1 products
- Category #11: 1 products
- Category #3: 1 products

### Custom Fields (x_*) Population
| Field | Populated | % | Unique Values |
|-------|----------|---|---------------|
| x_studio_style_reference | 54,558 | 99.4% | 39656 |
| x_studio_color_reference | 54,540 | 99.4% | 34 |
| x_studio_product_class | 54,558 | 99.4% | 2 |
| x_studio_hs_code | 54,339 | 99.0% | 996 |
| x_studio_country_of_origin_1 | 53,472 | 97.5% | 195 |
| x_studio_sfcc_sales_description | 51,424 | 93.7% | 50732 |
| x_studio_arabic_sfcc_sales_description | 51,171 | 93.3% | 50453 |
| x_cat_write_date | 48,124 | 87.7% | 8214 |
| x_avtive | 47,842 | 87.2% | 2 |
| x_comestri_ref | 33,836 | 61.7% | 4165 |
| x_studio_sfcc_url | 26,417 | 48.1% | 24815 |
| x_studio_active | 238 | 0.4% | 1 |
| x_studio_list_price | 238 | 0.4% | 1 |
| x_sfcc_primcat_write_date | 52 | 0.1% | 11 |
| x_testprodate | 2 | 0.0% | 2 |
| x_sale | 25 | 0.0% | 19 |
| x_sfcc_primary_category | 5 | 0.0% | 5 |

---
## 2. Sales Pattern Analysis
**Total sale orders:** 143,751
**Sampled:** 14,375 (1:10)

### Order States
- `sale`: ~141,960 (sampled: 14,196)
- `cancel`: ~1,790 (sampled: 179)

### Order Amount Statistics (Online)
- Min: 0.00
- Max: 26227.00
- Average: 593.13
- Median: 388.00

### POS Order Amount Statistics
- Min: -1090.00
- Max: 53510.00
- Average: 726.73
- Median: 410.00

### Channel Split: 143751 online : 34602 POS

### Orders by Year
- 2023: ~13,140
- 2024: ~52,810
- 2025: ~64,440
- 2026: ~13,360

### Orders by Month (sampled)
| Month | Count (sampled) |
|-------|----------------|
| 2023-09 | 139 |
| 2023-10 | 320 |
| 2023-11 | 475 |
| 2023-12 | 380 |
| 2024-01 | 465 |
| 2024-02 | 463 |
| 2024-03 | 755 |
| 2024-04 | 355 |
| 2024-05 | 390 |
| 2024-06 | 529 |
| 2024-07 | 303 |
| 2024-08 | 259 |
| 2024-09 | 372 |
| 2024-10 | 363 |
| 2024-11 | 436 |
| 2024-12 | 591 |
| 2025-01 | 523 |
| 2025-02 | 537 |
| 2025-03 | 855 |
| 2025-04 | 321 |
| 2025-05 | 629 |
| 2025-06 | 498 |
| 2025-07 | 410 |
| 2025-08 | 326 |
| 2025-09 | 423 |
| 2025-10 | 443 |
| 2025-11 | 750 |
| 2025-12 | 729 |
| 2026-01 | 809 |
| 2026-02 | 527 |

### Customer Orders: 12,727 unique customers in sample
Order frequency distribution (orders → customer count):
- 1 order(s): 11,731 customers
- 2 order(s): 800 customers
- 3 order(s): 127 customers
- 4 order(s): 48 customers
- 5 order(s): 12 customers
- 6 order(s): 2 customers
- 7 order(s): 3 customers
- 8 order(s): 1 customers
- 13 order(s): 1 customers
- 21 order(s): 1 customers
- 336 order(s): 1 customers

---
## 3. Customer Analysis
**Total partners:** 385,861
- Customer rank > 0: 47,512
- Supplier rank > 0: 8
- Both customer & supplier: 0
- Active: 119,745 | Inactive: 255
- Has email: 21,110 | No email: 98,890

### Top Countries (by country_id)
- Country #2: 63,207
- Country #192: 27,722
- Country #122: 8,887
- Country #233: 4,935
- Country #231: 2,444
- Country #13: 1,594
- Country #186: 1,321
- Country #23: 877
- Country #171: 207
- Country #38: 194
- Country #156: 186
- Country #113: 106
- Country #197: 101
- Country #48: 101
- Country #101: 85

### Top Cities
- Dubai: 21,404
- dubai: 7,463
- الرياض: 4,283
- Abu Dhabi: 4,053
- Riyadh: 3,361
- Sharjah: 2,421
- Jeddah: 1,782
- Alain: 1,229
- Dubai : 1,088
- undefined: 947
- جدة: 932
- الكويت: 824
- Al Ain: 824
- Abudhabi: 697
- Ajman: 688

### Custom Fields (x_*)

---
## 4. Inventory Analysis
**Total stock_quant records:** 471,153
- Positive qty records: 32,197
- Zero qty records: 23
- Negative qty records: 67,780
- Total stock units: -1,086,259
- Average qty per record: -10.86

**Total stock moves:** 2,491,416
### Stock Move States
- `done`: 23,179 (sampled)
- `cancel`: 1,140 (sampled)
- `draft`: 516 (sampled)
- `assigned`: 63 (sampled)
- `confirmed`: 13 (sampled)
- `waiting`: 3 (sampled)

### Top Stock Locations (by location_id)
- Location #14: 53,652 quant records
- Location #5: 31,443 quant records
- Location #4: 14,196 quant records
- Location #15786: 87 quant records
- Location #32641: 35 quant records
- Location #30022: 25 quant records
- Location #30023: 18 quant records
- Location #31025: 9 quant records
- Location #19879: 8 quant records
- Location #29088: 8 quant records
- Location #34563: 7 quant records
- Location #26349: 7 quant records
- Location #15817: 7 quant records
- Location #24507: 6 quant records
- Location #26729: 6 quant records


---
## 5. Resolved Reference Data

### Product Categories (product_category)
Only 10 categories exist:
- Shipping (x2 entries), Saleable, Expenses, PoS, All, Events, Deliveries, Discount, EIR-1920100-9-10
- **Note:** 54,824 of 54,867 products are in category #1 (likely 'All') — categories are barely used

### Product Attributes
5 attributes defined (all create_variant='always'):
- **Colorway** — primary variant axis
- **STYLE** — style reference
- **OLD STYLE** — legacy
- **Brand** (العلامة التجارية) — brand name
- **SKU** — individual SKU

### Account Move Types (from sample)
- entry: ~1,167K journal entries (91.8%)
- out_invoice: ~104K customer invoices (8.2%)
- **Note:** No vendor bills (in_invoice), credit notes (out_refund/in_refund) found in sample

### Account Move States
- posted: 99.997%
- draft: 0.003%

### Payment States (invoices only)
- 
ot_paid: ~6,610 sampled
- in_payment: ~513 sampled  
- paid: ~7 sampled

### POS Order States
- done: 99.2%
- paid: 0.6%
- invoiced: 0.2%

### Stock Move States
- done: 93.0%
- cancel: 4.6%
- draft: 2.1%
- ssigned: 0.25%
- confirmed/waiting: <0.1%

### Key Stock Locations
- Location #14 (53,652 quants) — primary warehouse
- Location #5 (31,443 quants) — likely virtual/customer
- Location #4 (14,196 quants) — likely virtual/vendor
- Named locations include: JC-USQ warehouse with bin structure (e.g., JC-USQ/Stock/223/A/5)

### Country Distribution (resolved from res_country)
Top countries (by country_id → partner count):
- #2 → UAE (63,207 partners) — **dominant market**
- #192 → Saudi Arabia (27,722)
- #122 → Kuwait (8,887)
- #233 → USA (4,935)
- #231 → UK (2,444)
- #13 → Australia (1,594)
- #186 → Qatar (1,321)
- #23 → Bahrain (877)

### Business Insights Summary
1. **JuniorCouture is a UAE-based children's fashion retailer** operating since Sep 2023
2. **80% online, 20% POS** sales channel split (143K online vs 35K POS orders)
3. **Average order value: ~593 AED** (online), ~727 AED (POS)  
4. **Growing business:** 2023 partial year → 2024: ~53K orders → 2025: ~64K orders (21% YoY growth)
5. **Seasonal peaks:** March and Nov-Dec are strongest months
6. **GCC-focused:** UAE (53%), Saudi (23%), Kuwait (7%)
7. **Product catalog:** 54,867 products, 88% active, 99.4% are 'product' type (storable)
8. **Categories underused:** Nearly all products in single category — classification happens via custom fields
9. **Key custom fields:** x_studio_style_reference (99.4%), x_studio_color_reference (99.4%), x_studio_product_class (99.4%)
10. **Price data issue:** Only 2,095 of 54,867 products have list_price > 0 (avg 1.84) — pricing likely managed elsewhere
11. **Inventory concern:** Negative total stock (-1.08M units) suggests heavy virtual location usage or data patterns
12. **Customer base:** 47,512 customers out of 385,861 partners, mostly one-time buyers (92% single order in sample)
