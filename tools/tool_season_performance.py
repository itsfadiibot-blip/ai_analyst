# -*- coding: utf-8 -*-
from datetime import date, timedelta

from odoo.exceptions import ValidationError

from .base_tool import BaseTool
from .registry import register_tool


@register_tool
class SeasonPerformanceTool(BaseTool):
    name = 'get_season_performance'
    description = 'Compare sales performance between two configured seasons using season tag patterns.'
    parameters_schema = {
        'type': 'object',
        'properties': {
            'season_code': {'type': 'string'},
            'compare_to_season': {'type': 'string'},
            'dimensions': {
                'type': 'array',
                'items': {'type': 'string'},
                'default': [],
            },
        },
        'required': ['season_code', 'compare_to_season'],
    }

    def execute(self, env, user, params):
        # Use environment user-switch API compatible with this Odoo runtime.
        user_id = user.id if hasattr(user, 'id') else int(user)
        env = env(user=user_id)
        season_code = (params.get('season_code') or '').strip()
        compare_code = (params.get('compare_to_season') or '').strip()
        dimensions = params.get('dimensions') or []

        Season = env['ai.analyst.season.config']
        season = Season.search([
            ('code', '=ilike', season_code),
            ('is_active', '=', True),
            '|', ('company_id', '=', False), ('company_id', 'in', user.company_ids.ids),
        ], limit=1)
        compare = Season.search([
            ('code', '=ilike', compare_code),
            ('is_active', '=', True),
            '|', ('company_id', '=', False), ('company_id', 'in', user.company_ids.ids),
        ], limit=1)
        if not season or not compare:
            raise ValidationError('Season code not found in configuration.')

        dim_map = {
            d.code: d for d in env['ai.analyst.dimension'].search([
                ('is_active', '=', True),
                ('code', 'in', dimensions),
                '|', ('company_id', '=', False), ('company_id', 'in', user.company_ids.ids),
            ])
        }

        season_dimension = env['ai.analyst.dimension'].search([
            ('code', '=', 'season'),
            ('is_active', '=', True),
            '|', ('company_id', '=', False), ('company_id', 'in', user.company_ids.ids),
        ], limit=1)
        if not season_dimension:
            raise ValidationError('Season dimension configuration is missing.')

        field_name = season_dimension.field_name
        base_domain = [
            ('order_id.state', 'in', ['sale', 'done']),
            ('order_id.company_id', '=', user.company_id.id),
            ('order_id.date_order', '>=', f'{(date.today() - timedelta(days=730)).isoformat()} 00:00:00'),
            ('order_id.date_order', '<=', f'{date.today().isoformat()} 23:59:59'),
        ]

        current_domain = base_domain + self._season_pattern_domain(season, field_name)
        compare_domain = base_domain + self._season_pattern_domain(compare, field_name)

        groupby_fields = [dim_map[d].field_name for d in dimensions if d in dim_map]
        fields = ['price_subtotal:sum', 'product_uom_qty:sum']

        SaleLine = env['sale.order.line']
        current = SaleLine.read_group(current_domain, fields, groupby_fields, lazy=False)
        previous = SaleLine.read_group(compare_domain, fields, groupby_fields, lazy=False)

        return {
            'season': season.code,
            'compare_to': compare.code,
            'dimensions': dimensions,
            'current': self._shape(groupby_fields, current),
            'previous': self._shape(groupby_fields, previous),
        }

    def _season_pattern_domain(self, season, field_name):
        patterns = season.tag_pattern_ids.filtered(lambda p: p.is_active)
        if not patterns:
            return [(field_name, '=ilike', season.code)]

        domain = []
        pieces = []
        for p in patterns:
            if p.match_type == 'exact':
                pieces.append((field_name, '=ilike', p.pattern))
            elif p.match_type == 'prefix':
                pieces.append((field_name, '=ilike', f'{p.pattern}%'))
            elif p.match_type == 'contains':
                pieces.append((field_name, 'ilike', p.pattern))
            else:  # regex fallback: broad ilike guard
                cleaned = ''.join(ch for ch in p.pattern if ch.isalnum())
                pieces.append((field_name, 'ilike', cleaned or p.pattern))

        for _ in range(len(pieces) - 1):
            domain.append('|')
        domain.extend(pieces)
        return domain

    def _shape(self, groupby_fields, rows):
        out = []
        for row in rows:
            dims = {}
            for f in groupby_fields:
                value = row.get(f)
                if isinstance(value, (tuple, list)) and len(value) >= 2:
                    dims[f] = value[1]
                else:
                    dims[f] = value or 'Undefined'
            out.append({
                'dimensions': dims,
                'sales': round(row.get('price_subtotal', 0.0) or 0.0, 2),
                'quantity': round(row.get('product_uom_qty', 0.0) or 0.0, 2),
            })
        return out
