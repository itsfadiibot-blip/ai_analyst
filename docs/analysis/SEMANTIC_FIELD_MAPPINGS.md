# Semantic Field Mappings for AI Analyst
**Purpose:** Bridge the gap between user natural language and actual database values

---

## 1. Season Field Mapping

### Field Location:
- **Model:** `product.template`
- **Field:** `x_studio_many2many_field_IXz60` (many2many)
- **Related Model:** `x_product_tags`
- **Label:** "Product Tags (Season)"

### Value Pattern:
Seasons are stored as: `{AGE}{SEASON}{YEAR}`
- **AGE:** 2-digit number (e.g., 00=adult, 01-20=child age)
- **SEASON:** FW=Fall/Winter, SS=Spring/Summer
- **YEAR:** 2-digit year (e.g., 25=2025)

**Examples:**
| Database Value | User Might Say | Search Strategy |
|---------------|----------------|-----------------|
| 19FW25 | "FW25", "Fall Winter 25", "Winter 25" | `ilike '%FW25%'` |
| 20FW26 | "FW26", "Fall Winter 26" | `ilike '%FW26%'` |
| 03SS25 | "SS25", "Spring Summer 25", "Summer 25" | `ilike '%SS25%'` |
| 05SS26 | "SS26", "Spring Summer 26" | `ilike '%SS26%'` |

### Semantic Rules:
```
User Input "FW25" → Search x_product_tags.name ILIKE '%FW25%'
User Input "Winter 25" → Search x_product_tags.name ILIKE '%FW25%'
User Input "Fall Winter 2025" → Search x_product_tags.name ILIKE '%FW25%'
User Input "SS25" → Search x_product_tags.name ILIKE '%SS25%'
User Input "Summer 25" → Search x_product_tags.name ILIKE '%SS25%'
User Input "age 3 winter" → Search x_product_tags.name ILIKE '03FW%'
```

---

## 2. Color Reference Mapping

### Field Location:
- **Model:** `product.template`
- **Field:** `x_studio_color_reference` (char)

### Value Pattern:
Colors stored as numbers that map to actual colors:

| Code | Color Name |
|------|-----------|
| 1 | White / Blanc / أبيض |
| 2 | Black / Noir / أسود |
| 3 | Red / Rouge / أحمر |
| 4 | Blue / Bleu / أزرق |
| 5 | Green / Vert / أخضر |
| 6 | Yellow / Jaune / أصفر |
| 7 | Pink / Rose / وردي |
| 8 | Grey / Gris / رمادي |
| 9 | Brown / Marron / بني |
| 10+ | Extended palette |

### Semantic Rules:
```
User Input "red products" → x_studio_color_reference = '3'
User Input "black" → x_studio_color_reference = '2'
User Input "white dress" → x_studio_color_reference = '1'
```

---

## 3. Style Reference Mapping

### Field Location:
- **Model:** `product.template`
- **Field:** `x_studio_style_reference` (char)
- **Purpose:** Groups colorways of same master style

### Value Pattern:
Style codes are alphanumeric identifiers like:
- `JC1234`
- `MYRL5678`
- `MAY2024001`

### Search Strategy:
- Exact match preferred
- Partial match if user enters partial code
- Case insensitive

---

## 4. Product Category Mapping

### Issue:
Categories barely used (almost all products in category "1" = "All")
Actual classification uses custom fields.

### Real Category Fields:
| User Says | Actual Field | Search |
|-----------|-------------|--------|
| "clothing" | `detailed_type` = 'product' | Basic check |
| "services" | `detailed_type` = 'service' | Service products |
| "consumables" | `detailed_type` = 'consu' | Consumables |
| "kids age 3" | `x_product_tags` containing '03' | Age-based |

---

## 5. Price Field Mapping

### Issue:
Only ~4% of products have `list_price` > 0

### Actual Price Sources:
| Field | Description | When to Use |
|-------|-------------|-------------|
| `list_price` | Base price | If > 0 |
| `x_studio_list_price` | Studio custom price | Alternative |
| `lst_price_aed` | AED specific price | For AED queries |
| `x_studio_jc_list_price` | JC list price | Another alternative |
| **Pricelists** | Customer-specific | Most accurate |

