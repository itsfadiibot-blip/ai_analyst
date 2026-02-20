# 05 — Big Query Safety and Exports

## Problem Statement

Unbounded queries can kill Odoo:
- "Show me all order lines from the last 2 years" → millions of rows
- "List all active products with attributes" → ORM memory explosion
- Dashboard with 12 widgets refreshing simultaneously → connection pool exhaustion

We need platform-level protections at every layer.

## Defense Layers

```
Layer 1: LLM Prompt Guardrails          (prevent bad queries)
Layer 2: Tool Parameter Validation       (reject unbounded params)
Layer 3: Cost Estimation                 (estimate before execute)
Layer 4: Inline Row Limits               (cap live results)
Layer 5: Async Export Jobs               (handle large results)
Layer 6: Query Budgets                   (throttle per user/workspace)
Layer 7: Connection Pool Protection      (semaphore + timeout)
```

## Layer 1: LLM Prompt Guardrails

Injected into the system prompt for every request:

```
## Query Safety Rules
- NEVER request "all" records without date filters and reasonable limits.
- Always include date_from/date_to for time-series queries.
- Default limit is 50 rows. Maximum inline display is 500 rows.
- If the user asks for a full export or "all data", use the export_csv tool
  which handles large datasets asynchronously.
- If a tool returns a row_count_total that exceeds the inline limit,
  inform the user and offer CSV export.
- Prefer aggregated views (read_group) over line-level detail.
```

## Layer 2: Tool Parameter Validation

Every tool's `validate_params()` method (already in `base_tool.py`) is extended:

```python
# base_tool.py extensions
class BaseTool:
    max_rows = 500           # existing — inline preview cap
    max_date_range_days = 730 # NEW — 2 years max
    require_date_filter = True # NEW — most tools require dates

    def validate_params(self, params):
        # Existing JSON Schema validation...
        super().validate_params(params)

        # Date range guard
        if self.require_date_filter:
            date_from = params.get('date_from')
            date_to = params.get('date_to')
            if not date_from or not date_to:
                raise ValidationError("date_from and date_to are required.")
            delta = (parse_date(date_to) - parse_date(date_from)).days
            if delta > self.max_date_range_days:
                raise ValidationError(
                    f"Date range exceeds {self.max_date_range_days} days. "
                    f"Use export for large datasets."
                )

        # Limit guard
        limit = params.get('limit', 50)
        if limit > self.max_rows:
            params['limit'] = self.max_rows  # silently cap
```

## Layer 3: Cost Estimation

New method on `BaseTool`:

```python
def estimate_cost(self, env, user, params):
    """Estimate query cost before execution.

    Returns:
        dict: {
            'estimated_rows': int,
            'estimated_seconds': float,
            'recommendation': 'inline' | 'export' | 'deny',
            'reason': str
        }
    """
    # Default implementation: count matching records
    domain = self._build_domain(env, user, params)
    count = env[self._model].with_user(user).search_count(domain)
    estimated_seconds = count / 10000  # rough heuristic

    if count <= self.max_rows:
        return {'estimated_rows': count, 'estimated_seconds': estimated_seconds,
                'recommendation': 'inline', 'reason': ''}
    elif count <= 100000:
        return {'estimated_rows': count, 'estimated_seconds': estimated_seconds,
                'recommendation': 'export',
                'reason': f'{count} rows exceeds inline limit of {self.max_rows}'}
    else:
        return {'estimated_rows': count, 'estimated_seconds': estimated_seconds,
                'recommendation': 'deny',
                'reason': f'{count} rows is too large. Add filters to narrow results.'}
```

Gateway integration:

```python
# In gateway._execute_tool_call():
estimate = tool.estimate_cost(env, user, params)
if estimate['recommendation'] == 'deny':
    return {'error': estimate['reason'], 'suggestion': 'Add more filters.'}
if estimate['recommendation'] == 'export':
    # Return export offer instead of inline data
    return {
        'answer': f"This query matches ~{estimate['estimated_rows']} rows. "
                  f"Inline display is limited to {tool.max_rows}. "
                  f"I'll prepare a CSV export for you.",
        'actions': [{'type': 'export_offer', 'tool_name': tool.name, 'params': params}]
    }
```

## Layer 4: Inline Row Limits

Already implemented via `BaseTool.max_rows = 500`. Tools must respect this:

```python
# In tool execute():
results = env[model].read_group(domain, fields, groupby, limit=self.max_rows)
total_count = env[model].search_count(domain)

return {
    'table': results[:self.max_rows],
    'meta': {
        'row_count': len(results),
        'row_count_total': total_count,
        'truncated': total_count > self.max_rows,
        'export_available': total_count > self.max_rows,
    }
}
```

## Layer 5: Async Export Jobs

### Export Job Model

