# -*- coding: utf-8 -*-
import json

from odoo import api, fields, models


class AiAnalystComputedMetric(models.Model):
    _name = 'ai.analyst.computed.metric'
    _description = 'AI Analyst Computed Metric'

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    formula = fields.Text(required=True)
    description = fields.Text()
    required_inputs = fields.Text(default='[]')
    output_format = fields.Selection([
        ('percentage', 'Percentage'),
        ('number', 'Number'),
        ('currency', 'Currency'),
    ], default='number', required=True)
    synonyms = fields.Text()
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('metric_code_uniq', 'unique(code)', 'Metric code must be unique.'),
    ]

    @api.model
    def compute(self, code, inputs_dict):
        rec = self.search([('code', '=', code), ('active', '=', True)], limit=1)
        if not rec:
            return None
        safe_locals = dict(inputs_dict or {})
        try:
            return eval(rec.formula, {'__builtins__': {}}, safe_locals)
        except Exception:
            return None

    @api.model
    def get_registry_prompt(self):
        rows = []
        for m in self.search([('active', '=', True)]):
            rows.append('%s: %s | inputs=%s' % (m.code, m.formula, m.required_inputs or '[]'))
        return '\n'.join(rows)

    @api.model
    def seed_defaults(self):
        defaults = [
            ('sell_through', 'sold_qty / (sold_qty + current_stock) if (sold_qty + current_stock) else 0', 'percentage'),
            ('stock_coverage_days', 'current_stock / avg_daily_sales if avg_daily_sales else 0', 'number'),
            ('inventory_turn', 'cogs_period / avg_inventory_value if avg_inventory_value else 0', 'number'),
            ('gross_margin_pct', '((revenue - cogs) / revenue * 100) if revenue else 0', 'percentage'),
            ('return_rate', '(returned_qty / sold_qty * 100) if sold_qty else 0', 'percentage'),
        ]
        for code, formula, fmt in defaults:
            if not self.search_count([('code', '=', code)]):
                self.create({
                    'name': code.replace('_', ' ').title(),
                    'code': code,
                    'formula': formula,
                    'required_inputs': json.dumps([]),
                    'output_format': fmt,
                })
