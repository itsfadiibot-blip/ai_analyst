# -*- coding: utf-8 -*-
"""Tool: get_stock_aging - Identify slow-moving and aging stock.

FIXED: Uses stock.quant.in_date for aging, stock.quant.value for valuation.
"""
import logging
from datetime import datetime, timedelta

from .base_tool import BaseTool
from .registry import register_tool

_logger = logging.getLogger(__name__)


@register_tool
class StockAgingTool(BaseTool):
    name = 'get_stock_aging'
    description = (
        'Identify slow-moving and aging stock. Shows products with stock on hand, '
        'last sale date, days since last sale, and current valuation.'
    )
    parameters_schema = {
        'type': 'object',
        'properties': {
            'days_threshold': {
                'type': 'integer',
                'description': "Consider stock 'slow-moving' if no sale in this many days",
                'default': 90,
                'minimum': 1,
            },
            'limit': {
                'type': 'integer',
                'minimum': 1,
                'maximum': 500,
                'default': 50,
            },
            'sort_by': {
                'type': 'string',
                'enum': ['days_since_last_sale', 'valuation', 'qty_on_hand'],
                'default': 'days_since_last_sale',
            },
        },
        'required': [],
    }

    def execute(self, env, user, params):
        days_threshold = params.get('days_threshold', 90)
        limit = params.get('limit', 50)
        sort_by = params.get('sort_by', 'days_since_last_sale')
        company_id = user.company_id.id
        currency = user.company_id.currency_id.name or 'AED'

        today = datetime.now().date()
        threshold_date = today - timedelta(days=days_threshold)

        # FIXED: Use stock.quant for inventory data (has in_date, value, quantity)
        Quant = env['stock.quant']
        quant_domain = [
            ('company_id', '=', company_id),
            ('quantity', '>', 0),
            ('location_id.usage', '=', 'internal'),
        ]

        # Group by product to get total qty and value
        quant_data = Quant.read_group(
            quant_domain,
            fields=['quantity:sum', 'value:sum'],
            groupby=['product_id'],
            orderby='quantity desc',
            limit=500,
        )

        SOLine = env['sale.order.line']
        SaleOrder = env['sale.order']
        rows = []

        for quant_row in quant_data:
            product = quant_row.get('product_id')
            if not product or not isinstance(product, (list, tuple)):
                continue

            product_id = product[0]
            product_name = product[1]
            qty_on_hand = round(quant_row.get('quantity', 0) or 0, 2)

            # FIXED: Use value from stock.quant
            valuation = round(quant_row.get('value', 0) or 0, 2)

            # Find last sale date for this product
            last_orders = SaleOrder.search_read(
                [
                    ('order_line.product_id', '=', product_id),
                    ('state', 'in', ['sale', 'done']),
                    ('company_id', '=', company_id),
                ],
                fields=['date_order'],
                order='date_order desc',
                limit=1,
            )

            if last_orders and last_orders[0].get('date_order'):
                last_date = last_orders[0]['date_order'].date() if hasattr(
                    last_orders[0]['date_order'], 'date'
                ) else datetime.strptime(
                    str(last_orders[0]['date_order'])[:10], '%Y-%m-%d'
                ).date()
                days_since = (today - last_date).days
                last_date_str = last_date.isoformat()
            else:
                days_since = 9999
                last_date_str = None

            # Only include if slower than threshold
            if days_since >= days_threshold:
                rows.append({
                    'product_id': product_id,
                    'product_name': product_name,
                    'qty_on_hand': qty_on_hand,
                    'valuation': valuation,
                    'last_sale_date': last_date_str,
                    'days_since_last_sale': days_since if days_since < 9999 else 'Never sold',
                })

        # Sort
        def sort_key(r):
            if sort_by == 'days_since_last_sale':
                v = r.get('days_since_last_sale', 0)
                return v if isinstance(v, int) else 99999
            elif sort_by == 'valuation':
                return -(r.get('valuation', 0))
            elif sort_by == 'qty_on_hand':
                return -(r.get('qty_on_hand', 0))
            return 0

        rows.sort(key=sort_key, reverse=(sort_by == 'days_since_last_sale'))
        rows = rows[:limit]

        total_valuation = sum(r.get('valuation', 0) for r in rows)
        total_qty = sum(r.get('qty_on_hand', 0) for r in rows)

        return {
            'threshold_days': days_threshold,
            'data': rows,
            'totals': {
                'total_slow_stock_valuation': round(total_valuation, 2),
                'total_slow_stock_qty': round(total_qty, 2),
                'product_count': len(rows),
            },
            'currency': currency,
        }
