# -*- coding: utf-8 -*-
"""Tool: get_top_sellers - Top products/salespersons/categories by revenue, quantity, or margin.

FIXED: Now uses salesman_id field (which exists and is populated) instead of order_id.user_id.
Margin is computed from standard_price since no margin field exists on sale_order_line.
"""
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
        'Includes margin data computed from product costs.'
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
        currency = user.company_id.currency_id.name or 'AED'

        # Use sale.order.line for product/category, sale.order for salesperson
        SOLine = env['sale.order.line']

        base_domain = [
            ('order_id.state', 'in', ['sale', 'done']),
            ('order_id.date_order', '>=', date_from),
            ('order_id.date_order', '<=', date_to + ' 23:59:59'),
            ('order_id.company_id', '=', company_id),
            ('display_type', '=', False),  # Skip section/note lines
        ]

        # Determine groupby field
        if by == 'product':
            groupby_field = 'product_id'
        elif by == 'salesperson':
            # FIXED: Use salesman_id which exists and is populated (not order_id.user_id)
            groupby_field = 'salesman_id'
        elif by == 'category':
            groupby_field = 'product_id.categ_id'
        else:
            groupby_field = 'product_id'

        # Determine sort field and aggregation
        if metric == 'revenue':
            agg_fields = ['price_subtotal:sum', 'product_uom_qty:sum']
            sort_field = 'price_subtotal'
        elif metric == 'quantity':
            agg_fields = ['product_uom_qty:sum', 'price_subtotal:sum']
            sort_field = 'product_uom_qty'
        elif metric == 'margin':
            # FIXED: For margin, we need to compute from standard_price
            # We'll get revenue and compute margin from product costs
            agg_fields = ['price_subtotal:sum', 'product_uom_qty:sum']
            sort_field = 'price_subtotal'  # Fallback, will re-sort after computing
        else:
            sort_field = 'price_subtotal'
            agg_fields = ['price_subtotal:sum', 'product_uom_qty:sum']

        group_data = SOLine.read_group(
            base_domain,
            fields=agg_fields,
            groupby=[groupby_field],
            orderby=f'{sort_field} desc',
            limit=limit if metric != 'margin' else limit * 2,  # Get more for margin recalculation
        )

        rows = []
        for row in group_data:
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

            # FIXED: Compute margin from product standard_price
            margin = self._compute_margin(env, base_domain, entity_id, by, groupby_field)
            margin_pct = round((margin / revenue * 100), 1) if revenue > 0 else 0

            entry = {
                'name': entity_name,
                'revenue': revenue,
                'quantity': qty,
                'margin': margin,
                'margin_pct': margin_pct,
            }
            rows.append(entry)

        # If sorting by margin, re-sort and trim
        if metric == 'margin':
            rows.sort(key=lambda x: x['margin'], reverse=True)
            rows = rows[:limit]

        # Add rank
        for i, row in enumerate(rows, 1):
            row['rank'] = i

        return {
            'period': {'from': date_from, 'to': date_to},
            'ranked_by': metric,
            'dimension': by,
            'data': rows,
            'total_results': len(rows),
            'currency': currency,
        }

    def _compute_margin(self, env, base_domain, entity_id, by, groupby_field):
        """Compute margin by fetching lines and calculating revenue - cost.

        FIXED: Uses standard_price from product_product since no margin field exists.
        """
        SOLine = env['sale.order.line']

        domain = list(base_domain)
        if entity_id:
            if by == 'product':
                domain.append(('product_id', '=', entity_id))
            elif by == 'category':
                domain.append(('product_id.categ_id', '=', entity_id))
            elif by == 'salesperson':
                # FIXED: Use salesman_id
                domain.append(('salesman_id', '=', entity_id))

        lines = SOLine.search_read(
            domain,
            fields=['price_subtotal', 'product_uom_qty', 'product_id'],
            limit=5000,
        )

        total_revenue = 0
        total_cost = 0

        product_ids = list(set([l['product_id'][0] for l in lines if l.get('product_id')]))

        if product_ids:
            Product = env['product.product']
            products = Product.browse(product_ids)
            cost_map = {p.id: (p.standard_price or 0) for p in products}

            for line in lines:
                revenue = line.get('price_subtotal', 0) or 0
                qty = line.get('product_uom_qty', 0) or 0
                product_id = line.get('product_id')

                total_revenue += revenue
                if product_id:
                    cost = cost_map.get(product_id[0], 0)
                    total_cost += qty * cost

        return round(total_revenue - total_cost, 2)
