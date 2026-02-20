# 04 — Dimension Dictionary

## Problem Statement

The LLM needs to translate natural language ("FW25 women's sneakers by brand") into structured tool parameters. Product data is spread across multiple Odoo fields:

- `product.template` fields: `categ_id`, `default_code`, `name`
- `product.tag` records: seasons (06AW21, 00NOS), collections
- `product.attribute.value`: size, color variants
- Custom fields: `x_gender`, `x_age_group`, `x_brand` (or stored in attributes)

Hardcoding these mappings is fragile. The Dimension Dictionary makes them dynamic and configurable.

## Data Models

### `ai.analyst.dimension`

```
_name = 'ai.analyst.dimension'
_description = 'Product Dimension Definition'
_order = 'sequence, name'

Fields:
    name                Char        required    e.g. "Gender", "Season", "Brand"
    code                Char        required    unique, e.g. "gender", "season", "brand"
    sequence            Integer     default=10
    is_active           Boolean     default=True
    company_id          Many2one    res.company

    # Source Configuration
    source_type         Selection   required
        'field'         — Direct field on product.template or product.product
        'attribute'     — product.attribute / product.attribute.value
        'tag'           — product.tag
        'category'      — product.category (categ_id hierarchy)
        'computed'       — Python expression on product fields (read-only, safe)

    # Source Details (depends on source_type)
    source_field        Char        Field name when source_type='field'
                                    e.g. "x_gender", "x_brand", "default_code"
    source_attribute_id Many2one    product.attribute
                                    When source_type='attribute'
    source_tag_prefix   Char        Tag name prefix when source_type='tag'
                                    e.g. "06" for season tags like "06AW25"
    source_category_depth Integer   How deep in category tree, default=1
    source_expression   Text        Safe expression when source_type='computed'
                                    e.g. "record.default_code[:3]"
                                    MUST be validated — allowlisted operations only

    # Synonym Mappings
    synonym_ids         One2many    ai.analyst.dimension.synonym

    # Display
    description         Text        Human-readable explanation
    example_values      Text        Comma-separated example values for LLM context
    include_in_prompt   Boolean     default=True    Include in system prompt for LLM
```

### `ai.analyst.dimension.synonym`

```
_name = 'ai.analyst.dimension.synonym'
_description = 'Dimension Value Synonym / Alias'

Fields:
    dimension_id        Many2one    ai.analyst.dimension    required
    canonical_value     Char        required    The actual value in Odoo
                                                e.g. "Women", "AW25", "Nike"
    synonym             Char        required    What users/LLM might say
                                                e.g. "ladies", "FW25", "nike inc"
    company_id          Many2one    res.company

SQL Constraint:
    unique(dimension_id, synonym, company_id)
```

### `ai.analyst.season.config`

```
_name = 'ai.analyst.season.config'
_description = 'Season Configuration'
_order = 'sequence desc'

Fields:
    name                Char        required    Display name, e.g. "Fall/Winter 2025"
    code                Char        required    Canonical code, e.g. "FW25"
    sequence            Integer     default=10  Higher = more recent
    is_active           Boolean     default=True
    company_id          Many2one    res.company

    # Tag Mappings — which product.tag records map to this season
    tag_pattern_ids     One2many    ai.analyst.season.tag.pattern

    # Date Range (optional, for time-based filtering)
    date_start          Date        When this season starts
    date_end            Date        When this season ends

    # Synonyms (user might say any of these)
    synonym_ids         One2many    links to ai.analyst.dimension.synonym
                                    where dimension_id.code = 'season'
```

### `ai.analyst.season.tag.pattern`

```
_name = 'ai.analyst.season.tag.pattern'
_description = 'Season Tag Pattern'

Fields:
    season_id           Many2one    ai.analyst.season.config    required
    tag_pattern         Char        required    Pattern to match product.tag.name
                                                e.g. "06AW25", "AW25", "FW25"
    match_type          Selection
        'exact'         — Exact match
        'prefix'        — Starts with
        'contains'      — Contains substring
        'regex'         — Regex (validated on save)
```

## Example JSON: Dimension Definitions

