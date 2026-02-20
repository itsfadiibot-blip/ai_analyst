# 10 — Performance and Scaling

## Current Bottlenecks (Phase 1)

| Bottleneck | Impact | Root Cause |
|---|---|---|
| Line-level queries on sale.order.line | Slow for large date ranges | Full table scan, no covering indexes |
| Dashboard 12-widget refresh | Connection pool exhaustion | Parallel tool calls per widget |
| stock.quant aggregation | Slow for many products | No partial indexes on internal locations |
| Dimension JOINs (tags, attributes) | Multiple round-trips | No denormalization |
| Repeated identical queries | Wasted LLM tokens + DB load | No result caching |

## Strategy Summary

```
Phase 2: Indexes + Query Caching + read_group optimization
Phase 3: Pre-aggregation tables + Dimension cache
Phase 4: Read replicas + Materialized views (if needed)
```

## 1. Database Indexes

### Priority 1: Sale Order Line (most queried)

```sql
-- Covering index for time-series sales queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sol_confirmed_date_product
    ON sale_order_line (create_date, product_id, product_uom_qty, price_subtotal)
    WHERE state IN ('sale', 'done');

-- For grouping by product template (dimension queries)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sol_product_tmpl
    ON sale_order_line (product_tmpl_id, create_date)
    WHERE state IN ('sale', 'done');

-- For salesperson grouping
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sol_salesperson
    ON sale_order_line (salesman_id, create_date)
    WHERE state IN ('sale', 'done');
```

### Priority 2: POS Order Line

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pos_ol_date_product
    ON pos_order_line (create_date, product_id, qty, price_subtotal_incl);

-- POS order: session + date for store-level queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pos_order_session_date
    ON pos_order (session_id, date_order)
    WHERE state IN ('paid', 'done', 'invoiced');
```

### Priority 3: Stock

```sql
-- Stock quant: internal locations only (most common filter)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_stock_quant_internal
    ON stock_quant (product_id, quantity)
    WHERE location_id IN (
        SELECT id FROM stock_location WHERE usage = 'internal'
    );

-- Stock move: incoming stock for coverage calculations
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_stock_move_incoming
    ON stock_move (product_id, product_uom_qty)
    WHERE state IN ('assigned', 'confirmed', 'waiting')
    AND location_dest_id IN (
        SELECT id FROM stock_location WHERE usage = 'internal'
    );
```

### Priority 4: Product Dimensions

```sql
-- Product template custom fields
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pt_gender ON product_template (x_gender) WHERE x_gender IS NOT NULL;
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pt_brand ON product_template (x_brand) WHERE x_brand IS NOT NULL;
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pt_age_group ON product_template (x_age_group) WHERE x_age_group IS NOT NULL;

-- Product tag names (for season resolution)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_product_tag_name ON product_tag (name);

-- Tag-to-template relation
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_product_tag_rel
    ON product_tag_product_template_rel (product_template_id, product_tag_id);
```

### Index Deployment

Indexes are created via a post-init hook or a migration script, using `CONCURRENTLY` to avoid locking production tables:

```python
def post_init_hook(env):
    """Create performance indexes without locking."""
    indexes = [
        # (name, table, definition)
        ("idx_sol_confirmed_date_product",
         "sale_order_line",
         "(create_date, product_id, product_uom_qty, price_subtotal) "
         "WHERE state IN ('sale', 'done')"),
        # ... etc
    ]
    for name, table, definition in indexes:
        try:
            env.cr.execute(f"""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS {name}
                ON {table} {definition}
            """)
        except Exception:
            _logger.warning("Could not create index %s (may already exist)", name)
```

## 2. read_group Optimization

### Current Pattern (Good)

Phase 1 tools already use `read_group()` which translates to SQL `GROUP BY`. This is efficient.

### Optimization: Avoid search() + mapped()

```python
# BAD (N+1 queries):
orders = env['sale.order'].search(domain)
for order in orders:
    total += sum(order.order_line.mapped('price_subtotal'))

# GOOD (single query):
data = env['sale.order.line'].read_group(
    domain=line_domain,
    fields=['order_id', 'price_subtotal:sum'],
    groupby=['order_id'],
)
```

### Optimization: Lazy field selection

```python
# Only request fields you need in read_group
data = env['sale.order.line'].read_group(
    domain=domain,
    fields=['product_id', 'product_uom_qty:sum', 'price_subtotal:sum'],
    groupby=['product_id'],
    orderby='price_subtotal desc',
    limit=limit,
    lazy=True,  # Don't auto-expand groupby
)
```

## 3. Query Result Caching

### Cache Model

```
_name = 'ai.analyst.cache.entry'
_description = 'Query Result Cache'

Fields:
    cache_key           Char        required    indexed, unique
    tool_name           Char        required
    params_hash         Char        required    SHA256 of sorted params JSON
    user_id             Many2one    res.users
    company_id          Many2one    res.company

    result_json         Text        Compressed (gzip) JSON result
    result_size_bytes   Integer
    row_count           Integer

    created_at          Datetime    default=now
    expires_at          Datetime    required
    hit_count           Integer     default=0
    last_hit_at         Datetime
