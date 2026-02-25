# Schema-Aware Query Planner - Design Blueprint
**Version:** 1.1 (Updated with color correction)  
**Date:** 2026-02-25  
**Purpose:** Design a field-aware query planning system for AI Analyst  

---

## IMPORTANT CORRECTIONS (v1.1)

### Color Field Clarification
**Previous misunderstanding:** `x_studio_color_reference = "3"` means "red"
**CORRECT:** `x_studio_color_reference` is just an **index** (1st color, 2nd color, 3rd color) within a product style. It has NO global meaning.

**Implication:**
- Style JC1234: color 1 = Red, color 2 = Blue, color 3 = Black
- Style JC5678: color 1 = Blue, color 2 = Green, color 3 = Red
- "Color 3" means different colors for different styles!

**Solution:** For color searches, use:
1. **Product name search** - `name ILIKE '%red%'`
2. **Attribute value search** - Find `product.attribute.value` with name containing color
3. **Style-specific context** - If user mentions style + color, lookup that style's color names

### Current Problem
The AI Analyst uses a hybrid approach:
1. **Intent classification** (regex-based) → routes to universal_query or specialized_tool
2. **Universal query** uses a planner that doesn't understand field semantics
3. **Result:** Simple questions like "FW25 products" fail because the system doesn't know:
   - Season is stored as `x_product_tags` with values like "19FW25"
   - User "FW25" means `LIKE '%FW25%'`
   - Color "red" maps to `x_studio_color_reference = '3'`

### Proposed Solution
Build a **Schema-Aware Query Planner** that:
- Loads Knowledge Base (business context) + Odoo metadata (schema)
- Maintains a Field Relevance Graph (which fields matter for which questions)
- Uses Query Pattern Templates for common business questions
- Performs Semantic Value Translation (user language → database values)
- Generates proper query plans with correct joins and filters

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER QUESTION                                │
│              "Show me FW25 red products"                        │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│              SCHEMA-AWARE QUERY PLANNER                         │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   Step 1:    │  │   Step 2:    │  │      Step 3:         │  │
│  │   PARSE      │  │    MATCH     │  │   BUILD PLAN         │  │
│  │              │  │   PATTERN    │  │                      │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
│         │                  │                     │              │
│  Extract entities      Find template        Generate ORM       │
│  - season: FW25        - product_query      - model: product   │
│  - color: red          - filters: [season,  - domain: [...]    │
│  - object: products      color]             - joins: [...]     │
└─────────┬──────────────────┬────────────────────┬──────────────┘
          │                  │                    │
          ▼                  ▼                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                     KNOWLEDGE GRAPH                             │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ Field       │  │  Pattern    │  │   Semantic              │ │
│  │ Relevance   │  │  Templates  │  │   Mappings              │ │
│  │ Graph       │  │             │  │                         │ │
│  │             │  │             │  │                         │ │
│  │ Which       │  │ Pre-built   │  │ User Value → DB Value   │ │
│  │ fields for  │  │ query       │  │                         │ │
│  │ which       │  │ structures  │  │ "red" → "3"             │ │
│  │ question    │  │ for common  │  │ "FW25" → "%FW25%"       │ │
│  │ types       │  │ scenarios   │  │ "online" → origin       │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Core Components

### 3.1 Knowledge Base Loader (Already Exists)
**Purpose:** Load and normalize the Knowledge Base document

**Input:** `JuniorCouture_Odoo_KnowledgeBase_merged_v1.json`
**Output:** Structured field metadata with business context

**Structure:**
```json
{
  "fields": {
    "product.template.x_studio_many2many_field_IXz60": {
      "label": "Product Tags (Season)",
      "type": "many2many",
      "relation": "x_product_tags",
      "business_meaning": "Season(s) the product belongs to",
      "search_strategy": "partial_match",
      "examples": ["19FW25", "20SS26"]
    }
  }
}
```

### 3.2 Schema Registry (New)
**Purpose:** Load Odoo metadata (ir.model, ir.model.fields)

**Data Source:**
- `ir.model` - All models
- `ir.model.fields` - All fields with types, relations
- `ir.model.relation` - Many2many relations

**Output:** Complete schema graph
```json
{
  "model": "product.template",
  "fields": {
    "id": {"type": "integer", "required": true},
    "name": {"type": "char", "required": true, "translate": true},
    "list_price": {"type": "float"},
    "categ_id": {"type": "many2one", "relation": "product.category"},
    "product_variant_ids": {"type": "one2many", "relation": "product.product", "inverse": "product_tmpl_id"}
  },
  "relations": {
    "product.category": {"field": "categ_id", "type": "many2one"},
    "product.product": {"field": "product_variant_ids", "type": "one2many"}
  }
}
```

### 3.3 Field Relevance Graph (New)
**Purpose:** Map question types to relevant fields