```json
[
  {
    "name": "Gender",
    "code": "gender",
    "source_type": "field",
    "source_field": "x_gender",
    "example_values": "Men, Women, Unisex, Kids",
    "synonyms": [
      {"canonical_value": "Women", "synonym": "ladies"},
      {"canonical_value": "Women", "synonym": "womens"},
      {"canonical_value": "Women", "synonym": "female"},
      {"canonical_value": "Men", "synonym": "mens"},
      {"canonical_value": "Men", "synonym": "male"},
      {"canonical_value": "Men", "synonym": "gents"},
      {"canonical_value": "Kids", "synonym": "children"},
      {"canonical_value": "Kids", "synonym": "boys"},
      {"canonical_value": "Kids", "synonym": "girls"}
    ]
  },
  {
    "name": "Age Group",
    "code": "age_group",
    "source_type": "field",
    "source_field": "x_age_group",
    "example_values": "Adult, Junior, Infant, Toddler",
    "synonyms": [
      {"canonical_value": "Junior", "synonym": "youth"},
      {"canonical_value": "Junior", "synonym": "teen"},
      {"canonical_value": "Infant", "synonym": "baby"}
    ]
  },
  {
    "name": "Brand",
    "code": "brand",
    "source_type": "field",
    "source_field": "x_brand",
    "example_values": "Nike, Adidas, New Balance, Puma",
    "synonyms": [
      {"canonical_value": "New Balance", "synonym": "NB"},
      {"canonical_value": "Adidas", "synonym": "adidas originals"}
    ]
  },
  {
    "name": "Category",
    "code": "category",
    "source_type": "category",
    "source_category_depth": 2,
    "example_values": "Footwear, Apparel, Accessories",
    "synonyms": [
      {"canonical_value": "Footwear", "synonym": "shoes"},
      {"canonical_value": "Footwear", "synonym": "sneakers"},
      {"canonical_value": "Footwear", "synonym": "trainers"},
      {"canonical_value": "Apparel", "synonym": "clothing"},
      {"canonical_value": "Apparel", "synonym": "clothes"}
    ]
  },
  {
    "name": "Season",
    "code": "season",
    "source_type": "tag",
    "source_tag_prefix": "06",
    "example_values": "FW25, SS25, FW24, SS24, NOS",
    "synonyms": [
      {"canonical_value": "FW25", "synonym": "AW25"},
      {"canonical_value": "FW25", "synonym": "fall winter 2025"},
      {"canonical_value": "FW25", "synonym": "autumn winter 2025"},
      {"canonical_value": "SS25", "synonym": "spring summer 2025"},
      {"canonical_value": "NOS", "synonym": "never out of stock"},
      {"canonical_value": "NOS", "synonym": "core"},
      {"canonical_value": "NOS", "synonym": "continuity"}
    ]
  },
  {
    "name": "Color",
    "code": "color",
    "source_type": "attribute",
    "source_attribute_id": "<ref to product.attribute 'Color'>",
    "example_values": "Black, White, Red, Blue, Navy",
    "synonyms": [
      {"canonical_value": "Navy", "synonym": "dark blue"},
      {"canonical_value": "Grey", "synonym": "gray"},
      {"canonical_value": "Burgundy", "synonym": "wine"},
      {"canonical_value": "Burgundy", "synonym": "maroon"}
    ]
  }
]
```

## Example JSON: Season Configuration

```json
[
  {
    "name": "Fall/Winter 2025",
    "code": "FW25",
    "date_start": "2025-07-01",
    "date_end": "2025-12-31",
    "tag_patterns": [
      {"tag_pattern": "06AW25", "match_type": "exact"},
      {"tag_pattern": "AW25",   "match_type": "exact"},
      {"tag_pattern": "FW25",   "match_type": "exact"},
      {"tag_pattern": "06FW25", "match_type": "exact"}
    ],
    "synonyms": ["AW25", "fall winter 2025", "autumn winter 2025", "fw2025"]
  },
  {
    "name": "Spring/Summer 2025",
    "code": "SS25",
    "date_start": "2025-01-01",
    "date_end": "2025-06-30",
    "tag_patterns": [
      {"tag_pattern": "06SS25", "match_type": "exact"},
      {"tag_pattern": "SS25",   "match_type": "exact"}
    ],
    "synonyms": ["spring summer 2025", "ss2025"]
  },
  {
    "name": "Never Out of Stock",
    "code": "NOS",
    "date_start": null,
    "date_end": null,
    "tag_patterns": [
      {"tag_pattern": "00NOS", "match_type": "exact"},
      {"tag_pattern": "NOS",   "match_type": "exact"}
    ],
    "synonyms": ["never out of stock", "core", "continuity", "carryover"]
  }
]
```

## How Dimensions Flow Into Tool Calls

### Step 1: System Prompt Injection

The gateway builds a dimension context block and injects it into the system prompt:

```python
def _build_dimension_context(self, company_id):
    dimensions = self.env['ai.analyst.dimension'].search([
        ('is_active', '=', True),
        ('include_in_prompt', '=', True),
        ('company_id', 'in', [company_id, False]),
    ])
    lines = ["## Available Product Dimensions\n"]
    for dim in dimensions:
        synonyms = dim.synonym_ids.mapped(
            lambda s: f"'{s.synonym}' → '{s.canonical_value}'"
        )
        lines.append(f"- **{dim.name}** (code: `{dim.code}`)")
        lines.append(f"  Source: {dim.source_type}")
        lines.append(f"  Examples: {dim.example_values}")
        if synonyms:
            lines.append(f"  Aliases: {', '.join(synonyms[:10])}")
    return "\n".join(lines)
```

### Step 2: Tool Parameter Schema

The `get_sales_by_dimension` tool accepts dimension parameters dynamically:

