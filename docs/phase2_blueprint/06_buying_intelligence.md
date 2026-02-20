# 06 — Buying Intelligence

## Overview

Buying Intelligence tools surface actionable insights for merchandisers and buyers:
- **Winners**: High-velocity, high-sell-through items to reorder
- **Dead Dogs**: Zero/low-velocity items consuming capital and warehouse space
- **Reorder Suggestions**: Data-driven reorder proposals with explainability
- **Stock Coverage**: How many weeks/days of stock remain at current velocity

All results are explainable (formulas shown), exportable (CSV always), and read-only. Any action (create PO) flows through the Safe Actions Framework (doc 07).

## Core Formulas

### Sales Velocity

```
velocity_daily = units_sold / selling_days

Where:
    units_sold   = SUM(sale.order.line.product_uom_qty)
                   WHERE state IN ('sale', 'done')
                   AND date_order BETWEEN [date_from, date_to]
    selling_days = business_days(date_from, date_to)
                   OR calendar_days if simpler

Variants:
    velocity_weekly  = velocity_daily * 7
    velocity_monthly = velocity_daily * 30
```

### Sell-Through Rate

```
sell_through_pct = units_sold / (units_sold + current_stock) * 100

Where:
    units_sold    = total units sold in the analysis period
    current_stock = SUM(stock.quant.quantity)
                    WHERE location_id.usage = 'internal'

Notes:
    - Sell-through > 80% = strong performer
    - Sell-through < 20% = potential dead stock
    - NOS items have different benchmarks (expected lower sell-through)
```

### Stock Coverage

```
coverage_days = current_stock / velocity_daily

coverage_weeks = coverage_days / 7

Where:
    current_stock = available on-hand quantity
    velocity_daily = as above

Interpretation:
    coverage < 14 days  → urgent reorder signal
    coverage 14-42 days → healthy
    coverage > 90 days  → overstocked (unless NOS/seasonal pre-buy)
```

### Dead Stock Score

```
dead_stock_score = w1 * age_score + w2 * velocity_score + w3 * coverage_score

Where:
    age_score      = min(days_since_last_sale / 90, 1.0)      # 0 = sold today, 1 = 90+ days ago
    velocity_score = max(1.0 - (velocity_daily / median_velocity), 0)  # 0 = at median, 1 = zero sales
    coverage_score = min(coverage_days / 180, 1.0)            # 0 = no stock, 1 = 180+ days of stock

    Default weights: w1=0.35, w2=0.40, w3=0.25

    dead_stock_score ∈ [0, 1]
    Score > 0.7 = "dead dog" candidate
    Score > 0.85 = critical dead stock

Configurable:
    - Weights (w1, w2, w3) stored in ir.config_parameter
    - Threshold for "dead" classification: default 0.7
    - Exclude NOS items by default (configurable)
```

### Reorder Point

```
reorder_quantity = (target_coverage_days * velocity_daily) - current_stock - incoming_stock

Where:
    target_coverage_days = configurable per category/brand (default: 42 days = 6 weeks)
    velocity_daily       = as above, using configurable lookback period (default: 30 days)
    current_stock        = on-hand in internal locations
    incoming_stock       = SUM(stock.move.product_uom_qty)
                           WHERE state IN ('assigned', 'confirmed', 'waiting')
                           AND location_dest_id.usage = 'internal'

    If reorder_quantity <= 0: no reorder needed
    Round up to supplier MOQ if known (from product.supplierinfo)
```

## Tool Specifications

### `get_buying_velocity`

```
Tool Name:      get_buying_velocity
Workspace:      buying
Required Groups: group_ai_user, purchase.group_purchase_user
Max Rows:       500

Parameters:
    date_from       date        required
    date_to         date        required
    group_by        string[]    optional    Dimension codes: ["brand", "category", "gender"]
    filters         object      optional    Dimension filters: {"season": "FW25"}
    metric          enum        default="velocity_daily"
                                ["velocity_daily", "velocity_weekly", "units_sold"]
    sort_by         enum        default="velocity_daily_desc"
    min_velocity    float       optional    Filter out items below threshold
    limit           integer     default=50

Returns:
    table:
        product_name, default_code, brand, category, gender, season,
        units_sold, selling_days, velocity_daily, velocity_weekly,
        current_stock, coverage_days
    kpis:
        total_units_sold, avg_velocity, median_velocity,
        products_analyzed, period_days
    chart:
        type: bar
        Top 20 by velocity
    meta:
        formula: "velocity_daily = units_sold / selling_days"
        period: "{date_from} to {date_to}"
```

