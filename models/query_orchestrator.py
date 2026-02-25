# -*- coding: utf-8 -*-
from odoo import api, models


class AiAnalystQueryOrchestrator(models.AbstractModel):
    _name = 'ai.analyst.query.orchestrator'
    _description = 'AI Analyst Query Orchestrator'

    @api.model
    def run(self, user, plan):
        results = {}
        for step in plan.get('steps', []):
            results[step['id']] = self._run_step(user, step)

        metric_values = {}
        metric_model = self.env['ai.analyst.computed.metric']
        for metric in plan.get('computed_metrics', []):
            inputs = {}
            for key, path in (metric.get('inputs') or {}).items():
                # path format: step_id.field
                step_id, _, field = (path or '').partition('.')
                value = 0
                data = results.get(step_id)
                if isinstance(data, list) and data:
                    value = data[0].get(field, 0)
                elif isinstance(data, dict):
                    value = data.get(field, 0)
                inputs[key] = value
            metric_values[metric.get('code')] = metric_model.compute(metric.get('code'), inputs)

        return {'steps': results, 'metrics': metric_values}

    def _run_step(self, user, step):
        # Bug #4 fix: Pass user.id (int) instead of user recordset for Odoo 17 compatibility
        user_id = user.id if hasattr(user, 'id') else int(user)
        model = self.env[step['model']].with_user(user_id)
        domain = step.get('domain') or []
        method = step.get('method')
        if method == 'search_count':
            return {'count': model.search_count(domain)}
        if method == 'read_group':
            agg_fields = []
            for a in step.get('aggregations', []):
                if a.get('op') == 'count':
                    agg_fields.append('__count')
                else:
                    agg_fields.append('%s:%s' % (a['field'], a['op']))
            return model.read_group(domain, agg_fields + step.get('group_by', []), step.get('group_by', []), limit=step.get('limit', 80), lazy=False)
        return model.search_read(domain, step.get('fields', []), limit=step.get('limit', 80), order=step.get('order'))
