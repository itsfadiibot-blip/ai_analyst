# 08 — Model Routing Strategy

## Goal

Run the cheapest model that can handle the query. Escalate to more capable (expensive) models only when needed. No user-visible latency or quality degradation for simple queries.

## Routing Architecture

### `ai.analyst.model.router` (AbstractModel)

```
_name = 'ai.analyst.model.router'
_description = 'AI Model Router'

No stored fields — this is pure logic.

Key Methods:
    select_provider(user, workspace, message, conversation_history) -> provider_config
    classify_complexity(message, conversation_history) -> tier
    should_escalate(provider_response, tool_results) -> bool
```

## Cost Tiers

| Tier | Use Case | Example Models | Cost Factor |
|---|---|---|---|
| **cheap** | Simple analytics, single-tool queries, clear intent | Claude Haiku, GPT-4o-mini, Gemini Flash | 1x |
| **standard** | Multi-step reasoning, dimension resolution, comparisons | Claude Sonnet, GPT-4o | 5-10x |
| **premium** | Ambiguous queries, action proposals, complex multi-tool chains | Claude Opus, GPT-4-turbo, o1 | 20-50x |

## Provider Config Extensions

```python
# ai.analyst.provider.config gains:
cost_tier           Selection   [('cheap','Cheap'), ('standard','Standard'), ('premium','Premium')]
                                default='standard'
capability_tags     Char        Comma-separated: "analytics,reasoning,actions"
max_tool_calls      Integer     Override per-provider (cheap models: 3, premium: 15)
is_escalation_target Boolean    default=False   Can this provider be escalated to?
priority            Integer     default=10      Lower = preferred within same tier
```

## Complexity Classification Algorithm

```python
def classify_complexity(self, message, conversation_history):
    """Deterministic complexity classification. No LLM call needed.

    Returns: 'cheap', 'standard', or 'premium'
    """
    text = message.lower().strip()
    history_len = len(conversation_history)

    # ── PREMIUM indicators (action-oriented, ambiguous, complex) ──
    premium_signals = [
        # Action/write intent
        any(kw in text for kw in [
            'create', 'make', 'generate po', 'place order', 'reorder',
            'purchase order', 'buy', 'replenish', 'adjust',
            'suggest and create', 'auto-order',
        ]),
        # High ambiguity
        any(kw in text for kw in [
            'what should', 'recommend', 'advise', 'strategy',
            'optimize', 'what would you', 'best approach',
        ]),
        # Multi-domain reasoning
        len([kw for kw in ['sales', 'stock', 'purchase', 'pos', 'margin',
                            'velocity', 'coverage', 'dead stock']
             if kw in text]) >= 3,
        # Complex conditionals
        any(kw in text for kw in [
            'if then', 'depending on', 'correlat', 'regress',
            'forecast', 'predict', 'anomal',
        ]),
    ]
    if sum(premium_signals) >= 2:
        return 'premium'

    # ── STANDARD indicators (multi-step, comparisons, dimensions) ──
    standard_signals = [
        # Comparison queries
        any(kw in text for kw in [
            'compare', 'vs', 'versus', 'difference', 'trend',
            'over time', 'month over month', 'yoy', 'year over year',
        ]),
        # Multi-dimension
        len([kw for kw in ['brand', 'gender', 'category', 'season',
                            'color', 'age group', 'size']
             if kw in text]) >= 2,
        # Follow-up in conversation (needs context understanding)
        history_len >= 4,
        # Aggregation complexity
        any(kw in text for kw in [
            'breakdown', 'group by', 'segment', 'cohort',
            'top and bottom', 'winners and losers',
        ]),
        # Buying intelligence
        any(kw in text for kw in [
            'sell-through', 'sell through', 'coverage', 'velocity',
            'dead stock', 'reorder', 'slow moving',
        ]),
    ]
    if sum(standard_signals) >= 2:
        return 'standard'

    # ── CHEAP: everything else (simple lookups, single metrics) ──
    return 'cheap'
```

## Provider Selection

```python
def select_provider(self, user, workspace, message, conversation_history):
    """Select the best provider for this query.

    Resolution order:
    1. Classify complexity → tier
    2. Find active providers in that tier
    3. Select by priority (lowest number wins)
    4. If no provider in tier, escalate to next tier
    5. If all fail, use default provider (existing fallback)
    """
    tier = self.classify_complexity(message, conversation_history)
    company_id = user.company_id.id

    provider = self.env['ai.analyst.provider.config'].search([
        ('is_active', '=', True),
        ('cost_tier', '=', tier),
        ('company_id', 'in', [company_id, False]),
    ], order='priority asc', limit=1)

    if not provider:
        # Escalate: cheap → standard → premium → default
        escalation = {'cheap': 'standard', 'standard': 'premium'}
        next_tier = escalation.get(tier)
        if next_tier:
            provider = self.env['ai.analyst.provider.config'].search([
                ('is_active', '=', True),
                ('cost_tier', '=', next_tier),
                ('company_id', 'in', [company_id, False]),
            ], order='priority asc', limit=1)

    if not provider:
        # Ultimate fallback: default provider
        provider = self.env['ai.analyst.provider.config'].get_default_provider(company_id)

    return provider
```