```

### Cache Key Strategy

```python
def _make_cache_key(self, tool_name, params, user, company_id):
    """Generate deterministic cache key."""
    # Normalize params: sort keys, stringify values
    normalized = json.dumps(params, sort_keys=True, default=str)
    params_hash = hashlib.sha256(normalized.encode()).hexdigest()[:16]

    # Key includes user for ACL-scoped results
    return f"{tool_name}:{company_id}:{user.id}:{params_hash}"
```

### Cache TTL by Tool Type

| Tool Category | TTL | Rationale |
|---|---|---|
| Sales summary (aggregated) | 5 minutes | Data changes frequently |
| Top sellers | 15 minutes | Rankings change slowly |
| Stock levels | 2 minutes | Stock moves in real-time |
| Dead stock analysis | 1 hour | Slow-changing metric |
| Season performance | 30 minutes | Medium change rate |
| AR/AP aging | 15 minutes | Changes on payment/invoice events |

```python
# Per-tool cache TTL
class SalesSummaryTool(BaseTool):
    cache_ttl_seconds = 300  # 5 minutes

class DeadStockTool(BaseTool):
    cache_ttl_seconds = 3600  # 1 hour
```

### Cache Integration in Gateway

```python
def _execute_tool_with_cache(self, tool, env, user, params):
    """Try cache first, fall back to live execution."""
    if not getattr(tool, 'cache_ttl_seconds', 0):
        return tool.execute(env, user, params)

    cache_key = self._make_cache_key(tool.name, params, user, user.company_id.id)
    cache_entry = env['ai.analyst.cache.entry'].sudo().search([
        ('cache_key', '=', cache_key),
        ('expires_at', '>', fields.Datetime.now()),
    ], limit=1)

    if cache_entry:
        cache_entry.sudo().write({
            'hit_count': cache_entry.hit_count + 1,
            'last_hit_at': fields.Datetime.now(),
        })
        return json.loads(gzip.decompress(base64.b64decode(cache_entry.result_json)))

    # Cache miss — execute live
    result = tool.execute(env, user, params)

    # Store in cache
    result_bytes = gzip.compress(json.dumps(result, default=str).encode())
    env['ai.analyst.cache.entry'].sudo().create({
        'cache_key': cache_key,
        'tool_name': tool.name,
        'params_hash': cache_key.split(':')[-1],
        'user_id': user.id,
        'company_id': user.company_id.id,
        'result_json': base64.b64encode(result_bytes).decode(),
        'result_size_bytes': len(result_bytes),
        'row_count': len(result.get('table', [])),
        'expires_at': fields.Datetime.now() + timedelta(seconds=tool.cache_ttl_seconds),
    })

    return result
```

### Cache Invalidation

```python
# Cron: clean expired cache entries (every 10 minutes)
def _cron_clean_cache(self):
    expired = self.search([('expires_at', '<', fields.Datetime.now())])
    count = len(expired)
    expired.unlink()
    _logger.info("Cleaned %d expired cache entries", count)

# Manual invalidation (admin action)
def action_flush_cache(self):
    """Flush all cache entries for this company."""
    self.search([('company_id', '=', self.env.company.id)]).unlink()
```

## 4. Pre-Aggregation Tables (Phase 3)

### Product Dimension Cache

```
_name = 'ai.analyst.product.dim.cache'
_description = 'Denormalized Product Dimensions'

Fields:
    product_tmpl_id     Many2one    product.template    required, indexed
    product_id          Many2one    product.product     indexed
    default_code        Char        indexed

    # Denormalized dimensions
    gender              Char        indexed
    age_group           Char        indexed
    brand               Char        indexed
    category_l1         Char        indexed     Top-level category name
    category_l2         Char        indexed     Second-level category name
    season_codes        Char                    Comma-separated: "FW25,NOS"
    color_values        Char                    Comma-separated: "Black,White"

    # Stock snapshot (refreshed periodically)
    stock_on_hand       Float
    stock_incoming      Float
    stock_value         Float

    last_synced_at      Datetime
```

### Daily Sales Aggregate

```
_name = 'ai.analyst.daily.sales.agg'
_description = 'Daily Sales Aggregation'

Fields:
    date                Date        required, indexed
    company_id          Many2one    res.company     required, indexed
    product_tmpl_id     Many2one    product.template    required, indexed

    # Denormalized dimensions (from product.dim.cache)
    gender              Char
    brand               Char
    category_l1         Char
    season_code         Char        Primary season

    # Aggregated metrics
    qty_sold            Float
    revenue             Float
    margin              Float       (if sale_margin installed)
    order_count         Integer
    refund_qty          Float
    refund_amount       Float

    # Channel split
    channel             Selection   [('online','Online'), ('pos','POS')]

SQL Constraints:
    unique(date, company_id, product_tmpl_id, channel)