### `get_dead_stock`

```
Tool Name:      get_dead_stock
Workspace:      buying
Required Groups: group_ai_user, purchase.group_purchase_user
Max Rows:       500

Parameters:
    lookback_days   integer     default=90      Sales lookback for velocity
    min_stock_qty   float       default=1       Minimum stock to consider
    threshold       float       default=0.7     Dead stock score threshold
    exclude_nos     boolean     default=True    Exclude NOS items
    filters         object      optional        Dimension filters
    group_by        string[]    optional        Dimension codes
    sort_by         enum        default="dead_stock_score_desc"
    limit           integer     default=100

Returns:
    table:
        product_name, default_code, brand, category, season,
        current_stock, stock_value, units_sold_period,
        days_since_last_sale, velocity_daily, coverage_days,
        dead_stock_score, age_score, velocity_score, coverage_score,
        recommendation (markdown string)
    kpis:
        dead_stock_items, dead_stock_value, pct_of_total_inventory,
        avg_days_since_last_sale
    chart:
        type: scatter
        x: days_since_last_sale, y: current_stock, color: dead_stock_score
    meta:
        formula: "dead_stock_score = 0.35*age + 0.40*velocity + 0.25*coverage"
        threshold_used, lookback_days, nos_excluded
```

### `get_stock_coverage`

```
Tool Name:      get_stock_coverage
Workspace:      buying
Required Groups: group_ai_user, purchase.group_purchase_user
Max Rows:       500

Parameters:
    velocity_lookback_days  integer     default=30
    filters                 object      optional
    group_by                string[]    optional
    coverage_alert_days     integer     default=14  Flag items below this
    sort_by                 enum        default="coverage_days_asc"
    include_incoming        boolean     default=True    Include incoming POs
    limit                   integer     default=100

Returns:
    table:
        product_name, default_code, brand, category,
        current_stock, incoming_stock, total_available,
        velocity_daily, coverage_days, coverage_weeks,
        alert (boolean: coverage < threshold),
        last_sale_date, last_po_date
    kpis:
        items_below_threshold, avg_coverage_weeks,
        total_stock_value_at_risk
    chart:
        type: horizontal_bar
        Coverage weeks by product (flagged items highlighted)
    meta:
        formula: "coverage_days = (on_hand + incoming) / velocity_daily"
        velocity_lookback_days, coverage_alert_threshold
```

### `get_reorder_suggestions`

```
Tool Name:      get_reorder_suggestions
Workspace:      buying
Required Groups: group_ai_user, purchase.group_purchase_user
Max Rows:       200

Parameters:
    velocity_lookback_days  integer     default=30
    target_coverage_days    integer     default=42      6 weeks default
    min_velocity            float       default=0.1     Skip zero-velocity items
    filters                 object      optional
    group_by                string[]    optional        Aggregate suggestions
    respect_moq             boolean     default=True    Round to supplier MOQ
    limit                   integer     default=50

Returns:
    table:
        product_name, default_code, brand, category, supplier,
        current_stock, incoming_stock, velocity_daily,
        coverage_days_current, target_coverage_days,
        suggested_qty, suggested_qty_after_moq, moq,
        estimated_cost (unit_cost * qty),
        confidence (high/medium/low based on velocity consistency),
        reasoning (markdown explanation)
    kpis:
        total_items_to_reorder, total_estimated_cost,
        avg_target_coverage, items_with_moq_adjustment
    chart:
        type: bar
        Suggested quantities by brand/category
    meta:
        formula: "reorder_qty = (target_days * velocity) - on_hand - incoming"
        target_coverage_days, velocity_lookback_days
    actions:
        - type: 'create_proposal'
          label: 'Create Reorder Proposal'
          proposal_type: 'purchase_order'
          data_key: 'table'  # References the suggestion table
```