### Semantic Rule:
```
User asks "product price" → 
  COALESCE(NULLIF(list_price, 0), x_studio_list_price, lst_price_aed) > 0
```

---

## 6. Age Group Mapping

### Field Location:
- **Model:** `product.template`
- **Field:** `age_group` (char)

### Values in Data:
```
WH## = Winter items for age ## (e.g., WH22 = Winter age 2-3)
WS## = Summer items for age ## (e.g., WS03 = Summer age 3)
```

### Semantic Rules:
```
User Input "age 2" → age_group ILIKE '%02%' OR x_product_tags ILIKE '%02%'
User Input "baby clothes" → age_group IN ('WH00', 'WS00', 'WH01', 'WS01')
User Input "teen" → age_group >= 'WH12' OR age_group >= 'WS12'
```

---

## 7. Channel/Source Mapping

### Order Sources:
| User Says | Database Value | Field |
|-----------|---------------|-------|
| "online" | `origin` contains 'SFCC' or website_id set | sale_order |
| "website" | Same as above | sale_order |
| "store" | `pos_order` record exists | pos_order |
| "POS" | Point of sale orders | pos_order |
| "Farfetch" | Specific origin marker | sale_order |

---

## 8. Status/State Mappings

### Sales Order States:
| User Says | Database Value |
|-----------|---------------|
| "draft orders" | state = 'draft' |
| "confirmed orders" | state = 'sale' |
| "sent quotations" | state = 'sent' |
| "done/completed" | state = 'done' |
| "cancelled" | state = 'cancel' |
| "active orders" | state IN ('sale', 'done') |

### Product Active Status:
| User Says | Database Value |
|-----------|---------------|
| "active products" | active = true |
| "inactive/discontinued" | active = false |
| "available" | active = true AND sale_ok = true |

---

## 9. Common Abbreviations

| Abbreviation | Full Meaning |
|--------------|-------------|
| FW | Fall Winter |
| SS | Spring Summer |
| SOH | Stock on Hand |
| SKU | Stock Keeping Unit (product.product) |
| Style | Master style (product.template groups) |
| POS | Point of Sale (in-store) |
| SFCC | Salesforce Commerce Cloud (online) |
| AED | UAE Dirhams (currency) |
| VAT | Value Added Tax (5%) |
| WH | Warehouse |
| SO | Sale Order |
| PO | Purchase Order |
| DO | Delivery Order |

---

## 10. Query Translation Examples

### Example 1: Season Query
**User:** "Show me FW25 products"  
**Translation:**
```python
# Find tags containing FW25
tags = env['x_product_tags'].search([('name', 'ilike', 'FW25')])
# Find products with those tags
products = env['product.template'].search([
    ('x_studio_many2many_field_IXz60', 'in', tags.ids),
    ('active', '=', True)
])
```

### Example 2: Age + Season Query
**User:** "Winter clothes for 3 year old"  
**Translation:**
```python
# Age 3 = '03' prefix in tags
tags = env['x_product_tags'].search([('name', 'ilike', '03FW%')])
products = env['product.template'].search([
    ('x_studio_many2many_field_IXz60', 'in', tags.ids)
])
```

### Example 3: Multi-Season Query
**User:** "Products in FW25 or SS25"  
**Translation:**
```python
tags = env['x_product_tags'].search([
    '|', ('name', 'ilike', 'FW25'), ('name', 'ilike', 'SS25')
])
products = env['product.template'].search([
    ('x_studio_many2many_field_IXz60', 'in', tags.ids)
])
```

---

## Implementation Notes for AI Analyst

1. **Always use `ilike` for text matching** - case insensitive
2. **Use `%` wildcards** for partial matching on season codes
3. **Consider age prefix** when user mentions child age
4. **Check multiple price fields** - don't rely on list_price alone
5. **Categories are unreliable** - use tags and custom fields instead
6. **Season is many2many** - product can have multiple seasons
7. **Style reference groups variants** - use for "find all colors of this style"

---

**Generated:** 2026-02-25  
**Based on:** Production database analysis + Knowledge Base  
**Purpose:** Field semantic mappings for query planner