```
_name = 'ai.analyst.export.job'
_description = 'Async Export Job'
_order = 'create_date desc'

Fields:
    name                Char            computed    "Export: {tool_name} @ {timestamp}"
    user_id             Many2one        res.users   required
    company_id          Many2one        res.company required
    conversation_id     Many2one        ai.analyst.conversation

    # What to export
    tool_name           Char            required
    tool_args_json      Text            required    JSON parameters
    export_format       Selection       [('csv','CSV'), ('xlsx','Excel')]  default='csv'

    # Execution state
    state               Selection       required    default='pending'
        'pending'       — Queued
        'running'       — In progress
        'done'          — Completed, file ready
        'failed'        — Error occurred
        'expired'       — File TTL exceeded, cleaned up

    # Progress
    total_rows          Integer         Estimated total
    processed_rows      Integer         Rows written so far
    progress_percent    Float           computed    processed_rows / total_rows * 100
    batch_size          Integer         default=5000

    # Result
    attachment_id       Many2one        ir.attachment   Download file
    file_size_bytes     Integer
    error_message       Text

    # Timing
    started_at          Datetime
    completed_at        Datetime
    expires_at          Datetime        computed    completed_at + TTL

    # Cleanup
    ttl_hours           Integer         default=24
```

### Export Job Processing

```python
class AiAnalystExportJob(models.Model):
    _name = 'ai.analyst.export.job'

    def action_start(self):
        """Called by cron or controller. Runs the export in batches."""
        self.ensure_one()
        self.write({'state': 'running', 'started_at': fields.Datetime.now()})
        self.env.cr.commit()  # Commit state change immediately

        try:
            tool = get_tool(self.tool_name)
            params = json.loads(self.tool_args_json)
            params.pop('limit', None)  # Remove limit for full export

            # Get total count
            estimate = tool.estimate_cost(self.env, self.user_id, params)
            self.total_rows = estimate['estimated_rows']
            self.env.cr.commit()

            # Stream results in batches
            output = io.BytesIO()
            writer = csv.writer(io.TextIOWrapper(output, encoding='utf-8', newline=''))
            header_written = False
            offset = 0

            while offset < self.total_rows:
                batch_params = {**params, 'limit': self.batch_size, 'offset': offset}
                result = tool.execute(self.env, self.user_id, batch_params)
                rows = result.get('table', [])

                if not rows:
                    break

                if not header_written:
                    writer.writerow(rows[0].keys())
                    header_written = True

                for row in rows:
                    writer.writerow(row.values())

                offset += len(rows)
                self.processed_rows = offset
                self.env.cr.commit()  # Commit progress for polling

            # Save file
            output.seek(0)
            filename = f"{self.tool_name}_{fields.Date.today()}.csv"
            attachment = self.env['ir.attachment'].create({
                'name': filename,
                'datas': base64.b64encode(output.read()),
                'mimetype': 'text/csv',
                'res_model': self._name,
                'res_id': self.id,
            })
            self.write({
                'state': 'done',
                'attachment_id': attachment.id,
                'file_size_bytes': len(attachment.datas),
                'completed_at': fields.Datetime.now(),
                'expires_at': fields.Datetime.now() + timedelta(hours=self.ttl_hours),
            })

        except Exception as e:
            self.write({'state': 'failed', 'error_message': str(e)[:2000]})
            _logger.exception("Export job %s failed", self.id)
```

### Export Controller Endpoints

```python
# controllers/export.py

class AiAnalystExportController(http.Controller):

    @http.route('/ai_analyst/export/start', type='json', auth='user')
    def start_export(self, tool_name, tool_args, export_format='csv'):
        """Create and queue an export job."""
        user = request.env.user
        # Validate tool access
        tool = get_tool(tool_name)
        if not tool or not tool.check_access(user):
            raise AccessError("Tool not accessible.")

        job = request.env['ai.analyst.export.job'].create({
            'tool_name': tool_name,
            'tool_args_json': json.dumps(tool_args),
            'export_format': export_format,
            'user_id': user.id,
            'company_id': user.company_id.id,
        })
        # Trigger processing via ir.cron or threaded worker
        job.with_delay().action_start()  # or schedule via cron
        return {'job_id': job.id, 'state': 'pending'}

    @http.route('/ai_analyst/export/status', type='json', auth='user')
    def export_status(self, job_id):
        """Poll export job progress."""
        job = request.env['ai.analyst.export.job'].browse(job_id)
        if job.user_id != request.env.user:
            raise AccessError("Not your export.")
        return {
            'job_id': job.id,
            'state': job.state,
            'progress_percent': job.progress_percent,
            'processed_rows': job.processed_rows,
            'total_rows': job.total_rows,
            'error_message': job.error_message,
            'download_url': f'/web/content/{job.attachment_id.id}' if job.state == 'done' else None,
        }

    @http.route('/ai_analyst/export/download/<int:job_id>', type='http', auth='user')
    def download_export(self, job_id):
        """Download completed export file."""
        job = request.env['ai.analyst.export.job'].browse(job_id)
        if job.user_id != request.env.user or job.state != 'done':
            raise AccessError("Export not available.")
        return request.env['ir.attachment']._get_stream_from(job.attachment_id).get_response()
```

### UI: Export Progress Component

```
AiExportProgress (OWL Component)
    - Shown as a toast/notification when export starts
    - Polls /ai_analyst/export/status every 3 seconds
    - Shows progress bar with percentage
    - On completion: shows download button
    - On failure: shows error message with retry option
```

## Layer 6: Query Budgets