### `get_season_performance`

```
Tool Name:      get_season_performance
Workspace:      sales, buying
Required Groups: group_ai_user
Max Rows:       500

Parameters:
    season_code     string      required    e.g. "FW25" (resolved via season config)
    compare_season  string      optional    e.g. "FW24" for comparison
    group_by        string[]    optional    ["brand", "category", "gender"]
    metric          enum        default="revenue"
                                ["revenue", "quantity", "margin", "sell_through"]
    limit           integer     default=50

Returns:
    table:
        dimension_value, revenue, quantity, margin, sell_through_pct,
        current_stock, coverage_weeks,
        compare_revenue (if compare_season), compare_quantity,
        delta_pct (vs comparison season)
    kpis:
        total_revenue, total_units, avg_sell_through,
        season_label, compare_season_label
    chart:
        type: grouped_bar
        Current vs previous season by dimension
    meta:
        season_resolved_tags: ["06AW25", "AW25", ...],
        compare_season_resolved_tags: ["06AW24", ...],
        formula: "sell_through = sold / (sold + stock) * 100"
```

## Explainability

Every buying intelligence tool MUST include:

1. **`meta.formula`** — The mathematical formula used, in plain text
2. **`table.reasoning`** or **`table.recommendation`** — Per-row plain English explanation
3. **`meta.parameters_used`** — Echo back the exact parameters that produced the result
4. **`table.confidence`** — Where applicable, a confidence indicator (high/medium/low)

Example per-row reasoning:

```json
{
  "product_name": "Nike Air Max 90 Black",
  "suggested_qty": 120,
  "reasoning": "Selling 4.2 units/day over last 30 days. Current stock (28) + incoming (0) covers only 6.7 days. Target is 42 days. Suggested 120 units (rounded to MOQ of 24).",
  "confidence": "high"
}
```

## Data Sources and ORM Patterns

All tools use `read_group()` for aggregation and `search_read()` for detail, never raw SQL:

```python
# Velocity calculation via read_group
velocity_data = env['sale.order.line'].with_user(user).read_group(
    domain=[
        ('order_id.state', 'in', ['sale', 'done']),
        ('order_id.date_order', '>=', date_from),
        ('order_id.date_order', '<=', date_to),
        ('product_id', 'in', product_ids),
    ],
    fields=['product_id', 'product_uom_qty:sum'],
    groupby=['product_id'],
    orderby='product_uom_qty desc',
    limit=limit,
)

# Stock levels via read_group
stock_data = env['stock.quant'].with_user(user).read_group(
    domain=[
        ('location_id.usage', '=', 'internal'),
        ('product_id', 'in', product_ids),
    ],
    fields=['product_id', 'quantity:sum'],
    groupby=['product_id'],
)

# Incoming stock via read_group
incoming_data = env['stock.move'].with_user(user).read_group(
    domain=[
        ('state', 'in', ['assigned', 'confirmed', 'waiting']),
        ('location_dest_id.usage', '=', 'internal'),
        ('product_id', 'in', product_ids),
    ],
    fields=['product_id', 'product_uom_qty:sum'],
    groupby=['product_id'],
)
```

## Configurable Parameters (ir.config_parameter)

| Key | Default | Description |
|---|---|---|
| `ai_analyst.dead_stock_weight_age` | 0.35 | Weight for age score |
| `ai_analyst.dead_stock_weight_velocity` | 0.40 | Weight for velocity score |
| `ai_analyst.dead_stock_weight_coverage` | 0.25 | Weight for coverage score |
| `ai_analyst.dead_stock_threshold` | 0.70 | Score above = dead stock |
| `ai_analyst.default_target_coverage_days` | 42 | Default reorder target |
| `ai_analyst.default_velocity_lookback_days` | 30 | Default lookback |
| `ai_analyst.reorder_confidence_min_datapoints` | 7 | Min selling days for "high" confidence |
