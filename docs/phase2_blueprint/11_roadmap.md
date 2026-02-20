# 11 — Roadmap

## Phase 2: Foundation (Workspaces + Safety + Routing)

### Milestone 2.1: Workspaces and RBAC

| Deliverable | Definition of Done |
|---|---|
| `ai.analyst.workspace` model | CRUD operations, seed data for 4 workspaces, record rules |
| `ai.analyst.workspace.tool.ref` model | Tool allowlists per workspace, admin UI |
| `ai.analyst.workspace.prompt.pack` model | Suggested prompts per workspace, UI integration |
| Workspace selector OWL component | Dropdown in chat header, stores selection on conversation |
| Gateway workspace context injection | System prompt includes workspace description, tools filtered by allowlist |
| Conversation gains `workspace_id` | Stored on conversation, used by gateway |
| Menu restructure | Workspaces admin menu under Administration |
| **DoD**: User selects "Buying" workspace → only sees buying tools and prompts → can switch to "Sales" and see different tools. Record rules verified for multi-company. |

### Milestone 2.2: Dimension Dictionary

| Deliverable | Definition of Done |
|---|---|
| `ai.analyst.dimension` model | 6 seed dimensions (gender, age_group, brand, category, season, color) |
| `ai.analyst.dimension.synonym` model | Synonym lookup with case-insensitive matching |
| `ai.analyst.season.config` model | Season → tag pattern mappings, seed data |
| `ai.analyst.season.tag.pattern` model | Exact/prefix/contains/regex matching |
| Dimension context in system prompt | Gateway injects dimension list + synonyms + examples |
| `get_sales_by_dimension` tool | Groups sales by any dimension, resolves synonyms, builds domains |
| `get_season_performance` tool | Season-aware analysis using season config |
| Admin UI for dimensions | Form/tree views for dimensions, synonyms, seasons |
| **DoD**: User asks "FW25 women's sneakers by brand" → LLM resolves FW25 via season config, "women's" via gender synonym, "sneakers" via category synonym → returns correct grouped results. Admin can add new dimension without code change. |

### Milestone 2.3: Big Query Safety

| Deliverable | Definition of Done |
|---|---|
| `BaseTool.estimate_cost()` method | Returns estimated rows, seconds, recommendation |
| Date range validation in `validate_params()` | Rejects > 730 days, logs |
| Cost estimation in gateway | Checked before tool execution, returns export offer if exceeded |
| `ai.analyst.export.job` model | Full lifecycle: pending → running → done/failed/expired |
| Export controller endpoints | start, status, download — with ownership checks |
| Export progress OWL component | Toast notification with progress bar, download button |
| Export file cleanup cron | Daily, deletes expired attachments |
| `ai.analyst.query.budget` model | Per-user/workspace budgets, enforced in gateway |
| Tool execution semaphore | 10 concurrent max, queue timeout, busy message |
| **DoD**: Query matching 15K rows → user sees "preparing CSV export" → progress bar → download link. Expired files cleaned. Budget-exceeded user sees clear message. Concurrent tool limit prevents worker exhaustion. |

### Milestone 2.4: Model Routing

| Deliverable | Definition of Done |
|---|---|
| `ai.analyst.model.router` AbstractModel | Complexity classification, provider selection |
| Provider config gains `cost_tier`, `priority`, `is_escalation_target` | Migration script, admin UI update |
| Seed provider configs | Haiku (cheap), Sonnet (standard), Opus (premium) |
| Gateway integration | Router selects provider, escalation on quality failure |
| Validation gates | Tool call validation, response validation before acting |
| Cost estimation in audit log | Per-query cost estimate stored |
| **DoD**: Simple query "revenue this month" → routed to Haiku. "Compare FW25 vs FW24 sell-through by brand with dead stock analysis" → routed to Sonnet. Confused Haiku response → auto-escalated to Sonnet. Cost tracking visible in audit logs. |

### Milestone 2.5: Security Hardening