```

### Aggregation Cron (Nightly)

```python
def _cron_aggregate_daily_sales(self):
    """Aggregate yesterday's sales into daily_sales_agg table.
    Runs nightly at 02:00. Idempotent (upsert logic).
    """
    yesterday = fields.Date.today() - timedelta(days=1)

    # Online sales
    online_data = self.env['sale.order.line'].read_group(
        domain=[
            ('order_id.state', 'in', ['sale', 'done']),
            ('order_id.date_order', '>=', yesterday),
            ('order_id.date_order', '<', fields.Date.today()),
        ],
        fields=['product_tmpl_id', 'product_uom_qty:sum',
                'price_subtotal:sum', 'order_id:count_distinct'],
        groupby=['product_tmpl_id'],
    )

    for row in online_data:
        self._upsert_daily_agg(yesterday, row, 'online')

    # POS sales (similar pattern)
    # ...
```

### Performance Impact of Pre-Aggregation

| Query | Without Agg | With Agg | Improvement |
|---|---|---|---|
| Revenue by brand, last 30 days | ~2s (scan sale.order.line) | ~50ms (scan 30 rows × brands) | 40x |
| Season sell-through | ~5s (JOIN tags + lines) | ~100ms (pre-joined) | 50x |
| Trend: daily revenue, 90 days | ~3s | ~20ms | 150x |
| Dead stock analysis | ~8s (stock + sales JOIN) | ~200ms | 40x |

## 5. Read Replicas (Phase 4)

### When to Consider

- Odoo worker count > 8 and AI queries compete with web requests
- Dashboard refresh during peak hours causes user-facing slowdowns
- Query volume exceeds 1,000/day consistently

### Architecture

```
                    ┌─────────────┐
                    │  Odoo Web   │ ──── Primary DB (read/write)
                    │  Workers    │
                    └──────┬──────┘
                           │
                    ┌──────┴──────┐
                    │ AI Analyst  │ ──── Read Replica DB (read-only)
                    │  Gateway    │      (streaming replication)
                    └─────────────┘
```

### Implementation (Odoo 17)

```python
# In gateway, use a read-only database cursor for analytics:
# Option 1: Odoo multi-database routing (custom)
# Option 2: PostgreSQL connection with read-only flag

# Pragmatic approach: configure a separate db_replica in odoo.conf
# and use it for tool execution only.

class BaseTool:
    use_read_replica = True  # Default for all analytics tools

    def execute(self, env, user, params):
        if self.use_read_replica and hasattr(env, 'replica_cr'):
            env = env.with_context(using_replica=True)
        return self._execute_impl(env, user, params)
```

### Replication Lag Handling

```
- Acceptable lag: < 5 seconds for analytics queries
- Cache TTL should be >= replication lag
- Write operations (proposals, audit logs) ALWAYS use primary
- If replica is down, fall back to primary (existing connection)
```

## 6. Connection Pool Management

### Current Protection (Phase 1)

- Dashboard widget semaphore: `MAX_PARALLEL = 10`

### Phase 2 Enhancements

```python
# Global tool execution pool
import threading

class ToolExecutionPool:
    """Manages concurrent tool executions to protect connection pool."""

    def __init__(self, max_workers=10, queue_timeout=5):
        self._semaphore = threading.Semaphore(max_workers)
        self._queue_timeout = queue_timeout
        self._active_count = 0
        self._lock = threading.Lock()

    def execute(self, func, *args, **kwargs):
        acquired = self._semaphore.acquire(timeout=self._queue_timeout)
        if not acquired:
            raise ResourceWarning(
                f"Tool execution pool full ({self._active_count} active). "
                f"Please retry."
            )
        with self._lock:
            self._active_count += 1
        try:
            return func(*args, **kwargs)
        finally:
            with self._lock:
                self._active_count -= 1
            self._semaphore.release()

    @property
    def utilization(self):
        return self._active_count

# Singleton
_tool_pool = ToolExecutionPool(max_workers=10)
```

## 7. Monitoring

### Key Metrics to Track (via audit log aggregation)

| Metric | Source | Alert Threshold |
|---|---|---|
| Avg tool execution time | tool_call_log.execution_time_ms | > 5,000ms |
| Tool timeout rate | tool_call_log (success=False, timeout) | > 5% |
| Cache hit rate | cache_entry.hit_count / total queries | < 30% |
| Concurrent tool executions | ToolExecutionPool.utilization | > 8/10 |
| Export job queue depth | export_job (state=pending) | > 10 |
| Daily query volume | audit_log (event_type=query) | > 2,000 |
| Provider error rate | audit_log (event_type=error) | > 2% |
| Avg tokens per query | audit_log.tokens_output | > 4,000 |

### Admin Dashboard (Phase 2)

A new "System Health" section in Administration showing:
- Tool execution times (last 24h, p50/p95/p99)
- Cache hit rate
- Provider costs by model
- Active export jobs
- Query volume trend
- Error rate

Implemented as pivot/graph views on existing audit log model.
