# 02 — Target Architecture

## High-Level Data Flow

```
                          +-----------------------+
                          |     OWL Chat / UI     |
                          |  (ai_analyst_action)   |
                          +----------+------------+
                                     |
                          POST /ai_analyst/chat
                                     |
                          +----------v------------+
                          |    AiAnalystGateway    |
                          |  (ai.analyst.gateway)  |
                          +----------+------------+
                                     |
                     +---------------+---------------+
                     |                               |
            +--------v--------+             +--------v--------+
            |  Model Router   |             | Workspace Ctx   |
            | (ai.analyst.    |             | (ai.analyst.    |
            |  model.router)  |             |  workspace)     |
            +--------+--------+             +--------+--------+
                     |                               |
            select provider                 inject workspace
            by complexity                   tool allowlist +
                     |                      system prompt
                     |                               |
            +--------v--------+             +--------v--------+
            | Provider Layer  |             | Tool Registry   |
            | Anthropic/OpenAI|             | + Dimension     |
            | (base_provider) |             |   Dictionary    |
            +--------+--------+             +--------+--------+
                     |                               |
              LLM response                   tool execution
              (tool_calls[])                 env.with_user(user)
                     |                               |
                     +---------------+---------------+
                                     |
                          +----------v------------+
                          |   Response Builder    |
                          |  answer + kpis +      |
                          |  table + chart +      |
                          |  actions + meta       |
                          +----------+------------+
                                     |
                     +---------------+---------------+
                     |               |               |
              +------v------+ +-----v------+ +------v------+
              | Inline      | | Export Job  | | Proposal    |
              | Preview     | | (async)    | | Engine      |
              | (≤500 rows) | | batched    | | (safe       |
              |             | | download   | |  actions)   |
              +-------------+ +------------+ +-------------+
                                     |
                          +----------v------------+
                          |    Audit Logger       |
                          | (ai.analyst.audit.log)|
                          +-----------------------+
```

## Architectural Layers

### Layer 1: Presentation (OWL)

| Component | File | Purpose |
|---|---|---|
| `AiAnalystMain` | `ai_analyst_action.js` | Chat interface (exists) |
| `AiAnalystDashboard` | `dashboard_client_action.js` | Dashboard view (exists) |
| `AiWorkspaceSelector` | `workspace_selector.js` | **NEW** — Workspace picker in chat header |
| `AiExportProgress` | `export_progress.js` | **NEW** — Export job progress polling |
| `AiProposalReview` | `proposal_review.js` | **NEW** — Proposal approval cards |

### Layer 2: Controllers (HTTP)

| Endpoint | Method | Purpose |
|---|---|---|
| `/ai_analyst/chat` | POST | Main chat (exists) |
| `/ai_analyst/export/start` | POST | **NEW** — Start async export |
| `/ai_analyst/export/status/<job_id>` | GET | **NEW** — Poll export progress |
| `/ai_analyst/export/download/<job_id>` | GET | **NEW** — Download completed export |
| `/ai_analyst/proposal/<id>/approve` | POST | **NEW** — Approve action proposal |
| `/ai_analyst/proposal/<id>/reject` | POST | **NEW** — Reject action proposal |
| `/ai_analyst/workspace/context` | POST | **NEW** — Get workspace config |

### Layer 3: Gateway (Business Logic)

The existing `ai.analyst.gateway` (AbstractModel) remains the single entry point. It gains:

1. **Workspace context injection** — Before building the system prompt, the gateway reads the user's active workspace and injects workspace-specific tool allowlists and prompt context.
2. **Model routing** — Instead of always calling the default provider, the gateway delegates to `ai.analyst.model.router` which selects the provider based on query complexity.
3. **Cost estimation** — Before executing a tool, the gateway calls `tool.estimate_cost(params)` to check against row/time budgets.
4. **Export redirection** — If estimated rows exceed the inline preview limit, the gateway returns an export-offer action instead of inline data.

### Layer 4: Tool Registry

The existing decorator-based registry (`@register_tool`) is unchanged. New tools are added for buying intelligence and workspace-specific analytics. Each tool gains:

- `estimate_cost(env, user, params) -> dict` — Returns `{estimated_rows, estimated_seconds}`
- `workspace` property — Which workspace(s) this tool belongs to
- `max_rows` already exists (default 500), used for inline preview cap

### Layer 5: Provider Abstraction

Existing `BaseProvider` / `AnthropicProvider` / `OpenAIProvider` are unchanged. New additions:

- `ai.analyst.model.router` — Deterministic routing logic (see `08_model_routing_strategy.md`)
- Provider configs gain `cost_tier` field (cheap / standard / premium)
- Provider configs gain `capability_tags` field (analytics, reasoning, actions)

### Layer 6: Data Layer

All new models follow Odoo 17 patterns: `_name`, `_description`, `company_id`, record rules.

## New Models Summary