| Deliverable | Definition of Done |
|---|---|
| Prompt injection detection | Pattern matching, audit logging, no false-positive blocking |
| System prompt hardening | Anti-injection suffix on all prompts |
| Input sanitization | Suspicious patterns logged |
| Tool result sanitization | Strip instruction-like patterns from data |
| Export file access control | Ownership verification in controller |
| Security audit checklist | Documented, 12-point checklist passes |
| **DoD**: Known injection patterns logged to audit. System prompt reveals nothing when asked. Export files only accessible by owner. All 12 security checklist items pass. |

---

## Phase 3: Intelligence (Buying + Actions + Performance)

### Milestone 3.1: Buying Intelligence Tools

| Deliverable | Definition of Done |
|---|---|
| `get_buying_velocity` tool | Velocity calculation with dimension filtering |
| `get_dead_stock` tool | Dead stock scoring with configurable weights |
| `get_stock_coverage` tool | Coverage in days/weeks with alert thresholds |
| `get_reorder_suggestions` tool | Reorder quantities with MOQ, confidence, reasoning |
| Configurable dead stock weights | ir.config_parameter, admin UI |
| Explainability in all results | Formula in meta, reasoning per row, confidence indicators |
| **DoD**: User asks "dead stock for FW24 women's" → gets scored list with per-item reasoning. Asks "reorder suggestions for items under 2 weeks coverage" → gets quantities with confidence and MOQ adjustments. All results include formula explanation. |

### Milestone 3.2: Safe Actions Framework

| Deliverable | Definition of Done |
|---|---|
| `ai.analyst.action.proposal` model | Full lifecycle with chatter |
| `ai.analyst.action.proposal.line` model | Editable lines with user overrides |
| `ai.analyst.action.execution` model | Execution log |
| Proposal creation from tool results | Gateway creates proposal from reorder suggestions |
| Proposal review UI | Form view with editable quantities, exclusion checkboxes |
| PO executor | Creates draft PO(s) grouped by supplier |
| Approval flow | Group-based approval, state machine enforcement |
| Proposal expiration cron | 7-day TTL, auto-expire |
| Proposal card in chat | OWL component showing proposal summary with action buttons |
| **DoD**: AI suggests reorders → proposal created → user edits quantities → purchase manager approves → draft PO created (NOT confirmed) → execution logged in audit. Expired proposals auto-expire. Non-authorized users cannot approve. |

### Milestone 3.3: Performance Optimization

| Deliverable | Definition of Done |
|---|---|
| Database indexes | All Priority 1-4 indexes created via post-init hook |
| `ai.analyst.cache.entry` model | Cache with TTL, hit counting |
| Cache integration in gateway | Check cache before tool execution, store results |
| Cache cleanup cron | Every 10 minutes, delete expired entries |
| `ai.analyst.product.dim.cache` | Denormalized product dimensions |
| Dimension cache sync cron | Nightly rebuild, incremental updates |
| **DoD**: Repeated identical query served from cache (< 50ms vs ~2s). Cache hit rate > 50% after warm-up. Dimension queries use denormalized table, 10x faster than JOINs. Indexes verified via EXPLAIN ANALYZE. |

### Milestone 3.4: Customer Service Workspace Tools

| Deliverable | Definition of Done |
|---|---|
| `get_helpdesk_summary` tool | Ticket volume, resolution time, category breakdown |
| Module dependency handling | Graceful if helpdesk module not installed |
| CS workspace seed prompts | 4-6 suggested prompts |
| **DoD**: CS workspace shows helpdesk analytics. If helpdesk not installed, workspace shows available tools only (sales-related). |

---

## Phase 4: Scale (Automation + Advanced + Infrastructure)

### Milestone 4.1: Advanced Buying Automation

| Deliverable | Definition of Done |
|---|---|
| Scheduled reorder analysis | Cron runs weekly reorder suggestion for configured categories |
| Auto-proposal creation | System creates proposals automatically, sends notification |
| Proposal notification | Odoo activity/email when new proposal awaits approval |
| Bulk approval UI | Tree view with multi-select approve/reject |
| **DoD**: Weekly cron identifies items needing reorder → creates proposals → notifies purchase managers → managers can bulk-approve → draft POs created. |