## Runtime Escalation

After the cheap model responds, the gateway checks if the response quality is sufficient:

```python
def should_escalate(self, provider_response, tool_results, original_tier):
    """Check if we need to re-run with a stronger model.

    Escalation triggers (all deterministic, no LLM call):
    """
    if original_tier == 'premium':
        return False  # Already at max

    escalation_reasons = []

    # 1. Tool call failure rate
    if tool_results:
        failures = sum(1 for r in tool_results if not r.get('success', True))
        if failures / len(tool_results) > 0.5:
            escalation_reasons.append('high_tool_failure_rate')

    # 2. No tool calls when expected (model confused)
    if not provider_response.tool_calls and not provider_response.content:
        escalation_reasons.append('empty_response')

    # 3. Model explicitly says it can't handle the query
    if provider_response.content:
        content_lower = provider_response.content.lower()
        confusion_markers = [
            "i'm not sure how to", "i cannot determine",
            "i don't have enough", "this is beyond",
            "i need more context", "ambiguous",
        ]
        if any(marker in content_lower for marker in confusion_markers):
            escalation_reasons.append('model_confusion')

    # 4. Too many tool calls (model is thrashing)
    max_for_tier = {'cheap': 3, 'standard': 6}
    if len(provider_response.tool_calls) >= max_for_tier.get(original_tier, 8):
        escalation_reasons.append('tool_call_thrashing')

    # 5. Invalid tool calls (hallucinated tool names or bad params)
    for tc in provider_response.tool_calls:
        tool = get_tool(tc.name)
        if not tool:
            escalation_reasons.append('hallucinated_tool')
            break
        try:
            tool.validate_params(tc.parameters)
        except Exception:
            escalation_reasons.append('invalid_tool_params')
            break

    if escalation_reasons:
        _logger.info("Escalation triggered: %s", escalation_reasons)
        return True
    return False
```

### Escalation Execution

```python
# In gateway.process_message():
router = self.env['ai.analyst.model.router']
provider_config = router.select_provider(user, workspace, message, history)
provider = get_provider(provider_config)

response = provider.chat(messages, tools)

if router.should_escalate(response, tool_results, provider_config.cost_tier):
    # Re-run with next tier
    escalated_config = router._get_escalation_provider(provider_config)
    if escalated_config:
        _logger.info("Escalating from %s to %s",
                     provider_config.model_name, escalated_config.model_name)
        # Audit the escalation
        self._log_audit(user, 'model_escalation', {
            'from_model': provider_config.model_name,
            'to_model': escalated_config.model_name,
            'reason': escalation_reasons,
        })
        provider = get_provider(escalated_config)
        response = provider.chat(messages, tools)
```

## Validation Gates

Before accepting a provider response, validate:

```python
def validate_response(self, response, available_tools):
    """Validate LLM response before acting on it."""
    errors = []

    # 1. Tool calls reference real tools
    for tc in response.tool_calls:
        if tc.name not in available_tools:
            errors.append(f"Unknown tool: {tc.name}")

    # 2. Tool parameters pass schema validation
    for tc in response.tool_calls:
        tool = available_tools.get(tc.name)
        if tool:
            try:
                tool.validate_params(tc.parameters)
            except Exception as e:
                errors.append(f"Invalid params for {tc.name}: {e}")

    # 3. Content is not empty when no tool calls
    if not response.tool_calls and not response.content:
        errors.append("Empty response with no tool calls")

    # 4. Token limits respected
    if response.usage.get('output_tokens', 0) > 8000:
        errors.append("Response exceeds token limit")

    return errors
```

## Cost Controls

### Per-Query Cost Tracking

```python
# After each provider call, log cost estimate
def _estimate_cost(self, provider_config, usage):
    """Estimate cost in USD based on provider pricing."""
    pricing = {
        # Approximate per-1K-token costs
        'claude-haiku': {'input': 0.00025, 'output': 0.00125},
        'claude-sonnet': {'input': 0.003, 'output': 0.015},
        'claude-opus': {'input': 0.015, 'output': 0.075},
        'gpt-4o-mini': {'input': 0.00015, 'output': 0.0006},
        'gpt-4o': {'input': 0.0025, 'output': 0.01},
    }
    model_key = provider_config.model_name.split('-202')[0]  # strip date suffix
    rates = pricing.get(model_key, {'input': 0.003, 'output': 0.015})
    cost = (usage.get('input_tokens', 0) / 1000 * rates['input'] +
            usage.get('output_tokens', 0) / 1000 * rates['output'])
    return round(cost, 6)
```

### Daily Cost Dashboard (Admin)

Aggregate from audit logs: total cost by model, by workspace, by user. Exposed as a pivot view on `ai.analyst.audit.log` with the computed cost field.

## Comparison: OpenRouter vs LiteLLM vs Direct Routing

### OpenRouter

