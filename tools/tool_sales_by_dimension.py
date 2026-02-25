# -*- coding: utf-8 -*-
import re
from datetime import datetime

from odoo.exceptions import ValidationError

from .base_tool import BaseTool
from .registry import register_tool


@register_tool
class SalesByDimensionTool(BaseTool):
    name = 'get_sales_by_dimension'
    description = 'Get sales grouped by configurable dimensions with synonym-aware filters.'
    parameters_schema = {
        'type': 'object',
        'properties': {
            'date_from': {'type': 'string', 'format': 'date'},
            'date_to': {'type': 'string', 'format': 'date'},
            'dimension_codes': {
                'type': 'array',
                'items': {'type': 'string'},
                'description': 'Dimension codes to group by, e.g. ["brand", "category"]',
            },
            'filters': {
                'type': 'object',
                'description': 'Dimension filters keyed by dimension code. Values can be string or list.',
                'default': {},
            },
        },
        'required': ['date_from', 'date_to', 'dimension_codes'],
    }

    def execute(self, env, user, params):
        # Use environment user-switch API compatible with this Odoo runtime.
        user_id = user.id if hasattr(user, 'id') else int(user)
        env = env(user=user_id)
        date_from = params['date_from']
        date_to = params['date_to']
        dimension_codes = params.get('dimension_codes') or []
        filters = params.get('filters') or {}

        self._validate_date_range(date_from, date_to)

        Dimension = env['ai.analyst.dimension']
        dims = Dimension.search([
            ('is_active', '=', True),
            ('code', 'in', dimension_codes),
            '|', ('company_id', '=', False), ('company_id', 'in', user.company_ids.ids),
        ])
        dim_map = {d.code: d for d in dims}
        if any(code not in dim_map for code in dimension_codes):
            missing = [code for code in dimension_codes if code not in dim_map]
            raise ValidationError(f'Unknown or inactive dimension(s): {", ".join(missing)}')

        SaleLine = env['sale.order.line']
        domain = [
            ('order_id.state', 'in', ['sale', 'done']),
            ('order_id.company_id', '=', user.company_id.id),
            ('order_id.date_order', '>=', f'{date_from} 00:00:00'),
            ('order_id.date_order', '<=', f'{date_to} 23:59:59'),
        ]

        resolved_filters = {}
        for code, raw in filters.items():
            dimension = dim_map.get(code)
            if not dimension:
                continue
            values = raw if isinstance(raw, list) else [raw]
            canonical_values = []
            for v in values:
                canonical_values.append(self._resolve_synonym(env, dimension, str(v or '')))
            canonical_values = [v for v in canonical_values if v]
            if not canonical_values:
                continue
            domain += self._build_value_domain(dimension.field_name, canonical_values)
            resolved_filters[code] = canonical_values

        groupby = [dim_map[code].field_name for code in dimension_codes]
        rg_fields = [f'{g}:count' for g in groupby] + ['price_subtotal:sum', 'product_uom_qty:sum']
        rows = SaleLine.read_group(domain, rg_fields, groupby, lazy=False)

        data = []
        for row in rows:
            dims_out = {}
            for code in dimension_codes:
                field_name = dim_map[code].field_name
                value = row.get(field_name)
                if isinstance(value, (tuple, list)) and len(value) >= 2:
                    dims_out[code] = value[1]
                else:
                    dims_out[code] = value or 'Undefined'
            data.append({
                'dimensions': dims_out,
                'sales': round(row.get('price_subtotal', 0.0) or 0.0, 2),
                'quantity': round(row.get('product_uom_qty', 0.0) or 0.0, 2),
                'line_count': row.get('__count', 0),
            })

        return {
            'period': {'from': date_from, 'to': date_to},
            'grouped_by': dimension_codes,
            'resolved_filters': resolved_filters,
            'rows': data,
        }

    def _resolve_synonym(self, env, dimension, value):
        value_l = (value or '').strip().lower()
        if not value_l:
            return ''
        synonyms = env['ai.analyst.dimension.synonym'].search([
            ('dimension_id', '=', dimension.id),
            ('is_active', '=', True),
        ], order='priority asc, id asc')
        for s in synonyms:
            term = (s.synonym or '').strip()
            if not term:
                continue
            term_l = term.lower()
            if s.match_type == 'exact' and value_l == term_l:
                return s.canonical_value
            if s.match_type == 'prefix' and value_l.startswith(term_l):
                return s.canonical_value
            if s.match_type == 'contains' and term_l in value_l:
                return s.canonical_value
            if s.match_type == 'regex' and re.search(term, value, flags=re.IGNORECASE):
                return s.canonical_value
        return value

    def _build_value_domain(self, field_name, values):
        if not values:
            return []
        if len(values) == 1:
            return [(field_name, '=ilike', values[0])]
        domain = []
        for _ in range(len(values) - 1):
            domain.append('|')
        for value in values:
            domain.append((field_name, '=ilike', value))
        return domain

    def _validate_date_range(self, date_from, date_to):
        start = datetime.strptime(date_from, '%Y-%m-%d').date()
        end = datetime.strptime(date_to, '%Y-%m-%d').date()
        if end < start:
            raise ValidationError('date_to must be greater than or equal to date_from.')
        if (end - start).days > 730:
            raise ValidationError('Date range cannot exceed 730 days.')