**Structure:**
```json
{
  "question_types": {
    "product_catalog": {
      "primary_model": "product.template",
      "relevant_fields": [
        {"field": "name", "weight": 1.0, "search_type": "text"},
        {"field": "x_studio_many2many_field_IXz60", "weight": 0.9, "search_type": "season"},
        {"field": "x_studio_color_reference", "weight": 0.8, "search_type": "color"},
        {"field": "list_price", "weight": 0.7, "search_type": "price"},
        {"field": "categ_id", "weight": 0.5, "search_type": "category"}
      ]
    },
    "sales_analysis": {
      "primary_model": "sale.order",
      "relevant_fields": [
        {"field": "amount_total", "weight": 1.0, "aggregation": "sum"},
        {"field": "date_order", "weight": 0.9, "search_type": "date"},
        {"field": "state", "weight": 0.8, "filter": ["sale", "done"]},
        {"field": "partner_id", "weight": 0.6, "search_type": "customer"}
      ]
    }
  }
}
```

### 3.4 Query Pattern Templates (New)
**Purpose:** Pre-defined query structures for common business questions

**Patterns:**
```json
{
  "patterns": [
    {
      "name": "product_by_season",
      "description": "Find products matching a season code",
      "trigger_keywords": ["season", "FW", "SS", "spring", "summer", "fall", "winter"],
      "primary_model": "product.template",
      "query_structure": {
        "base_model": "product.template",
        "domain": [
          ["active", "=", true]
        ],
        "joins": [
          {
            "model": "x_product_tags",
            "relation_field": "x_studio_many2many_field_IXz60",
            "domain": [["name", "ilike", "{{season_code}}"]]
          }
        ]
      }
    },
    {
      "name": "sales_by_period",
      "description": "Sales totals grouped by time period",
      "trigger_keywords": ["sales", "revenue", "orders", "total"],
      "primary_model": "sale.order",
      "query_structure": {
        "base_model": "sale.order",
        "domain": [
          ["state", "in", ["sale", "done"]]
        ],
        "aggregation": {
          "field": "amount_total",
          "operator": "sum"
        },
        "group_by": ["date_order:month"]
      }
    },
    {
      "name": "inventory_levels",
      "description": "Current stock on hand",
      "trigger_keywords": ["stock", "inventory", "on hand", "available"],
      "primary_model": "stock.quant",
      "query_structure": {
        "base_model": "stock.quant",
        "domain": [
          ["location_id.usage", "=", "internal"]
        ],
        "aggregation": {
          "field": "quantity",
          "operator": "sum",
          "group_by": ["product_id"]
        }
      }
    }
  ]
}
```

### 3.5 Semantic Value Translator (New)
**Purpose:** Convert user natural language to database values

**Mappings:**
```json
{
  "translators": {
    "season": {
      "type": "pattern",
      "rules": [
        {"pattern": "^(FW|SS)(\\d{2})$", "transform": "%{{match}}%"},
        {"pattern": "fall\\s*winter\\s*(\\d{2,4})", "transform": "%FW{{year_short}}%"},
        {"pattern": "spring\\s*summer\\s*(\\d{2,4})", "transform": "%SS{{year_short}}%"}
      ]
    },
    "color": {
      "type": "multi_strategy",
      "note": "x_studio_color_reference is NOT a global color code. It's just an index (1st color, 2nd color, etc.) per product style.",
      "strategies": [
        {
          "name": "product_name_search",
          "description": "Search product name for color mentions",
          "implementation": "product.template.search([('name', 'ilike', '%{{color}}%')])"
        },
        {
          "name": "color_attribute_search", 
          "description": "Search product.attribute.value for color names, then find products with those attribute values",
          "implementation": "Search product.attribute.value → find matching product.template via attribute lines"
        },
        {
          "name": "style_specific_context",
          "description": "If user mentions specific style + color, lookup color_reference from that style's color names",
          "implementation": "For style X, find which color_reference has name matching '{{color}}'"
        }
      ],
      "examples": [
        {"user_says": "red dress", "strategy": "product_name_search", "query": "('name', 'ilike', '%red%')"},
        {"user_says": "color 3 of style JC1234", "strategy": "use color_reference directly", "query": "('x_studio_style_reference', '=', 'JC1234'), ('x_studio_color_reference', '=', '3')"}
      ]
    },
    "order_state": {
      "type": "synonym",
      "mappings": {
        "confirmed": "sale",
        "done": "done",
        "draft": "draft",
        "cancelled": "cancel"
      }
    }
  }
}
```

---

## 4. Query Planning Algorithm

### Step 1: Entity Extraction
Parse the user question to identify:
- **Target entities:** products, orders, customers, inventory
- **Attributes:** season=FW25, color=red, date=last month
- **Operations:** count, sum, list, compare
- **Filters:** active only, confirmed orders

**Example:**
```
"Show me FW25 red products"
→ entities: {
    target: "products",
    season: "FW25",
    color: "red",
    operation: "list"
  }
```

### Step 2: Pattern Matching
Match extracted entities to query patterns:
```
Has "season" → product_by_season pattern
Has "color" → add color filter
Target "products" → primary_model: product.template
```

### Step 3: Semantic Translation
Convert user values to database values:
```
"FW25" → "%FW25%" (partial match)
"red" → "3" (color code)
```

