# 03 — Workspaces and RBAC

## Overview

Workspaces are **configuration records** that scope the AI experience for a team: which tools are available, which prompts are suggested, which dashboard is default, and what system prompt context is injected. The underlying engine (gateway, providers, tool registry) is shared.

## Data Model

### `ai.analyst.workspace`

```
_name = 'ai.analyst.workspace'
_description = 'AI Analyst Workspace'

Fields:
    name                Char            required    e.g. "Sales", "Buying"
    code                Char            unique      e.g. "sales", "buying", "pos", "cs"
    description         Text                        Workspace purpose (injected into system prompt)
    icon                Char                        CSS icon class for UI
    sequence            Integer         default=10  Menu ordering
    is_active           Boolean         default=True
    company_id          Many2one        res.company (multi-company)

    # Access
    group_ids           Many2many       res.groups  Who can access this workspace
    manager_group_ids   Many2many       res.groups  Who can manage this workspace's config

    # Tool Scoping
    allowed_tool_ids    Many2many       ai.analyst.workspace.tool.ref
                                        Allowlisted tools for this workspace.
                                        If empty, all user-accessible tools are available.

    # Prompt Packs
    prompt_pack_ids     One2many        ai.analyst.workspace.prompt.pack

    # Dashboard
    default_dashboard_id Many2one      ai.analyst.dashboard

    # System Prompt Context
    system_prompt_extra  Text           Injected after base system prompt.
                                        Contains workspace-specific instructions,
                                        domain knowledge, and dimension hints.

    # Query Budgets
    max_tool_calls      Integer         default=8   Override per workspace
    max_inline_rows     Integer         default=500
    daily_query_limit   Integer         default=0   0 = unlimited
```

### `ai.analyst.workspace.tool.ref`

```
_name = 'ai.analyst.workspace.tool.ref'
_description = 'Workspace Tool Reference'

Fields:
    workspace_id        Many2one        ai.analyst.workspace    required
    tool_name           Char            required    Must match registry key
    is_active           Boolean         default=True
    sequence            Integer         default=10  Ordering in tool list
```

### `ai.analyst.workspace.prompt.pack`

```
_name = 'ai.analyst.workspace.prompt.pack'
_description = 'Workspace Suggested Prompt'

Fields:
    workspace_id        Many2one        ai.analyst.workspace    required
    category            Char            e.g. "Quick Stats", "Deep Dive", "Trends"
    prompt_text         Text            required    The suggested prompt
    description         Char            Short label shown in UI
    sequence            Integer         default=10
    is_active           Boolean         default=True
    icon                Char            Optional icon
```

## Seed Workspaces (data/workspace_data.xml)

### Sales Workspace

```xml
code:           sales
group_ids:      group_ai_user (base access)
system_prompt_extra:
    "You are a sales analyst for an ecommerce company.
     Primary models: sale.order, sale.order.line.
     Key metrics: revenue, AOV, order count, conversion, margin.
     Dimensions: gender, age_group, brand, category, season, color.
     Always consider both online and POS channels unless specified."
allowed_tools:
    get_sales_summary, get_top_sellers, get_margin_summary,
    get_sales_by_dimension, get_season_performance,
    get_pos_vs_online_summary, get_refund_return_summary, export_csv
prompt_pack examples:
    - "Revenue this month vs last month"
    - "Top 10 products by margin this quarter"
    - "Sales by gender and age group, last 30 days"
    - "Which brands are trending up vs down?"
    - "Season FW25 sell-through by category"
```

### Buying Workspace

```xml
code:           buying
group_ids:      group_ai_user + purchase.group_purchase_user
system_prompt_extra:
    "You are a buying/merchandising analyst.
     Focus on inventory velocity, sell-through, stock coverage, dead stock.
     Primary models: sale.order.line, stock.quant, purchase.order.
     Use buying intelligence tools to surface reorder opportunities
     and dead stock risks. Always provide explainable results."
allowed_tools:
    get_buying_velocity, get_dead_stock, get_stock_coverage,
    get_reorder_suggestions, get_inventory_valuation,
    get_stock_aging, get_sales_by_dimension, get_season_performance,
    get_top_sellers, export_csv
prompt_pack examples:
    - "Dead stock: items with zero sales in 90 days and stock > 0"
    - "Stock coverage in weeks for top 50 SKUs"
    - "Sell-through rate for FW25 by brand"
    - "Reorder suggestions for items with < 2 weeks coverage"
    - "Winners: fastest velocity items this season"
```

### POS Workspace

```xml
code:           pos
group_ids:      group_ai_user + point_of_sale.group_pos_user
system_prompt_extra:
    "You are a POS / retail analyst.
     Primary models: pos.order, pos.order.line, pos.session, pos.config.
     Key metrics: revenue, basket size, items per transaction, hourly trends.
     Always filter by POS config (store location) when relevant."
allowed_tools:
    get_pos_summary, get_pos_vs_online_summary,
    get_top_sellers, get_sales_by_dimension,
    get_refund_return_summary, export_csv
prompt_pack examples:
    - "POS sales today by store"
    - "Average basket size this week vs last week"
    - "Top sellers in-store this month"
    - "Hourly sales pattern for Saturday"
```

### Customer Service Workspace

