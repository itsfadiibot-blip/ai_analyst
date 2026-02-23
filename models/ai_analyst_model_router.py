# -*- coding: utf-8 -*-
"""AI Analyst Model Router - Intelligent model selection for cost optimization.

Routes queries to appropriate AI model (Haiku/Sonnet/Opus) based on complexity.
Implements escalation when cheaper models struggle.
"""
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class AiAnalystModelRouter(models.AbstractModel):
    _name = 'ai.analyst.model.router'
    _description = 'AI Model Router for Cost Optimization'

    def classify_complexity(self, message, conversation_history):
        """Deterministic complexity classification.

        Returns: 'cheap', 'standard', or 'premium'
        """
        text = (message or '').lower().strip()
        history_len = len(conversation_history or [])

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
            # Sell-through and retail intelligence
            any(kw in text for kw in [
                'sell-through', 'sell through', 'coverage', 'velocity',
                'dead stock', 'reorder', 'slow moving',
            ]),
        ]
        if sum(standard_signals) >= 2:
            return 'standard'

        # ── CHEAP: everything else (simple lookups, single metrics) ──
        return 'cheap'

    def select_provider(self, user, workspace, message, conversation_history):
        """Select the best provider for this query.

        Resolution order:
        1. Classify complexity → tier
        2. Find active providers in that tier
        3. Select by priority (lowest number wins)
        4. If no provider in tier, escalate to next tier
        5. If all fail, use default provider
        """
        tier = self.classify_complexity(message, conversation_history)
        company_id = user.company_id.id
        Provider = self.env['ai.analyst.provider.config']

        _logger.info(f'Router classified query as: {tier}')

        provider = Provider.search([
            ('is_active', '=', True),
            ('cost_tier', '=', tier),
            ('company_id', 'in', [company_id, False]),
        ], order='priority asc, sequence asc, id asc', limit=1)

        if not provider:
            # Escalate: cheap → standard → premium
            escalation = {'cheap': 'standard', 'standard': 'premium'}
            next_tier = escalation.get(tier)
            if next_tier:
                _logger.info(f'No provider for {tier}, escalating to {next_tier}')
                provider = Provider.search([
                    ('is_active', '=', True),
                    ('cost_tier', '=', next_tier),
                    ('company_id', 'in', [company_id, False]),
                ], order='priority asc, sequence asc, id asc', limit=1)

        if not provider:
            # Ultimate fallback: default provider
            _logger.warning('No tier-specific provider found, using default')
            provider = Provider.get_default_provider(company_id)

        if provider:
            _logger.info(f'Selected provider: {provider.model_name} (tier: {provider.cost_tier})')

        return provider

    def should_escalate(self, provider_response, tool_results, original_tier):
        """Check if we need to re-run with a stronger model.

        Escalation triggers (all deterministic, no LLM call):
        1. High tool call failure rate
        2. Empty response
        3. Model confusion markers
        4. Tool call thrashing
        5. Invalid tool calls
        """
        if original_tier == 'premium':
            return False  # Already at max

        escalation_reasons = []

        # 1. Tool call failure rate
        if tool_results:
            failures = sum(1 for r in tool_results if not r.get('success', True))
            if len(tool_results) and (failures / len(tool_results)) > 0.5:
                escalation_reasons.append('high_tool_failure_rate')

        # 2. No tool calls when expected (model confused)
        if not getattr(provider_response, 'tool_calls', None) and not getattr(provider_response, 'content', None):
            escalation_reasons.append('empty_response')

        # 3. Model explicitly says it can't handle the query
        content = (getattr(provider_response, 'content', None) or '').lower()
        if content:
            confusion_markers = [
                "i'm not sure how to", "i cannot determine",
                "i don't have enough", "this is beyond",
                "i need more context", "ambiguous",
            ]
            if any(marker in content for marker in confusion_markers):
                escalation_reasons.append('model_confusion')

        # 4. Too many tool calls (model is thrashing)
        tool_calls = getattr(provider_response, 'tool_calls', None) or []
        max_for_tier = {'cheap': 3, 'standard': 6}
        if len(tool_calls) >= max_for_tier.get(original_tier, 8):
            escalation_reasons.append('tool_call_thrashing')

        # 5. Invalid tool calls (hallucinated tool names or bad params)
        from odoo.addons.ai_analyst.tools.registry import get_available_tools_for_user
        available_tools = get_available_tools_for_user(self.env.user)

        for tc in tool_calls:
            if tc.name not in available_tools:
                escalation_reasons.append('hallucinated_tool')
                break
            tool = available_tools[tc.name]
            try:
                tool.validate_params(tc.parameters or {})
            except Exception:
                escalation_reasons.append('invalid_tool_params')
                break

        if escalation_reasons:
            _logger.info(f'Escalation triggered: {", ".join(escalation_reasons)}')
            return True
        return False

    def _get_escalation_provider(self, provider_config):
        """Get the provider to escalate to.

        Returns escalation target or next tier provider.
        """
        if not provider_config:
            return self.env['ai.analyst.provider.config']

        company_id = provider_config.company_id.id if provider_config.company_id else False
        Provider = self.env['ai.analyst.provider.config']

        # First, check for explicit escalation target
        explicit = Provider.search([
            ('is_active', '=', True),
            ('is_escalation_target', '=', True),
            ('company_id', 'in', [company_id, False]),
        ], order='priority asc, sequence asc, id asc', limit=1)
        if explicit:
            return explicit

        # Otherwise, escalate to next tier
        next_tier = {'cheap': 'standard', 'standard': 'premium'}.get(provider_config.cost_tier)
        if next_tier:
            candidate = Provider.search([
                ('is_active', '=', True),
                ('cost_tier', '=', next_tier),
                ('company_id', 'in', [company_id, False]),
            ], order='priority asc, sequence asc, id asc', limit=1)
            if candidate:
                return candidate

        # Final fallback
        return Provider.get_default_provider(company_id)