| Aspect | Assessment |
|---|---|
| **What it does** | SaaS proxy that routes to 100+ models. Has "auto" mode that picks model by query. |
| **Pros** | Zero config for multi-model. Auto-routing is tempting. Single API key. |
| **Cons** | External dependency (latency, availability). Auto-routing is opaque — you can't control which model handles which query type. No deterministic tier control. Additional cost markup (~5-15%). Data leaves your infra to a third party. Cannot enforce tool schemas per-tier. |
| **Verdict** | **Not recommended.** Opaque routing defeats cost control. External dependency adds latency and a failure point. |

### LiteLLM (Self-Hosted Proxy)

| Aspect | Assessment |
|---|---|
| **What it does** | Self-hosted proxy that normalizes API calls to 100+ models. Router module supports cost-based routing. |
| **Pros** | Open source. Can be self-hosted. Normalizes API differences. Has router with cost/latency strategies. |
| **Cons** | Requires deploying and maintaining a separate service (Python FastAPI). Another moving part in infrastructure. Router is still basic (round-robin, cost-based, latency-based) — not query-complexity-aware. You'd still need custom classification logic. Adds network hop latency. |
| **Verdict** | **Viable but unnecessary.** The provider abstraction already exists in Phase 1 (`BaseProvider` + `AnthropicProvider` + `OpenAIProvider`). LiteLLM would duplicate this layer while adding infrastructure complexity. |

### Direct Routing in ai_gateway (Recommended)

| Aspect | Assessment |
|---|---|
| **What it does** | Route models inside `ai.analyst.model.router` using deterministic complexity classification. Provider abstraction already handles API differences. |
| **Pros** | Zero external dependencies. Full control over routing logic. Deterministic — you know exactly which model handles what. No additional latency. No infrastructure to deploy/maintain. Complexity classification is domain-specific (buying vs analytics vs actions). Audit logging is native. Cost tracking is native. |
| **Cons** | Must maintain provider implementations (already done for Anthropic + OpenAI). Adding new providers requires code (but this is intentional — each provider needs Odoo-specific tool schema mapping). |
| **Verdict** | **Recommended.** Leverages existing Phase 1 architecture. Adds routing as a thin classification layer. No new infrastructure. Full control. |

### Decision Matrix

| Criterion | OpenRouter | LiteLLM | Direct (Recommended) |
|---|---|---|---|
| Infrastructure complexity | None (SaaS) | Medium (deploy proxy) | None (in-addon) |
| Routing control | Low (opaque) | Medium (basic strategies) | High (domain-specific) |
| Latency overhead | +100-300ms | +20-50ms | 0ms |
| Cost markup | 5-15% | 0% | 0% |
| Data sovereignty | External | Self-hosted | Internal |
| Failure modes | External SaaS down | Proxy down | Provider API down only |
| Odoo integration | None | None | Native |
| Audit integration | Manual | Manual | Native |

## Recommended Provider Configuration

```xml
<!-- Cheap tier: Claude Haiku for simple analytics -->
<record model="ai.analyst.provider.config" id="provider_haiku">
    <field name="name">Claude Haiku (Cheap)</field>
    <field name="provider_type">anthropic</field>
    <field name="model_name">claude-haiku-4-5-20251001</field>
    <field name="cost_tier">cheap</field>
    <field name="priority">10</field>
    <field name="temperature">0.1</field>
    <field name="max_tokens">4096</field>
    <field name="max_tool_calls">3</field>
    <field name="is_active">True</field>
</record>

<!-- Standard tier: Claude Sonnet for multi-step reasoning -->
<record model="ai.analyst.provider.config" id="provider_sonnet">
    <field name="name">Claude Sonnet (Standard)</field>
    <field name="provider_type">anthropic</field>
    <field name="model_name">claude-sonnet-4-5-20250929</field>
    <field name="cost_tier">standard</field>
    <field name="priority">10</field>
    <field name="temperature">0.1</field>
    <field name="max_tokens">4096</field>
    <field name="max_tool_calls">8</field>
    <field name="is_active">True</field>
    <field name="is_default">True</field>
</record>

<!-- Premium tier: Claude Opus for complex/action queries -->
<record model="ai.analyst.provider.config" id="provider_opus">
    <field name="name">Claude Opus (Premium)</field>
    <field name="provider_type">anthropic</field>
    <field name="model_name">claude-opus-4-6</field>
    <field name="cost_tier">premium</field>
    <field name="priority">10</field>
    <field name="temperature">0.1</field>
    <field name="max_tokens">8192</field>
    <field name="max_tool_calls">15</field>
    <field name="is_active">True</field>
    <field name="is_escalation_target">True</field>
</record>
```

## Expected Cost Impact

With proper routing, estimated cost distribution:

| Query Type | % of Traffic | Tier | Cost per Query |
|---|---|---|---|
| Simple stats ("revenue this month") | 60% | Cheap | ~$0.002 |
| Comparisons, dimensions | 25% | Standard | ~$0.02 |
| Complex reasoning, proposals | 10% | Premium | ~$0.10 |
| Escalations (cheap→standard) | 5% | Standard | ~$0.025 |

**Estimated 70-80% cost reduction** vs running Opus/Sonnet for all queries.