```xml
code:           cs
group_ids:      group_ai_user + (helpdesk.group_helpdesk_user if installed)
system_prompt_extra:
    "You are a customer service analyst.
     Primary models: helpdesk.ticket, sale.order, account.move.
     Key metrics: ticket volume, resolution time, refund rate, CSAT.
     Focus on identifying patterns in complaints and return reasons."
allowed_tools:
    get_helpdesk_summary, get_refund_return_summary,
    get_sales_summary, get_ar_aging, export_csv
prompt_pack examples:
    - "Open tickets by category this week"
    - "Average resolution time trend, last 30 days"
    - "Top refund reasons this month"
    - "Customers with most returns in last 90 days"
```

## How Workspace Context Flows

### Step 1: User selects workspace

The OWL `AiWorkspaceSelector` component in the chat header shows available workspaces (filtered by user's groups). Selection is stored on the conversation record.

```
ai.analyst.conversation gains:
    workspace_id    Many2one    ai.analyst.workspace
```

### Step 2: Gateway reads workspace context

In `ai.analyst.gateway.process_message()`, after loading the conversation:

```python
# Pseudocode — gateway extension
workspace = conversation.workspace_id
if workspace:
    # 1. Filter tools to workspace allowlist
    available_tools = self._get_workspace_tools(workspace, user)
    # 2. Inject workspace system prompt
    system_prompt += "\n\n" + workspace.system_prompt_extra
    # 3. Apply workspace budget overrides
    max_tool_calls = workspace.max_tool_calls or default
    max_inline_rows = workspace.max_inline_rows or default
```

### Step 3: Tool filtering

```python
def _get_workspace_tools(self, workspace, user):
    """Return tools allowed in this workspace AND accessible by this user."""
    if not workspace.allowed_tool_ids:
        # No restriction — return all user-accessible tools
        return get_available_tools_for_user(user)
    allowed_names = workspace.allowed_tool_ids.filtered('is_active').mapped('tool_name')
    all_tools = get_available_tools_for_user(user)
    return {k: v for k, v in all_tools.items() if k in allowed_names}
```

### Step 4: Prompt packs shown in UI

The chat UI's welcome screen shows workspace-specific suggested prompts instead of the generic ones. Loaded via:

```
POST /ai_analyst/workspace/context
Request:  { workspace_id: int }
Response: { prompts: [...], tools: [...], dashboard_id: int }
```

## RBAC Model

### Security Groups (Extended)

The existing three groups remain:

| Group | Implied By | Purpose |
|---|---|---|
| `group_ai_user` | `base.group_user` | Chat access, own data |
| `group_ai_manager` | `group_ai_user` | All users' data, audit logs |
| `group_ai_admin` | `group_ai_manager` | Provider config, workspace config |

Workspace access is **additive** — a user must have BOTH `group_ai_user` AND the workspace's `group_ids` to access it. A user in `purchase.group_purchase_user` + `group_ai_user` can access the Buying workspace.

### Record Rules (New)

```xml
<!-- Users see workspaces they have group access to -->
<record model="ir.rule" id="rule_workspace_user">
    <field name="name">Workspace: User sees permitted workspaces</field>
    <field name="model_id" ref="model_ai_analyst_workspace"/>
    <field name="domain_force">[('is_active','=',True)]</field>
    <!-- Group filtering is done in Python via group_ids check -->
    <field name="groups" eval="[(4, ref('group_ai_user'))]"/>
</record>

<!-- Prompt packs follow workspace access -->
<record model="ir.rule" id="rule_prompt_pack_user">
    <field name="name">Prompt Pack: follows workspace access</field>
    <field name="model_id" ref="model_ai_analyst_workspace_prompt_pack"/>
    <field name="domain_force">[('workspace_id.is_active','=',True)]</field>
    <field name="groups" eval="[(4, ref('group_ai_user'))]"/>
</record>
```

### Workspace Access Check (Python)

```python
def _user_can_access_workspace(self, workspace, user):
    """Check if user has all required groups for this workspace."""
    if not workspace.group_ids:
        return True  # No restriction
    user_group_ids = set(user.groups_id.ids)
    required_group_ids = set(workspace.group_ids.ids)
    return required_group_ids.issubset(user_group_ids)
```

## Menu Structure (Phase 2)

```
AI Analyst (Root)
├── Chat                            (existing, gains workspace selector)
├── Dashboards                      (existing)
├── Reports
│   ├── Saved Reports               (existing)
│   ├── Conversation History        (existing)
│   └── Export Jobs                  (NEW)
├── Proposals                       (NEW — pending approval queue)
└── Administration (Manager+)
    ├── Provider Configuration       (existing, Admin)
    ├── Workspaces                   (NEW, Admin)
    │   ├── Workspace List
    │   └── Prompt Packs
    ├── Dimension Dictionary         (NEW, Admin)
    ├── Season Configuration         (NEW, Admin)
    ├── Query Budgets               (NEW, Admin)
    ├── Audit Logs                  (existing, Manager)
    └── Tool Call Logs              (existing, Manager)
```

## Workspace Switching UX

1. Chat header shows current workspace as a dropdown pill.
2. Switching workspace starts a **new conversation** (workspace context is conversation-scoped).
3. Default workspace is determined by user's primary group:
   - `purchase.group_purchase_user` → Buying
   - `point_of_sale.group_pos_user` → POS
   - Fallback → Sales
4. Users with multiple workspace access can switch freely.
5. Console mode remains a per-user toggle, orthogonal to workspace.
