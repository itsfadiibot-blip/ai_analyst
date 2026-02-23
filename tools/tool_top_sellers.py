# -*- coding: utf-8 -*-
"""Tool: get_top_sellers — Top products/salespersons/categories by revenue, quantity, or margin."""
import logging

from .base_tool import BaseTool
from .registry import register_tool

_logger = logging.getLogger(__name__)


@register_tool
class TopSellersTool(BaseTool):
    name = 'get_top_sellers'
    description = (
        'Get top-selling products, salespersons, or product categories ranked by '
        'revenue, quantity sold, or margin. Covers confirmed sale orders. '
        'Includes margin data when available.'
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
            'by': {
                'type': 'string',
                'enum': ['product', 'salesperson', 'category'],
                'default': 'product',
                'description': 'Dimension to rank by',
            },
            'metric': {
                'type': 'string',
                'enum': ['revenue', 'quantity', 'margin'],
                'default': 'revenue',
                'description': 'Metric to sort/rank by',
            },
            'limit': {
                'type': 'integer',
                'minimum': 1,
                'maximum': 100,
                'default': 20,
                'description': 'Number of top results to return',
            },
        },
        'required': ['date_from', 'date_to'],
    }

    def execute(self, env, user, params):
        date_from = params['date_from']
        date_to = params['date_to']
        by = params.get('by', 'product')
        metric = params.get('metric', 'revenue')
        limit = params.get('limit', 20)
        company_id = user.company_id.id
        currency = user.company_id.currency_id.name or 'USD'

        # Use sale.order.line for product/category, sale.order for salesperson
        SOLine = env['sale.order.line']

        base_domain = [
            ('order_id.state', 'in', ['sale', 'done']),
            ('order_id.date_order', '>=', date_from),
            ('order_id.date_order', '<=', date_to + ' 23:59:59'),
            ('order_id.company_id', '=', company_id),
        ]

        # Determine groupby field and aggregation
        if by == 'product':
            groupby_field = 'product_id'
        elif by == 'salesperson':
            groupby_field = 'salesman_id'
        elif by == 'category':
            groupby_field = 'product_id.categ_id'
        else:
            groupby_field = 'product_id'

        # Determine sort field
        if metric == 'revenue':
            agg_fields = ['price_subtotal:sum', 'product_uom_qty:sum']
            sort_field = 'price_subtotal'
        elif metric == 'quantity':
            agg_fields = ['product_uom_qty:sum', 'price_subtotal:sum']
            sort_field = 'product_uom_qty'
        elif metric == 'margin':
            agg_fields = ['price_subtotal:sum', 'product_uom_qty:sum']
            # Margin requires purchase_price field (from sale_margin module)
            try:
                env['sale.order.line']._fields['margin']
                agg_fields.append('margin:sum')
                sort_field = 'margin'
            except KeyError:
                # sale_margin module not installed, fall back to revenue
                sort_field = 'price_subtotal'
        else:
            sort_field = 'price_subtotal'
            agg_fields = ['price_subtotal:sum', 'product_uom_qty:sum']

        group_data = SOLine.read_group(
            base_domain,
            fields=agg_fields,
            groupby=[groupby_field],
            orderby=f'{sort_field} desc',
            limit=limit,
        )

        rows = []
        rank = 0
        for row in group_data:
            rank += 1
            entity = row.get(groupby_field)
            entity_name = 'Unknown'
            entity_id = None

            if isinstance(entity, (list, tuple)) and len(entity) >= 2:
                entity_id = entity[0]
                entity_name = entity[1]
            elif entity:
                entity_name = str(entity)

            revenue = round(row.get('price_subtotal', 0) or 0, 2)
            qty = round(row.get('product_uom_qty', 0) or 0, 2)
            margin = round(row.get('margin', 0) or 0, 2) if 'margin' in row else None

            entry = {
                'rank': rank,
                'id': entity_id,
                'name': entity_name,
                'revenue': revenue,
                'quantity': qty,
            }
            if margin is not None:
                entry['margin'] = margin
                entry['margin_pct'] = round(
                    (margin / revenue * 100) if revenue > 0 else 0, 1
                )

            rows.append(entry)

        return {
            'period': {'from': date_from, 'to': date_to},
            'ranked_by': metric,
            'dimension': by,
            'data': rows,
            'total_results': len(rows),
            'currency': currency,
        }
