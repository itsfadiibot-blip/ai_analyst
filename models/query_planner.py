# -*- coding: utf-8 -*-
import re

from odoo import api, models


class AiAnalystQueryPlanner(models.AbstractModel):
    _name = 'ai.analyst.query.planner'
    _description = 'AI Analyst Query Planner'

    @api.model
    def plan(self, user, question, conversation_context=None, tier='cheap'):
        q = (question or '').strip()
        terms = [t for t in re.split(r'[^a-zA-Z0-9_]+', q) if len(t) > 2]
        resolver = self.env['ai.analyst.field.resolver']
        resolved = []
        for term in terms[:8]:
            resolved.extend(resolver.resolve(term))

        primary_model = 'sale.order.line'
        if resolved:
            primary_model = resolved[0]['model']

        fields = []
        for r in resolved[:4]:
            if r['model'] == primary_model:
                fields.append(r['field_path'])
        if not fields:
            fields = ['id']

        method = 'search_read'
        if any(k in q.lower() for k in ['count', 'how many', 'number of']):
            method = 'search_count'
        if any(k in q.lower() for k in ['by ', 'group', 'per ']):
            method = 'read_group'

        step = {
            'id': 'step_1',
            'model': primary_model,
            'method': method,
            'domain': [],
            'fields': fields,
            'group_by': [fields[0]] if method == 'read_group' else [],
            'aggregations': [{'field': 'id', 'op': 'count', 'alias': 'count'}] if method == 'read_group' else [],
            'limit': 80,
            'order': 'id desc',
        }

        return {
            'steps': [step],
            'computed_metrics': [],
            'output_format': 'table' if method != 'search_count' else 'single_value',
            'meta': {
                'planner_tier': tier,
                'resolved_fields': resolved,
            }
        }