### Step 4: Join Resolution
Determine required joins based on filters:
```
Filter on season (x_product_tags) → join x_product_tags
Filter on category (product.category) → join product.category
```

### Step 5: Query Plan Generation
Generate executable query plan:
```json
{
  "steps": [
    {
      "model": "product.template",
      "method": "search_read",
      "domain": [
        ["active", "=", true],
        ["x_studio_many2many_field_IXz60.name", "ilike", "%FW25%"],
        ["x_studio_color_reference", "=", "3"]
      ],
      "fields": ["name", "list_price", "default_code"],
      "limit": 100
    }
  ]
}
```

---

## 5. Implementation Phases

### Phase 1: Foundation (Week 1)
1. Build Schema Registry loader (read ir.model.fields)
2. Integrate with existing Knowledge Base
3. Create Field Relevance Graph structure
4. Build basic query plan generator

### Phase 2: Pattern Library (Week 2)
1. Define 10-15 core query patterns:
   - Product by season/color
   - Sales by period/channel
   - Inventory levels
   - Customer analysis
2. Build Pattern Matcher
3. Implement pattern-based routing

### Phase 3: Semantic Translation (Week 3)
1. Build Semantic Value Translator
2. Add season pattern recognition
3. Add color code mappings
4. Add state/value synonyms
5. Make it extensible (config file)

### Phase 4: Integration (Week 4)
1. Replace existing `_run_universal_query()` logic
2. Add fallback to specialized tools
3. Build feedback loop (failed queries → pattern improvement)
4. Add query result caching

---

## 6. Data Flow Example

### User Question: "How many FW25 red products do we have?"

**Step 1: Entity Extraction**
```json
{
  "operation": "count",
  "target": "products",
  "filters": {
    "season": "FW25",
    "color": "red"
  }
}
```

**Step 2: Pattern Match**
- Matches `product_by_season` pattern
- Primary model: `product.template`
- Operation: `count`

**Step 3: Semantic Translation**
- "FW25" → search pattern: `%FW25%`
- "red" → color code: `3`
- "products" → model: `product.template`

**Step 4: Join Resolution**
- Season filter requires join to `x_product_tags` via `x_studio_many2many_field_IXz60`
- Color filter is direct field on `product.template`

**Step 5: Query Plan**
```json
{
  "steps": [
    {
      "model": "product.template",
      "method": "search_count",
      "domain": [
        ["active", "=", true],
        ["x_studio_color_reference", "=", "3"],
        ["x_studio_many2many_field_IXz60.name", "ilike", "%FW25%"]
      ]
    }
  ]
}
```

**Step 6: Execution**
```python
count = env['product.template'].search_count([
    ('active', '=', True),
    ('x_studio_color_reference', '=', '3'),
    ('x_studio_many2many_field_IXz60.name', 'ilike', '%FW25%')
])
return f"You have {count} FW25 red products"
```

---

## 7. Key Design Decisions

### 7.1 Pattern-Based vs AI-Generated
**Decision:** Use pattern-based for common queries, AI-generated for edge cases
**Rationale:** Patterns are reliable and fast. AI as fallback for novel queries.

### 7.2 Hardcoded vs Configurable Mappings
**Decision:** Semantic mappings in JSON config files
**Rationale:** Easy to update without code changes. Business users can maintain mappings.

### 7.3 Schema Discovery vs Manual Definition
**Decision:** Auto-discover schema from Odoo, manually enhance with business context
**Rationale:** Schema changes automatically. Business meaning added via KB.

### 7.4 Single Model vs Multi-Model Queries
**Decision:** Support multi-model with explicit join resolution
**Rationale:** Real questions span models (products + sales + inventory).

---

## 8. Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| "FW25 products" queries succeed | 0% | 95% |
| Color filter queries succeed | 0% | 95% |
| Query plan generation time | N/A | <100ms |
| Fallback to specialized tools | High | <20% |
| User satisfaction (test set) | Low | >80% |

---

## 9. Files to Create

1. `models/schema_registry.py` - Schema loader
2. `models/field_relevance_graph.py` - Field mapping
3. `models/query_pattern_library.py` - Pattern templates
4. `models/semantic_translator.py` - Value translation
5. `models/schema_aware_planner.py` - Main planner
6. `data/query_patterns.json` - Pattern definitions
7. `data/semantic_mappings.json` - Value mappings

---

## 10. Integration with Existing System

### Current Flow:
```
User → _classify_intent() → universal_query OR specialized_tool
```

### New Flow:
```
User → _classify_intent() → schema_aware_planner() → pattern_match()
                                                ↓
                                          semantic_translate()
                                                ↓
                                          build_query_plan()
                                                ↓
                                          execute() → Result
```

### Fallback Strategy:
1. Try pattern-based planning first
2. If no pattern matches → use AI to generate plan
3. If AI plan fails → fallback to specialized tools
4. Log all failures for pattern improvement

---

**End of Blueprint**

**Next Steps:**
1. Review and approve design
2. Prioritize phases
3. Begin Phase 1 implementation