### Milestone 4.2: Finance Workspace

| Deliverable | Definition of Done |
|---|---|
| Finance workspace config | AR, AP, P&L, cash flow tools |
| `get_pl_summary` tool | Revenue, COGS, gross margin, expenses |
| `get_cash_flow` tool | Cash in/out by period |
| Enhanced AR/AP tools | Aging by customer segment, payment behavior |
| **DoD**: Finance users access Finance workspace with dedicated tools. P&L and cash flow analytics functional. |

### Milestone 4.3: Inventory/Operations Workspace

| Deliverable | Definition of Done |
|---|---|
| Inventory workspace config | Stock levels, movements, warehouse efficiency |
| `get_warehouse_efficiency` tool | Fill rate, picking accuracy, turnover |
| `get_stock_movement` tool | In/out/internal transfers by period |
| **DoD**: Operations users access Inventory workspace. Warehouse efficiency metrics functional. |

### Milestone 4.4: Pre-Aggregation and Scaling

| Deliverable | Definition of Done |
|---|---|
| `ai.analyst.daily.sales.agg` model | Daily sales aggregation table |
| Nightly aggregation cron | Idempotent upsert of daily data |
| Tool migration to aggregation tables | High-frequency tools use agg tables when available |
| Read replica routing (optional) | AI queries routed to read replica if configured |
| **DoD**: Dashboard queries use pre-aggregated data. P95 query time < 500ms. Read replica routing works if replica configured, falls back to primary if not. |

### Milestone 4.5: Additional Safe Action Types

| Deliverable | Definition of Done |
|---|---|
| Stock adjustment proposals | AI suggests inventory corrections |
| Price change proposals | AI suggests price list updates |
| Same Propose → Approve → Execute flow | Reuses existing framework |
| **DoD**: Each new action type follows SAF pattern. Draft records only. Full audit trail. |

---

## Release Checklist (Every Milestone)

- [ ] All new models have `company_id` + record rules
- [ ] No `sudo()` in analytics/tool code paths
- [ ] All tools use `env.with_user(user)`
- [ ] JSON Schema validation on all new tool parameters
- [ ] Unit tests for new tools (parameterized)
- [ ] Security audit checklist passes (12 points)
- [ ] Audit logging covers new features
- [ ] Admin UI exists for new configuration models
- [ ] Seed data loads without errors
- [ ] `__manifest__.py` version bumped
- [ ] Migration script if schema changes on existing models
- [ ] Performance tested with representative data volumes

---

## Dependency Graph

```
Milestone 2.1 (Workspaces)
    └── Milestone 2.2 (Dimensions)  ← needs workspace context injection
    └── Milestone 2.3 (Big Query)   ← needs workspace budgets
    └── Milestone 2.4 (Routing)     ← independent, can parallel with 2.2
    └── Milestone 2.5 (Security)    ← independent, can parallel

Milestone 3.1 (Buying Tools) ← needs 2.2 (dimensions) + 2.3 (big query safety)
Milestone 3.2 (Safe Actions) ← needs 3.1 (buying suggestions as input)
Milestone 3.3 (Performance)  ← needs 2.3 (cache model) + 2.2 (dimension cache)
Milestone 3.4 (CS Workspace) ← needs 2.1 (workspaces)

Milestone 4.x ← needs Phase 3 complete
```

## Parallelization Opportunities

```
Sprint 1: 2.1 (Workspaces) + 2.4 (Routing) + 2.5 (Security) in parallel
Sprint 2: 2.2 (Dimensions) + 2.3 (Big Query) — can partially overlap
Sprint 3: 3.1 (Buying) + 3.4 (CS Workspace) in parallel
Sprint 4: 3.2 (Safe Actions) + 3.3 (Performance) — can partially overlap
Sprint 5+: Phase 4 milestones as needed
```
