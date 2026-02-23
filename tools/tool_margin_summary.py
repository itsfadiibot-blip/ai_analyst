# -*- coding: utf-8 -*-
"""Tool: get_margin_summary - Profit margin analysis by product, category, time, or salesperson.

FIXED: Now computes margin from product_product.cost_aed since sale_order_line.margin doesn't exist.
Margin = price_subtotal - (product_uom_qty * product_id.cost_aed)
"""
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
        'Margin is computed as revenue minus cost (using product cost_aed field).'
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
        currency = user.company_id.currency_id.name or 'AED'

        SOLine = env['sale.order.line']

        domain = [
            ('order_id.state', 'in', ['sale', 'done']),
            ('order_id.date_order', '>=', date_from),
            ('order_id.date_order', '<=', date_to + ' 23:59:59'),
            ('order_id.company_id', '=', company_id),
            ('display_type', '=', False),  # Skip section/note lines
        ]

        # Determine ORM groupby field
        # FIXED: Use salesman_id (real field) instead of order_id.user_id
        groupby_map = {
            'product': 'product_id',
            'category': 'product_id.categ_id',
            'month': 'order_id.date_order:month',
            'salesperson': 'salesman_id',  # FIXED: was order_id.user_id, now salesman_id
        }
        orm_groupby = groupby_map.get(group_by, 'product_id.categ_id')

        # Read group to get revenue and quantity
        agg_fields = ['price_subtotal:sum', 'product_uom_qty:sum']

        group_data = SOLine.read_group(
            domain,
            fields=agg_fields,
            groupby=[orm_groupby],
            orderby='price_subtotal desc',
            limit=limit,
        )

        rows = []
        total_revenue = 0
        total_cost = 0

        for row in group_data:
            entity = row.get(orm_groupby)
            entity_name = 'Unknown'
            entity_id = None
            if isinstance(entity, (list, tuple)) and len(entity) >= 2:
                entity_name = entity[1]
                entity_id = entity[0]
            elif isinstance(entity, str):
                entity_name = entity
            elif entity:
                entity_name = str(entity)

            revenue = round(row.get('price_subtotal', 0) or 0, 2)
            qty = round(row.get('product_uom_qty', 0) or 0, 2)

            # FIXED: Compute cost and margin from product_product.cost_aed
            # Since we can't aggregate cost in read_group, we'll fetch costs separately
            cost = self._compute_total_cost(env, domain, entity_id, group_by, orm_groupby)
            margin = round(revenue - cost, 2)
            margin_pct = round((margin / revenue * 100), 1) if revenue > 0 else 0

            total_revenue += revenue
            total_cost += cost

            entry = {
                'name': entity_name,
                'revenue': revenue,
                'cost': cost,
                'margin': margin,
                'margin_pct': margin_pct,
                'quantity': qty,
            }
            rows.append(entry)

        result = {
            'period': {'from': date_from, 'to': date_to},
            'grouped_by': group_by,
            'data': rows,
            'totals': {
                'total_revenue': round(total_revenue, 2),
                'total_cost': round(total_cost, 2),
            },
            'currency': currency,
        }

        # Calculate overall margin
        if total_revenue > 0:
            overall_margin = total_revenue - total_cost
            result['totals']['total_margin'] = round(overall_margin, 2)
            result['totals']['overall_margin_pct'] = round(
                (overall_margin / total_revenue * 100), 1
            )

        return result

    def _compute_total_cost(self, env, base_domain, entity_id, group_by, orm_groupby):
        """Compute total cost for a grouping by summing (qty * cost_aed) for each line.
        
        FIXED: Since sale_order_line has no margin field, we compute from product_product.cost_aed
        """
        SOLine = env['sale.order.line']
        
        # Build specific domain for this entity
        domain = list(base_domain)
        if entity_id:
            if group_by == 'product':
                domain.append(('product_id', '=', entity_id))
            elif group_by == 'category':
                domain.append(('product_id.categ_id', '=', entity_id))
            elif group_by == 'salesperson':
                # FIXED: Use salesman_id instead of order_id.user_id
                if entity_id:
                    domain.append(('salesman_id', '=', entity_id))
                else:
                    domain.append(('salesman_id', '=', False))
            # For month, we can't filter by ID easily, skip optimization
        
        # Fetch lines with product cost
        lines = SOLine.search_read(
            domain,
            fields=['product_uom_qty', 'product_id'],
            limit=10000,  # Reasonable limit for aggregation
        )
        
        total_cost = 0
        product_ids = list(set([l['product_id'][0] for l in lines if l.get('product_id')]))
        
        if product_ids:
            # Fetch costs in batch
            Product = env['product.product']
            products = Product.browse(product_ids)
            cost_map = {p.id: (p.cost_aed or 0) for p in products}
            
            for line in lines:
                qty = line.get('product_uom_qty', 0) or 0
                product_id = line.get('product_id')
                if product_id:
                    cost = cost_map.get(product_id[0], 0)
                    total_cost += qty * cost
        
        return round(total_cost, 2)