### Budget Model

```
_name = 'ai.analyst.query.budget'
_description = 'Query Budget Configuration'

Fields:
    name                Char            computed
    budget_type         Selection
        'global'        — System-wide defaults
        'workspace'     — Per workspace
        'user'          — Per user override

    workspace_id        Many2one        ai.analyst.workspace
    user_id             Many2one        res.users
    company_id          Many2one        res.company

    # Limits
    daily_query_limit   Integer         default=0   0=unlimited
    hourly_query_limit  Integer         default=0   0=unlimited
    max_tool_calls_per_query  Integer   default=8
    max_inline_rows     Integer         default=500
    max_export_rows     Integer         default=100000
    max_concurrent_exports Integer      default=3

    # Cost limits
    daily_token_budget  Integer         default=0   0=unlimited
    max_tokens_per_query Integer        default=8000
```

Budget resolution order: **user override → workspace → global**.

### Budget Enforcement

```python
# In gateway.process_message():
budget = self._resolve_budget(user, workspace)

# Check daily query count
today_count = self.env['ai.analyst.audit.log'].search_count([
    ('user_id', '=', user.id),
    ('event_type', '=', 'query'),
    ('create_date', '>=', fields.Date.today()),
])
if budget.daily_query_limit and today_count >= budget.daily_query_limit:
    return {'error': 'Daily query limit reached. Try again tomorrow.'}

# Check token budget
today_tokens = sum(self.env['ai.analyst.audit.log'].search([
    ('user_id', '=', user.id),
    ('event_type', '=', 'provider_call'),
    ('create_date', '>=', fields.Date.today()),
]).mapped('tokens_output'))
if budget.daily_token_budget and today_tokens >= budget.daily_token_budget:
    return {'error': 'Daily token budget exhausted.'}
```

## Layer 7: Connection Pool Protection

Already partially implemented (semaphore in dashboard controller with `MAX_PARALLEL = 10`). Extend to all tool execution:

```python
import threading

_TOOL_SEMAPHORE = threading.Semaphore(10)  # Max 10 concurrent tool executions
_TOOL_TIMEOUT = 30  # seconds (matches BaseTool.timeout_seconds)

def _execute_tool_safe(self, tool, env, user, params):
    acquired = _TOOL_SEMAPHORE.acquire(timeout=5)
    if not acquired:
        return {'error': 'Server busy. Please retry in a few seconds.'}
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(tool.execute, env, user, params)
            return future.result(timeout=_TOOL_TIMEOUT)
    except TimeoutError:
        return {'error': f'Query timed out after {_TOOL_TIMEOUT}s. Try narrower filters.'}
    finally:
        _TOOL_SEMAPHORE.release()
```

## Recommended Defaults

| Setting | Default | Max | Notes |
|---|---|---|---|
| Inline preview rows | 500 | 500 | Hard cap in BaseTool |
| Export batch size | 5,000 | 10,000 | Per-batch commit |
| Export max rows | 100,000 | 500,000 | Configurable per budget |
| Export file TTL | 24 hours | 72 hours | Cleanup via cron |
| Max concurrent exports per user | 3 | 5 | Prevent abuse |
| Max concurrent tool executions | 10 | 20 | Server-wide semaphore |
| Tool execution timeout | 30 seconds | 60 seconds | Per-tool configurable |
| Max date range | 730 days | 1095 days | Per-tool configurable |
| Rate limit | 20 req/min | 60 req/min | Existing, per-user |
| Daily query limit | Unlimited | — | Configurable per budget |
| Daily token budget | Unlimited | — | Configurable per budget |
| Max tool calls per query | 8 | 15 | Existing, per-config |
| Max input chars | 8,000 | 16,000 | Existing |
| Cache TTL (dashboard widgets) | 60 seconds | 300 seconds | Existing |
| Cache TTL (query results) | 300 seconds | 3,600 seconds | New, per-tool |

## Cron Jobs (New)

| Cron | Schedule | Action |
|---|---|---|
| Export Job Processor | Every 1 minute | Process pending export jobs (FIFO, max 2 concurrent) |
| Export File Cleanup | Daily at 03:00 | Delete expired export attachments |
| Query Budget Reset | Daily at 00:00 | Reset daily counters (implicit via date-based queries) |

## Failure Modes and UX Messaging

| Scenario | System Behavior | User Message |
|---|---|---|
| Query exceeds inline limit | Return export offer | "This query matches ~15,000 rows. I'll prepare a CSV export for you." |
| Query exceeds export limit | Reject with suggestion | "Too many results (~500K rows). Please add date or category filters." |
| Tool execution timeout | Return error | "The query took too long. Try narrower date ranges or fewer dimensions." |
| Export job fails | Mark failed, log error | "Export failed. You can retry or contact your admin." |
| Rate limit hit | Return 429-style error | "You've reached the query limit. Please wait a moment." |
| Budget exhausted | Return budget error | "Daily query limit reached. Resets at midnight." |
| Server busy (semaphore) | Return 503-style error | "The server is handling many requests. Please retry in a few seconds." |
| Export file expired | Return 410 | "This export has expired. Please re-run the query." |
