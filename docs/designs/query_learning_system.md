# Query Learning System — Design Document

**Date:** 2026-02-25 | **Author:** Architect Agent | **Status:** Design (not yet implemented)

---

## 1. Problem Statement

`_classify_intent()` in `ai_analyst_gateway.py` uses hardcoded regex patterns to route queries between `universal_query` and `specialized_tool`. There's no feedback loop — when classification is wrong, we don't learn from it. We also can't see which questions fail, which require rephrasing, or which patterns are missing.

## 2. Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| **Data model** | New model `ai.analyst.query.log` | Audit log is generic events; query learning needs intent-specific fields. Separate model keeps concerns clean. |
| **Storage** | Log everything, 90-day retention | Volume is low (human queries, not API traffic). Matches existing `log_retention_days` param. |
| **Analysis** | Cron weekly + on-demand report action | Weekly auto-analysis catches trends; manual button in UI for ad-hoc review. |
| **Real-time flagging** | Yes, lightweight | Flag fallbacks and rephrases immediately in the log for easy filtering. |

## 3. Data Model

### 3.1 `ai.analyst.query.log`

```python
class AiAnalystQueryLog(models.Model):
    _name = 'ai.analyst.query.log'
    _description = 'AI Analyst Query Learning Log'
    _order = 'create_date desc'

    # --- Core fields ---
    user_id = fields.Many2one('res.users', required=True, index=True)
    company_id = fields.Many2one('res.company', required=True, index=True)
    conversation_id = fields.Many2one('ai.analyst.conversation', index=True, ondelete='set null')
    message_id = fields.Many2one('ai.analyst.message', ondelete='set null')

    # --- Question & Intent ---
    question_text = fields.Text(required=True)
    question_hash = fields.Char(index=True, help='MD5 of normalized question for dedup/grouping')
    detected_intent = fields.Selection([
        ('universal_query', 'Universal Query'),
        ('specialized_tool', 'Specialized Tool'),
        ('chitchat', 'Chitchat'),
    ], required=True, index=True)
    intent_confidence = fields.Float(help='Future: confidence score when we add ML classifier')
    matched_keywords = fields.Char(help='Which regex keywords triggered the match')

    # --- Execution outcome ---
    route_used = fields.Selection([
        ('universal_query', 'Universal Query'),
        ('specialized_tool', 'Specialized Tool'),
        ('fallback', 'Fallback (UQ failed → specialized)'),
    ], index=True, help='Actual route taken (may differ from detected_intent if fallback)')
    tools_used = fields.Char(help='Comma-separated tool names called')
    success = fields.Boolean(default=True)
    error_message = fields.Text()
    response_time_ms = fields.Integer()
    tier_used = fields.Char(help='Model tier: cheap/standard/premium')

    # --- Learning signals ---
    was_fallback = fields.Boolean(
        index=True,
        help='True if universal_query failed and fell back to specialized_tool'
    )
    was_rephrase = fields.Boolean(
        index=True,
        help='True if user sent a similar question within 2 minutes (rephrase detection)'
    )
    rephrase_of_id = fields.Many2one(
        'ai.analyst.query.log', ondelete='set null',
        help='Links to the original query this is a rephrase of'
    )
    feedback_rating = fields.Selection([
        ('up', 'Thumbs Up'),
        ('down', 'Thumbs Down'),
    ], help='Copied from query.feedback if user rated')

    # --- Cleanup ---
    def _gc_old_logs(self):
        """Called by cron. Respects ai_analyst.log_retention_days."""
        days = int(self.env['ir.config_parameter'].sudo().get_param(
            'ai_analyst.log_retention_days', 90))
        cutoff = fields.Datetime.subtract(fields.Datetime.now(), days=days)
        self.search([('create_date', '<', cutoff)]).unlink()
```

### 3.2 `ai.analyst.query.learning.report` (TransientModel)

```python
class AiAnalystQueryLearningReport(models.TransientModel):
    _name = 'ai.analyst.query.learning.report'
    _description = 'Query Learning Analysis Report'

    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    company_id = fields.Many2one('res.company')

    # --- Report output (stored as JSON in Text field) ---
    report_json = fields.Text()

    # Generated metrics
    total_queries = fields.Integer(readonly=True)
    fallback_count = fields.Integer(readonly=True)
    fallback_rate = fields.Float(readonly=True)
    rephrase_count = fields.Integer(readonly=True)
    rephrase_rate = fields.Float(readonly=True)
    top_failed_questions = fields.Text(readonly=True, help='JSON array')
    suggested_keywords = fields.Text(readonly=True, help='JSON array of suggested regex additions')
```

## 4. Integration Points

### 4.1 Hook into `_classify_intent()` — Logging the decision

Minimal change to gateway. After classification, log the decision:

```python
# In process_message(), around line 219:
intent = self._classify_intent(user_message)
matched_kw = self._get_matched_keywords(user_message)  # new helper

# After the entire request completes (success or fallback):
self.env['ai.analyst.query.log'].sudo().create({
    'user_id': user.id,
    'company_id': company.id,
    'conversation_id': conversation.id,
    'question_text': user_message,
    'question_hash': hashlib.md5(user_message.lower().strip().encode()).hexdigest(),
    'detected_intent': intent,
    'matched_keywords': matched_kw,
    'route_used': actual_route,  # tracked during execution
    'tools_used': ','.join(tools_called),
    'success': not bool(error),
    'error_message': error,
    'response_time_ms': int((time.time() - start_time) * 1000),
    'was_fallback': fell_back_to_specialized,
    'tier_used': tier_used,
})
```

### 4.2 Rephrase Detection

Simple heuristic: if same user sends another query to same conversation within 120 seconds, and the normalized text similarity > 0.5 (Jaccard on word tokens), mark it as a rephrase.

```python
def _detect_rephrase(self, user_id, conversation_id, question_text):
    """Check if this looks like a rephrase of a recent failed query."""
    cutoff = fields.Datetime.subtract(fields.Datetime.now(), seconds=120)
    recent = self.search([
        ('user_id', '=', user_id),
        ('conversation_id', '=', conversation_id),
        ('create_date', '>=', cutoff),
    ], limit=1, order='create_date desc')
    if not recent:
        return False, False
    # Jaccard similarity on word tokens
    words_a = set(question_text.lower().split())
    words_b = set(recent.question_text.lower().split())
    if not words_a or not words_b:
        return False, False
    similarity = len(words_a & words_b) / len(words_a | words_b)
    if similarity > 0.4:
        return True, recent.id
    return False, False
```

### 4.3 Feedback Integration

When `ai.analyst.query.feedback` receives a thumbs up/down, copy rating to the corresponding query log:

```python
# In query_feedback create() override or write():
query_log = self.env['ai.analyst.query.log'].search([
    ('message_id', '=', self.message_id.id)
], limit=1)
if query_log:
    query_log.write({'feedback_rating': self.rating})
```

## 5. Analysis Engine

### 5.1 Weekly Cron: `_analyze_query_patterns()`

Runs as a scheduled action. Generates a report record:

```python
def _analyze_query_patterns(self):
    """Weekly analysis of query learning data."""
    date_from = fields.Date.subtract(fields.Date.today(), days=7)
    date_to = fields.Date.today()

    logs = self.env['ai.analyst.query.log'].search([
        ('create_date', '>=', date_from),
    ])

    report = {
        'period': f'{date_from} to {date_to}',
        'total_queries': len(logs),
        'intent_distribution': {},  # count per intent
        'fallback_queries': [],     # questions where was_fallback=True
        'rephrase_queries': [],     # questions where was_rephrase=True
        'failed_queries': [],       # questions where success=False
        'misrouted_candidates': [], # specialized_tool queries that contain UQ keywords
        'suggested_keywords': [],   # new words appearing in successful UQ queries not in regex
        'top_questions_by_frequency': [],  # most common question_hash groups
        'user_patterns': {},        # per-user intent distribution
    }

    # 1. Fallback analysis
    fallbacks = logs.filtered(lambda l: l.was_fallback)
    report['fallback_queries'] = [{
        'question': l.question_text,
        'error': l.error_message,
        'user': l.user_id.name,
    } for l in fallbacks[:50]]

    # 2. Rephrase analysis (indicates confusion)
    rephrases = logs.filtered(lambda l: l.was_rephrase)
    report['rephrase_queries'] = [{
        'question': l.question_text,
        'original': l.rephrase_of_id.question_text if l.rephrase_of_id else '',
    } for l in rephrases[:50]]

    # 3. Keyword gap analysis
    # Extract words from successful universal_query logs
    # Compare against current regex pattern words
    # Suggest new keywords that appear frequently
    current_keywords = self._get_current_regex_keywords()
    word_freq = {}
    for log in logs.filtered(lambda l: l.route_used == 'universal_query' and l.success):
        for word in log.question_text.lower().split():
            word = re.sub(r'[^\w]', '', word)
            if word and word not in current_keywords and len(word) > 3:
                word_freq[word] = word_freq.get(word, 0) + 1
    report['suggested_keywords'] = sorted(
        word_freq.items(), key=lambda x: -x[1]
    )[:20]

    # 4. Misrouted candidates: went to specialized_tool but look like data queries
    for log in logs.filtered(lambda l: l.detected_intent == 'specialized_tool'):
        # Check if the question has data-query signals that regex missed
        if '?' in log.question_text or any(
            w in log.question_text.lower()
            for w in ['how many', 'total', 'average', 'list all']
        ):
            report['misrouted_candidates'].append({
                'question': log.question_text,
                'tools_used': log.tools_used,
            })

    # Store report
    self.env['ai.analyst.query.learning.report'].create({
        'date_from': date_from,
        'date_to': date_to,
        'report_json': json.dumps(report, indent=2),
        'total_queries': report['total_queries'],
        'fallback_count': len(fallbacks),
        'fallback_rate': len(fallbacks) / max(len(logs), 1) * 100,
        'rephrase_count': len(rephrases),
        'rephrase_rate': len(rephrases) / max(len(logs), 1) * 100,
        'top_failed_questions': json.dumps(report['fallback_queries'][:20]),
        'suggested_keywords': json.dumps(report['suggested_keywords']),
    })
```

