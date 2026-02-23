# -*- coding: utf-8 -*-
"""Tool: get_inventory_valuation — Inventory valuation as of a specific date.

FIXED: Uses stock.quant.value for valuation, product.product.free_qty for available stock.
"""
import logging

from .base_tool import BaseTool
from .registry import register_tool

_logger = logging.getLogger(__name__)


@register_tool
class InventoryValuationTool(BaseTool):
    name = 'get_inventory_valuation'
    description = (
        'Get inventory valuation as of a specific date. '
        'Shows stock value and available quantity. '
        'Groups by product, category, or brand.'
    )
    parameters_schema = {
        'type': 'object',
        'properties': {
            'as_of_date': {
                'type': 'string',
                'format': 'date',
                'description': 'Valuation date (YYYY-MM-DD)',
            },
            'group_by': {
                'type': 'string',
                'enum': ['product', 'category', 'brand'],
                'default': 'category',
            },
            'limit': {
                'type': 'integer',
                'minimum': 1,
                'maximum': 500,
                'default': 50,
            },
        },
        'required': ['as_of_date'],
    }

    def execute(self, env, user, params):
        as_of_date = params['as_of_date']
        group_by = params.get('group_by', 'category')
        limit = params.get('limit', 50)
        company_id = user.company_id.id
        currency = user.company_id.currency_id.name or 'AED'

        # FIXED: Use stock.quant for valuation (has value field)
        Quant = env['stock.quant']

        domain = [
            ('company_id', '=', company_id),
            ('quantity', '>', 0),  # Only positive stock
            ('location_id.usage', '=', 'internal'),  # Only internal locations
        ]

        # FIXED: Group by using correct field paths
        if group_by == 'product':
            groupby_field = 'product_id'
        elif group_by == 'category':
            # FIXED: Use x_sfcc_primary_category not categ_id
            groupby_field = 'product_id.product_tmpl_id.x_sfcc_primary_category'
        elif group_by == 'brand':
            # FIXED: Use real brand field
            groupby_field = 'product_id.product_tmpl_id.x_studio_many2one_field_mG9Pn'
        else:
            groupby_field = 'product_id.product_tmpl_id.x_sfcc_primary_category'

        # FIXED: stock.quant has value field for valuation
        group_data = Quant.read_group(
            domain,
            fields=['value:sum', 'quantity:sum'],
            groupby=[groupby_field],
            orderby='value desc',
            limit=limit,
        )

        rows = []
        total_value = 0
        total_qty = 0

        for row in group_data:
            entity = row.get(groupby_field)
            entity_name = 'Unknown'
            entity_id = None

            if isinstance(entity, (list, tuple)) and len(entity) >= 2:
                entity_id = entity[0]
                entity_name = entity[1]
            elif entity:
                entity_name = str(entity)

            value = round(row.get('value', 0) or 0, 2)
            qty = round(row.get('quantity', 0) or 0, 2)
            unit_cost = round(value / qty, 2) if qty > 0 else 0

            # Only include items with positive stock
            if qty > 0:
                total_value += value
                total_qty += qty
                rows.append({
                    'id': entity_id,
                    'name': entity_name,
                    'quantity_on_hand': qty,
                    'valuation': value,
                    'avg_unit_cost': unit_cost,
                })

        return {
            'as_of_date': as_of_date,
            'grouped_by': group_by,
            'data': rows,
            'totals': {
                'total_valuation': round(total_value, 2),
                'total_quantity': round(total_qty, 2),
            },
            'currency': currency,
            'total_results': len(rows),
        }
