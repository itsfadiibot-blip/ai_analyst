# -*- coding: utf-8 -*-
"""Tool: get_margin_summary — Profit margin analysis by product, category, time, or salesperson."""
import logging

from .base_tool import BaseTool
from .registry import register_tool

_logger = logging.getLogger(__name__)


@register_tool
class MarginSummaryTool(BaseTool):
    name = 'get_margin_summary'
    description = (
        'Get profit margin analysis: revenue, cost, gross margin, and margin percentage. '
        'Can group by product, product category, month, or salesperson. '
        'Requires the sale_margin module (margin field on sale order lines).'
    )
    parameters_schema = {
        'type': 'object',
        'properties': {
            'date_from': {
                'type': 'string', 'format': 'date',
                'description': 'Start date (YYYY-MM-DD)',
            },
            'date_to': {
                'type': 'string', 'format': 'date',
                'description': 'End date (YYYY-MM-DD)',
            },
            'group_by': {
                'type': 'string',
                'enum': ['product', 'category', 'month', 'salesperson'],
                'default': 'category',
            },
            'limit': {
                'type': 'integer',
                'minimum': 1,
                'maximum': 100,
                'default': 20,
            },
        },
        'required': ['date_from', 'date_to'],
    }

    def execute(self, env, user, params):
        date_from = params['date_from']
        date_to = params['date_to']
        group_by = params.get('group_by', 'category')
        limit = params.get('limit', 20)
        company_id = user.company_id.id
        currency = user.company_id.currency_id.name or 'USD'

        SOLine = env['sale.order.line']

        domain = [
            ('order_id.state', 'in', ['sale', 'done']),
            ('order_id.date_order', '>=', date_from),
            ('order_id.date_order', '<=', date_to + ' 23:59:59'),
            ('order_id.company_id', '=', company_id),
        ]

        # Determine ORM groupby field
        groupby_map = {
            'product': 'product_id',
            'category': 'product_id.categ_id',
            'month': 'order_id.date_order:month',
            'salesperson': 'salesman_id',
        }
        orm_groupby = groupby_map.get(group_by, 'product_id.categ_id')

        # Check if margin field exists
        has_margin = 'margin' in SOLine._fields

        agg_fields = ['price_subtotal:sum', 'product_uom_qty:sum']
        if has_margin:
            agg_fields.append('margin:sum')

        group_data = SOLine.read_group(
            domain,
            fields=agg_fields,
            groupby=[orm_groupby],
            orderby='price_subtotal desc',
            limit=limit,
        )

        rows = []
        total_revenue = 0
        total_margin = 0

        for row in group_data:
            entity = row.get(orm_groupby)
            entity_name = 'Unknown'
            if isinstance(entity, (list, tuple)) and len(entity) >= 2:
                entity_name = entity[1]
            elif isinstance(entity, str):
                entity_name = entity
            elif entity:
                entity_name = str(entity)

            revenue = round(row.get('price_subtotal', 0) or 0, 2)
            qty = round(row.get('product_uom_qty', 0) or 0, 2)
            margin = round(row.get('margin', 0) or 0, 2) if has_margin else None
            cost = round(revenue - margin, 2) if margin is not None else None
            margin_pct = round((margin / revenue * 100), 1) if margin is not None and revenue > 0 else None

            total_revenue += revenue
            if margin is not None:
                total_margin += margin

            entry = {
                'name': entity_name,
                'revenue': revenue,
                'quantity': qty,
            }
            if margin is not None:
                entry['cost'] = cost
                entry['margin'] = margin
                entry['margin_pct'] = margin_pct

            rows.append(entry)

        result = {
            'period': {'from': date_from, 'to': date_to},
            'grouped_by': group_by,
            'data': rows,
            'totals': {
                'total_revenue': round(total_revenue, 2),
            },
            'currency': currency,
        }
        if has_margin:
            overall_margin_pct = round(
                (total_margin / total_revenue * 100), 1
            ) if total_revenue > 0 else 0
            result['totals']['total_margin'] = round(total_margin, 2)
            result['totals']['overall_margin_pct'] = overall_margin_pct

        if not has_margin:
            result['warning'] = (
                'Margin data is not available. Install the sale_margin module '
                'and ensure purchase_price is set on sale order lines.'
            )

        return result