```json
{
  "name": "get_sales_by_dimension",
  "parameters": {
    "type": "object",
    "properties": {
      "date_from": {"type": "string", "format": "date"},
      "date_to": {"type": "string", "format": "date"},
      "group_by": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Dimension codes to group by, e.g. ['gender', 'brand']"
      },
      "filters": {
        "type": "object",
        "description": "Dimension code → value(s) filter, e.g. {\"gender\": \"Women\", \"season\": \"FW25\"}"
      },
      "metric": {
        "type": "string",
        "enum": ["revenue", "quantity", "margin", "order_count"],
        "default": "revenue"
      },
      "limit": {"type": "integer", "default": 50, "maximum": 500}
    },
    "required": ["date_from", "date_to"]
  }
}
```

### Step 3: Synonym Resolution in Tool Execution

```python
def _resolve_dimension_filters(self, env, filters, company_id):
    """Resolve user-facing values to canonical Odoo values using synonyms."""
    resolved = {}
    for dim_code, raw_value in filters.items():
        dimension = env['ai.analyst.dimension'].search([
            ('code', '=', dim_code),
            ('company_id', 'in', [company_id, False]),
        ], limit=1)
        if not dimension:
            continue

        values = [raw_value] if isinstance(raw_value, str) else raw_value
        canonical_values = []
        for val in values:
            # Check synonym table
            synonym = env['ai.analyst.dimension.synonym'].search([
                ('dimension_id', '=', dimension.id),
                ('synonym', '=ilike', val),
            ], limit=1)
            canonical_values.append(synonym.canonical_value if synonym else val)

        resolved[dim_code] = canonical_values
    return resolved
```

### Step 4: Domain Building

```python
def _build_dimension_domain(self, env, dimension, values, company_id):
    """Convert a dimension + values into an Odoo domain."""
    if dimension.source_type == 'field':
        return [(dimension.source_field, 'in', values)]

    elif dimension.source_type == 'attribute':
        attr_values = env['product.attribute.value'].search([
            ('attribute_id', '=', dimension.source_attribute_id.id),
            ('name', 'in', values),
        ])
        tmpl_ids = env['product.template.attribute.value'].search([
            ('product_attribute_value_id', 'in', attr_values.ids),
        ]).mapped('product_tmpl_id').ids
        return [('product_tmpl_id', 'in', tmpl_ids)]

    elif dimension.source_type == 'tag':
        # Resolve season config → tag patterns → product.tag records
        tag_names = self._resolve_tag_names(env, dimension, values, company_id)
        tags = env['product.tag'].search([('name', 'in', tag_names)])
        tmpl_ids = env['product.template'].search([
            ('tag_ids', 'in', tags.ids)
        ]).ids
        return [('product_tmpl_id', 'in', tmpl_ids)]

    elif dimension.source_type == 'category':
        categories = env['product.category'].search([
            ('name', 'in', values),
        ])
        # Include children
        all_cat_ids = categories.ids
        for cat in categories:
            all_cat_ids += env['product.category'].search([
                ('parent_id', 'child_of', cat.id)
            ]).ids
        return [('categ_id', 'in', list(set(all_cat_ids)))]
```

## Indexing and Denormalization Plan

### Database Indexes (Phase 2)

```sql
-- product.tag: fast lookup by name
CREATE INDEX IF NOT EXISTS idx_product_tag_name
    ON product_tag (name);

-- product.template: fast filtering by custom dimension fields
CREATE INDEX IF NOT EXISTS idx_product_template_gender
    ON product_template (x_gender) WHERE x_gender IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_product_template_brand
    ON product_template (x_brand) WHERE x_brand IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_product_template_age_group
    ON product_template (x_age_group) WHERE x_age_group IS NOT NULL;

-- sale.order.line: date + product for fast time-series
CREATE INDEX IF NOT EXISTS idx_sol_date_product
    ON sale_order_line (create_date, product_id)
    WHERE state IN ('sale', 'done');

-- Dimension synonym: fast lookup
CREATE INDEX IF NOT EXISTS idx_dim_synonym_lookup
    ON ai_analyst_dimension_synonym (dimension_id, synonym);
```

### Denormalization Strategy (Phase 3 — Pre-aggregation)

For high-frequency queries, pre-aggregate into summary tables. See `10_performance_scaling.md` for details. Key concept:

```
ai.analyst.product.dimension.cache
    product_tmpl_id     Many2one    product.template
    gender              Char        Denormalized from source
    age_group           Char
    brand               Char
    category_l1         Char        Top-level category
    category_l2         Char        Second-level category
    season_codes        Char        Comma-separated season codes
    color_values        Char        Comma-separated colors
    last_synced_at      Datetime    For incremental refresh
```

This cache table is populated by a scheduled action and used by dimension-aware tools for fast GROUP BY queries without JOINs.

## Validation and Safety

1. **No arbitrary field access** — `source_field` values are validated against the model's `_fields` on save.
2. **No raw SQL** — All domain building uses Odoo ORM `search()` and `read_group()`.
3. **Expression safety** — `source_expression` (for `computed` type) is parsed via AST and restricted to attribute access only. No function calls, no imports, no builtins.
4. **Synonym case-insensitivity** — All synonym lookups use `=ilike` for case-insensitive matching.
5. **Tag pattern validation** — Regex patterns in `ai.analyst.season.tag.pattern` are validated on save with `re.compile()` in a try/except.