| Model | Purpose | Detail Doc |
|---|---|---|
| `ai.analyst.workspace` | Workspace definition | `03_workspaces_and_rbac.md` |
| `ai.analyst.workspace.prompt.pack` | Suggested prompts per workspace | `03_workspaces_and_rbac.md` |
| `ai.analyst.dimension` | Product dimension definitions | `04_dimension_dictionary.md` |
| `ai.analyst.dimension.synonym` | Alias/synonym mappings | `04_dimension_dictionary.md` |
| `ai.analyst.season.config` | Season → tag mappings | `04_dimension_dictionary.md` |
| `ai.analyst.export.job` | Async export tracking | `05_big_query_safety_and_exports.md` |
| `ai.analyst.query.budget` | Per-user/workspace query budgets | `05_big_query_safety_and_exports.md` |
| `ai.analyst.buying.suggestion` | Reorder/dead-stock suggestions | `06_buying_intelligence.md` |
| `ai.analyst.action.proposal` | Proposed write actions | `07_safe_actions_framework.md` |
| `ai.analyst.action.execution` | Execution log of approved actions | `07_safe_actions_framework.md` |
| `ai.analyst.model.router` | Routing logic (AbstractModel) | `08_model_routing_strategy.md` |
| `ai.analyst.cache.entry` | Query result cache | `10_performance_scaling.md` |

## Dependency Graph (Addon Level)

```
ai_analyst (existing)
├── base, web, sale, point_of_sale, account, stock, purchase, contacts
└── (No new addon dependencies for Phase 2)
    All new models live inside ai_analyst.
    Optional: sale_margin (already soft-checked in margin tool)
```

## Module File Structure (Phase 2 Additions)

```
ai_analyst/
├── models/
│   ├── (existing files unchanged)
│   ├── ai_analyst_workspace.py          # NEW
│   ├── ai_analyst_dimension.py          # NEW
│   ├── ai_analyst_season_config.py      # NEW
│   ├── ai_analyst_export_job.py         # NEW
│   ├── ai_analyst_query_budget.py       # NEW
│   ├── ai_analyst_action_proposal.py    # NEW
│   ├── ai_analyst_model_router.py       # NEW
│   └── ai_analyst_cache_entry.py        # NEW
├── tools/
│   ├── (existing tools unchanged)
│   ├── tool_sales_by_dimension.py       # NEW
│   ├── tool_buying_velocity.py          # NEW
│   ├── tool_dead_stock.py              # NEW
│   ├── tool_stock_coverage.py          # NEW
│   ├── tool_reorder_suggestion.py      # NEW
│   ├── tool_helpdesk_summary.py        # NEW
│   └── tool_season_performance.py      # NEW
├── controllers/
│   ├── main.py                         # EXTENDED
│   ├── dashboard.py                    # UNCHANGED
│   └── export.py                       # NEW
├── security/
│   ├── (existing files extended)
│   └── workspace_rules.xml             # NEW
├── views/
│   ├── (existing files unchanged)
│   ├── workspace_views.xml             # NEW
│   ├── dimension_views.xml             # NEW
│   ├── export_job_views.xml            # NEW
│   └── proposal_views.xml             # NEW
├── data/
│   ├── workspace_data.xml             # NEW (seed workspaces)
│   ├── dimension_data.xml             # NEW (seed dimensions)
│   └── season_data.xml                # NEW (seed seasons)
├── static/src/
│   ├── js/
│   │   ├── (existing files unchanged)
│   │   ├── workspace_selector.js       # NEW
│   │   ├── export_progress.js          # NEW
│   │   └── proposal_review.js          # NEW
│   └── xml/
│       ├── (existing files unchanged)
│       ├── workspace_selector.xml      # NEW
│       ├── export_progress.xml         # NEW
│       └── proposal_review.xml         # NEW
└── docs/
    └── phase2_blueprint/              # THIS DOCUMENT SET
```

## Key Architectural Decisions

### Decision 1: Single Addon, Not Multiple Modules

**Choice**: All Phase 2 models and tools live inside `ai_analyst`, not in separate addons.

**Rationale**: The workspaces share a single gateway, provider layer, and tool registry. Splitting into `ai_analyst_sales`, `ai_analyst_buying`, etc. would create circular dependencies and duplicated provider configs. Workspaces are a *configuration* layer on top of the shared engine.

### Decision 2: Workspace = Configuration, Not Code Branch

**Choice**: Workspaces are data records (`ai.analyst.workspace`), not Python classes or separate modules.

**Rationale**: Adding a new workspace (e.g., Finance) should require only creating a record and assigning tools + groups — no code changes, no module upgrade.

### Decision 3: Direct Model Routing Over External Proxies

**Choice**: Route models inside `ai.analyst.model.router`, not via OpenRouter or LiteLLM.

**Rationale**: Full control over routing logic, no external dependency, no additional latency, deterministic behavior. See `08_model_routing_strategy.md` for detailed comparison.

### Decision 4: Async Exports via ir.cron, Not Celery/Redis

**Choice**: Export jobs use Odoo's built-in `ir.cron` for background processing and `ir.attachment` for file delivery.

**Rationale**: No new infrastructure. Odoo workers already handle cron jobs. Export jobs are infrequent enough that dedicated workers are unnecessary. The job model tracks state, progress, and errors.
