# -*- coding: utf-8 -*-
"""Tool: get_margin_summary - Profit margin analysis.

FIXED: Margin is calculated as revenue - cost, NOT from a stored field.
Cost comes from product.product.standard_price (NOT purchase_price on sale.order.line).
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
        'Margin = revenue - (quantity × cost_price).'
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
                'enum': ['product', 'category', 'month', 'salesperson', 'brand'],
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
            ('display_type', '=', False),
        ]

        # FIXED: Determine groupby field using correct field paths
        groupby_map = {
            'product': 'product_id',
            'category': 'product_id.product_tmpl_id.x_sfcc_primary_category',  # FIXED: not categ_id
            'month': 'order_id.date_order:month',
            'salesperson': 'salesman_id',
            'brand': 'product_id.product_tmpl_id.x_studio_many2one_field_mG9Pn',  # FIXED: real brand field
        }
        orm_groupby = groupby_map.get(group_by, 'product_id.product_tmpl_id.x_sfcc_primary_category')

        # Get revenue aggregates
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

            # FIXED: Compute cost and margin from product.product.standard_price
            # NO margin or purchase_price fields exist on sale.order.line
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
        """Compute total cost for a grouping by summing (qty × standard_price) for each line.

        FIXED: Uses product.product.standard_price (cost field), NOT purchase_price or margin.
        """
        SOLine = env['sale.order.line']

        # Build specific domain for this entity
        domain = list(base_domain)
        if entity_id:
            if group_by == 'product':
                domain.append(('product_id', '=', entity_id))
            elif group_by == 'category':
                domain.append(('product_id.product_tmpl_id.x_sfcc_primary_category', '=', entity_id))
            elif group_by == 'brand':
                domain.append(('product_id.product_tmpl_id.x_studio_many2one_field_mG9Pn', '=', entity_id))
            elif group_by == 'salesperson':
                if entity_id:
                    domain.append(('salesman_id', '=', entity_id))
                else:
                    domain.append(('salesman_id', '=', False))
            # For month, entity_id is string, skip optimization

        # Fetch lines with product reference
        lines = SOLine.search_read(
            domain,
            fields=['product_uom_qty', 'product_id'],
            limit=10000,
        )

        total_cost = 0
        product_ids = list(set([l['product_id'][0] for l in lines if l.get('product_id')]))

        if product_ids:
            # FIXED: Fetch costs from product.product.standard_price in batch
            Product = env['product.product']
            products = Product.browse(product_ids)
            cost_map = {p.id: (p.standard_price or 0) for p in products}

            for line in lines:
                qty = line.get('product_uom_qty', 0) or 0
                product_id = line.get('product_id')
                if product_id:
                    cost = cost_map.get(product_id[0], 0)
                    total_cost += qty * cost

        return round(total_cost, 2)
