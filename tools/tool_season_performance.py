# -*- coding: utf-8 -*-
"""Tool: get_season_performance - Compare sales performance between seasons.

FIXED: Now uses x_studio_many2many_field_IXz60 → x_product_tags for season matching.
compare_to_season is now OPTIONAL.
"""
from datetime import date, timedelta

from odoo.exceptions import ValidationError

from .base_tool import BaseTool
from .registry import register_tool


@register_tool
class SeasonPerformanceTool(BaseTool):
    name = 'get_season_performance'
    description = (
        'Compare sales performance between two seasons, or analyze a single season. '
        'Groups sales by optional dimensions like brand, category, etc.'
    )
    parameters_schema = {
        'type': 'object',
        'properties': {
            'season_code': {
                'type': 'string',
                'description': 'Primary season to analyze (e.g. FW25)',
            },
            'compare_to_season': {
                'type': 'string',
                'description': 'Optional second season to compare against (e.g. SS25)',
            },
            'dimensions': {
                'type': 'array',
                'items': {'type': 'string'},
                'default': [],
                'description': 'Dimensions to group by (brand, category, etc.)',
            },
        },
        'required': ['season_code'],
    }

    def execute(self, env, user, params):
        env = env.with_user(user)
        season_code = (params.get('season_code') or '').strip()
        compare_code = (params.get('compare_to_season') or '').strip()
        dimensions = params.get('dimensions') or []

        if not season_code:
            raise ValidationError('season_code is required')

        # FIXED: Find season tag in x_product_tags
        season_tag = env['x_product_tags'].search([
            ('name', '=ilike', season_code)
        ], limit=1)

        if not season_tag:
            raise ValidationError(f'Season "{season_code}" not found')

        compare_tag = None
        if compare_code:
            compare_tag = env['x_product_tags'].search([
                ('name', '=ilike', compare_code)
            ], limit=1)
            if not compare_tag:
                raise ValidationError(f'Season "{compare_code}" not found')

        # Get dimension configs
        Dimension = env['ai.analyst.dimension']
        dim_map = {
            d.code: d for d in Dimension.search([
                ('is_active', '=', True),
                ('code', 'in', dimensions),
                '|', ('company_id', '=', False), ('company_id', 'in', user.company_ids.ids),
            ])
        }

        # Base domain for sales
        base_domain = [
            ('order_id.state', 'in', ['sale', 'done']),
            ('order_id.company_id', '=', user.company_id.id),
            ('order_id.date_order', '>=', f'{(date.today() - timedelta(days=730)).isoformat()} 00:00:00'),
            ('order_id.date_order', '<=', f'{date.today().isoformat()} 23:59:59'),
            ('display_type', '=', False),
        ]

        # FIXED: Build season-specific domains using x_studio_many2many_field_IXz60
        current_domain = base_domain + [
            ('product_id.product_tmpl_id.x_studio_many2many_field_IXz60', 'in', [season_tag.id])
        ]

        # Build groupby fields
        groupby_fields = []
        for d in dimensions:
            if d in dim_map:
                gf = dim_map[d].field_name
                groupby_fields.append(gf)

        fields = ['price_subtotal:sum', 'product_uom_qty:sum']

        SaleLine = env['sale.order.line']
        current = SaleLine.read_group(current_domain, fields, groupby_fields, lazy=False)

        result = {
            'season': season_code,
            'dimensions': dimensions,
            'current': self._shape(groupby_fields, current),
        }

        # Optional comparison
        if compare_tag:
            compare_domain = base_domain + [
                ('product_id.product_tmpl_id.x_studio_many2many_field_IXz60', 'in', [compare_tag.id])
            ]
            previous = SaleLine.read_group(compare_domain, fields, groupby_fields, lazy=False)
            result['compare_to'] = compare_code
            result['previous'] = self._shape(groupby_fields, previous)

        return result

    def _shape(self, groupby_fields, rows):
        """Format read_group results"""
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