### 5.2 `_get_current_regex_keywords()` Helper

Extracts the word list from the current `_classify_intent` regex so we can compare against actual usage:

```python
def _get_current_regex_keywords(self):
    """Parse the hardcoded regex in _classify_intent to get current keyword set."""
    return {
        'sales', 'stock', 'inventory', 'margin', 'order', 'orders', 'count',
        'revenue', 'pos', 'purchase', 'top', 'product', 'products', 'customer',
        'customers', 'invoice', 'invoices', 'vendor', 'supplier', 'profit',
        'cost', 'price', 'warehouse', 'quantity', 'amount', 'total', 'average',
        'sum', 'category', 'brand', 'payment', 'refund', 'return', 'deliver',
        'shipping', 'expense', 'budget', 'forecast', 'target', 'goal', 'kpi',
    }
```

## 6. User-Specific Learning (Phase 2)

Optional enhancement. Add to query log analysis:

```python
# Per-user pattern: what does each user typically ask about?
user_profiles = {}
for log in logs:
    uid = log.user_id.id
    if uid not in user_profiles:
        user_profiles[uid] = {'name': log.user_id.name, 'intents': {}, 'tools': {}}
    intent = log.detected_intent
    user_profiles[uid]['intents'][intent] = user_profiles[uid]['intents'].get(intent, 0) + 1
    for tool in (log.tools_used or '').split(','):
        if tool.strip():
            user_profiles[uid]['tools'][tool.strip()] = user_profiles[uid]['tools'].get(tool.strip(), 0) + 1
```

This enables:
- **Cache pre-warming**: CEO always asks sales → pre-cache sales summary on login
- **Personalized routing**: If user 90% uses universal_query, skip regex → go straight to UQ
- **Smarter defaults**: Pre-fill date ranges, brands user always filters by

## 7. UI for Reports

Minimal UI — a tree view of `ai.analyst.query.learning.report` records with:
- Date range, totals, fallback/rephrase rates
- Button to open full JSON report in a dialog
- Action button "Generate Report Now" (calls `_analyze_query_patterns` on demand)

```xml
<!-- views/query_learning_views.xml -->
<record id="view_query_learning_report_tree" model="ir.ui.view">
    <field name="name">ai.analyst.query.learning.report.tree</field>
    <field name="model">ai.analyst.query.learning.report</field>
    <field name="arch" type="xml">
        <tree>
            <field name="date_from"/>
            <field name="date_to"/>
            <field name="total_queries"/>
            <field name="fallback_count"/>
            <field name="fallback_rate" widget="percentage"/>
            <field name="rephrase_count"/>
            <field name="rephrase_rate" widget="percentage"/>
        </tree>
    </field>
</record>

<record id="action_query_learning_report" model="ir.actions.act_window">
    <field name="name">Query Learning Reports</field>
    <field name="res_model">ai.analyst.query.learning.report</field>
    <field name="view_mode">tree,form</field>
</record>
```

Menu under AI Analyst → Configuration → Query Learning Reports (visible to `group_ai_admin` only).

## 8. File Structure

```
models/
  ai_analyst_query_log.py          # New: ai.analyst.query.log model
  ai_analyst_query_learning.py     # New: analysis engine + report transient model
  ai_analyst_gateway.py            # Modified: add logging hooks
  query_feedback.py                # Modified: copy rating to query log
views/
  query_learning_views.xml         # New: tree/form views + menu
security/
  ir.model.access.csv             # Modified: add ACL for new models
data/
  ai_analyst_cron.xml             # Modified: add weekly analysis cron
```

## 9. Implementation Plan

| Step | What | Effort | Dependencies |
|---|---|---|---|
| 1 | Create `ai.analyst.query.log` model + migration | 0.5 day | None |
| 2 | Hook into `process_message()` to create log entries | 0.5 day | Step 1 |
| 3 | Add rephrase detection logic | 0.5 day | Step 2 |
| 4 | Create `ai.analyst.query.learning.report` transient + analysis engine | 1 day | Step 1 |
| 5 | Add weekly cron job | 0.5 day | Step 4 |
| 6 | Integrate feedback rating copy | 0.5 day | Step 2 |
| 7 | Add views + menu + security | 0.5 day | Steps 1, 4 |
| 8 | Testing + QA | 1 day | All |
| **Total** | | **5 days** | |

## 10. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Log volume too high | 90-day retention + daily cleanup cron (reuse existing pattern) |
| Rephrase detection false positives | Conservative threshold (0.4 Jaccard) + 120s window |
| Analysis cron too slow on large datasets | Limit to last 7 days per run; use `read_group` for aggregation where possible |
| Suggested keywords are noise | Human review required — report is advisory, not auto-applied |

## 11. Future Enhancements (Out of Scope)

- **ML-based classifier** replacing regex (needs enough training data from logs first)
- **Auto-apply keyword suggestions** with A/B testing
- **Embedding-based intent classification** using cached question embeddings
- **Real-time dashboard** with live fallback/error rates
