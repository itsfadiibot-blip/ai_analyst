# -*- coding: utf-8 -*-
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class AiAnalystModelRouter(models.AbstractModel):
    _name = 'ai.analyst.model.router'
    _description = 'AI Model Router'

    def classify_complexity(self, message, conversation_history):
        """Deterministic complexity classification.

        Returns: cheap | standard | premium
        """
        text = (message or '').lower().strip()
        history_len = len(conversation_history or [])

        premium_signals = [
            any(kw in text for kw in [
                'create', 'make', 'generate po', 'place order', 'reorder',
                'purchase order', 'buy', 'replenish', 'adjust',
                'suggest and create', 'auto-order',
            ]),
            any(kw in text for kw in [
                'what should', 'recommend', 'advise', 'strategy',
                'optimize', 'what would you', 'best approach',
            ]),
            len([kw for kw in ['sales', 'stock', 'purchase', 'pos', 'margin',
                               'velocity', 'coverage', 'dead stock']
                 if kw in text]) >= 3,
            any(kw in text for kw in [
                'if then', 'depending on', 'correlat', 'regress',
                'forecast', 'predict', 'anomal',
            ]),
        ]
        if sum(premium_signals) >= 2:
            return 'premium'

        standard_signals = [
            any(kw in text for kw in [
                'compare', 'vs', 'versus', 'difference', 'trend',
                'over time', 'month over month', 'yoy', 'year over year',
            ]),
            len([kw for kw in ['brand', 'gender', 'category', 'season',
                               'color', 'age group', 'size']
                 if kw in text]) >= 2,
            history_len >= 4,
            any(kw in text for kw in [
                'breakdown', 'group by', 'segment', 'cohort',
                'top and bottom', 'winners and losers',
            ]),
            any(kw in text for kw in [
                'sell-through', 'sell through', 'coverage', 'velocity',
                'dead stock', 'reorder', 'slow moving',
            ]),
        ]
        if sum(standard_signals) >= 2:
            return 'standard'

        return 'cheap'

    def select_provider(self, user, workspace, message, conversation_history):
        """Select provider by complexity tier, then priority, then fallback."""
        tier = self.classify_complexity(message, conversation_history)
        company_id = user.company_id.id
        Provider = self.env['ai.analyst.provider.config']

        provider = Provider.search([
            ('is_active', '=', True),
            ('cost_tier', '=', tier),
            ('company_id', 'in', [company_id, False]),
        ], order='priority asc, sequence asc, id asc', limit=1)

        if not provider:
            escalation = {'cheap': 'standard', 'standard': 'premium'}
            next_tier = escalation.get(tier)
            if next_tier:
                provider = Provider.search([
                    ('is_active', '=', True),
                    ('cost_tier', '=', next_tier),
                    ('company_id', 'in', [company_id, False]),
                ], order='priority asc, sequence asc, id asc', limit=1)

        if not provider:
            provider = Provider.get_default_provider(company_id)

        return provider

    def should_escalate(self, provider_response, tool_results, original_tier):
        """Check deterministic escalation conditions."""
        if original_tier == 'premium':
            return False

        escalation_reasons = []

        if tool_results:
            failures = sum(1 for r in tool_results if not r.get('success', True))
            if len(tool_results) and (failures / len(tool_results)) > 0.5:
                escalation_reasons.append('high_tool_failure_rate')

        if not getattr(provider_response, 'tool_calls', None) and not getattr(provider_response, 'content', None):
            escalation_reasons.append('empty_response')

        content = (getattr(provider_response, 'content', None) or '').lower()
        if content:
            confusion_markers = [
                "i'm not sure how to", "i cannot determine",
                "i don't have enough", "this is beyond",
                "i need more context", "ambiguous",
            ]
            if any(marker in content for marker in confusion_markers):
                escalation_reasons.append('model_confusion')

        tool_calls = getattr(provider_response, 'tool_calls', None) or []
        max_for_tier = {'cheap': 3, 'standard': 6}
        if len(tool_calls) >= max_for_tier.get(original_tier, 8):
            escalation_reasons.append('tool_call_thrashing')

        from odoo.addons.ai_analyst.tools.registry import get_tool
        for tc in tool_calls:
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
            _logger.info('Escalation triggered: %s', escalation_reasons)
            return True
        return False

    def _get_escalation_provider(self, provider_config):
        """Escalate to configured escalation target or next tier provider."""
        if not provider_config:
            return self.env['ai.analyst.provider.config']

        company_id = provider_config.company_id.id
        Provider = self.env['ai.analyst.provider.config']

        explicit = Provider.search([
            ('is_active', '=', True),
            ('is_escalation_target', '=', True),
            ('company_id', 'in', [company_id, False]),
        ], order='priority asc, sequence asc, id asc', limit=1)
        if explicit:
            return explicit

        next_tier = {'cheap': 'standard', 'standard': 'premium'}.get(provider_config.cost_tier)
        if next_tier:
            candidate = Provider.search([
                ('is_active', '=', True),
                ('cost_tier', '=', next_tier),
                ('company_id', 'in', [company_id, False]),
            ], order='priority asc, sequence asc, id asc', limit=1)
            if candidate:
                return candidate

        return Provider.get_default_provider(company_id)
