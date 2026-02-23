# -*- coding: utf-8 -*-
"""Tool: get_sell_through - Sell-through analysis for fashion retail.

Most critical metric for fashion: how fast are products selling vs sitting in stock?
Uses x_studio_many2many_field_IXz60 for season filtering.
"""
import logging
from datetime import date, timedelta

from odoo.exceptions import ValidationError

from .base_tool import BaseTool
from .registry import register_tool

_logger = logging.getLogger(__name__)


@register_tool
class SellThroughTool(BaseTool):
    name = 'get_sell_through'
    description = (
        'Get sell-through analysis: shows how fast products are selling relative to available stock. '
        'Sell-through % = units sold / (units sold + units on hand). '
        'Critical for fashion retail to identify strong sellers vs slow movers. '
        'Filter by season, group by product/brand/category.'
    )
    parameters_schema = {
        'type': 'object',
        'properties': {
            'season_code': {
                'type': 'string',
                'description': 'Season code to analyze (e.g. FW25, SS25)',
            },
            'group_by': {
                'type': 'string',
                'enum': ['product', 'brand', 'category'],
                'default': 'product',
                'description': 'Group results by dimension',
            },
            'date_from': {
                'type': 'string',
                'format': 'date',
                'description': 'Start date for sales (YYYY-MM-DD), optional',
            },
            'date_to': {
                'type': 'string',
                'format': 'date',
                'description': 'End date for sales (YYYY-MM-DD), defaults to today',
            },
            'limit': {
                'type': 'integer',
                'minimum': 1,
                'maximum': 200,
                'default': 50,
                'description': 'Number of results to return',
            },
        },
        'required': ['season_code'],
    }

    def execute(self, env, user, params):
        env = env.with_user(user)
        season_code = (params.get('season_code') or '').strip()
        group_by = params.get('group_by', 'product')
        date_to = params.get('date_to', date.today().isoformat())
        date_from = params.get('date_from')
        if not date_from:
            # Default to 6 months ago
            date_from = (date.today() - timedelta(days=180)).isoformat()
        limit = params.get('limit', 50)
        company_id = user.company_id.id
        currency = user.company_id.currency_id.name or 'AED'

        if not season_code:
            raise ValidationError('season_code is required')

        # FIXED: Find season tag in x_product_tags via x_studio_many2many_field_IXz60
        season_tag = env['x_product_tags'].search([
            ('name', '=ilike', season_code)
        ], limit=1)

        if not season_tag:
            raise ValidationError(f'Season "{season_code}" not found in x_product_tags table')

        # Get products for this season via custom many2many field
        Product = env['product.product']
        Template = env['product.template']

        # Find templates with this season tag
        template_domain = [
            ('x_studio_many2many_field_IXz60', 'in', [season_tag.id]),
            ('active', '=', True),
        ]
        templates = Template.search(template_domain)

        if not templates:
            return {
                'season': season_code,
                'period': {'from': date_from, 'to': date_to},
                'group_by': group_by,
                'summary': {
                    'total_sold': 0,
                    'total_on_hand': 0,
                    'overall_sell_through_pct': 0.0,
                },
                'rows': [],
                'message': f'No products found for season {season_code}',
            }

        # Get all product variants for these templates
        products = Product.search([('product_tmpl_id', 'in', templates.ids)])

        if not products:
            return {
                'season': season_code,
                'period': {'from': date_from, 'to': date_to},
                'group_by': group_by,
                'summary': {'total_sold': 0, 'total_on_hand': 0, 'overall_sell_through_pct': 0.0},
                'rows': [],
                'message': f'No product variants found for season {season_code}',
            }

        # Build sale order line domain
        SaleLine = env['sale.order.line']
        sale_domain = [
            ('order_id.state', 'in', ['sale', 'done']),
            ('order_id.company_id', '=', company_id),
            ('order_id.date_order', '>=', f'{date_from} 00:00:00'),
            ('order_id.date_order', '<=', f'{date_to} 23:59:59'),
            ('product_id', 'in', products.ids),
            ('display_type', '=', False),
        ]

        # Aggregate sales by grouping
        if group_by == 'product':
            groupby_field = 'product_id'
        elif group_by == 'brand':
            groupby_field = 'product_id.product_tmpl_id.x_studio_many2one_field_mG9Pn'
        elif group_by == 'category':
            groupby_field = 'product_id.product_tmpl_id.x_sfcc_primary_category'
        else:
            groupby_field = 'product_id'

        # Get sales data
        sales_data = SaleLine.read_group(
            sale_domain,
            fields=['product_uom_qty:sum'],
            groupby=[groupby_field],
            orderby='product_uom_qty desc',
            limit=limit * 2,  # Get more to account for filtering
        )

        # Process each group
        rows = []
        total_sold = 0
        total_on_hand = 0

        for row in sales_data:
            entity = row.get(groupby_field)
            if not entity:
                continue

            # Extract entity ID and name
            if isinstance(entity, (list, tuple)) and len(entity) >= 2:
                entity_id = entity[0]
                entity_name = entity[1]
            else:
                entity_id = None
                entity_name = str(entity) if entity else 'Unknown'

            units_sold = round(row.get('product_uom_qty', 0) or 0, 2)

            # Get on-hand quantity
            # FIXED: Use free_qty (real SOH) not qty_available (includes reserved)
            if group_by == 'product':
                product = Product.browse(entity_id) if entity_id else Product
                units_on_hand = round(product.free_qty or 0, 2)
                brand_name = product.product_tmpl_id.x_studio_many2one_field_mG9Pn.name if product.product_tmpl_id.x_studio_many2one_field_mG9Pn else ''
            elif group_by == 'brand':
                # Sum free_qty for all products in this brand within the season
                brand_products = products.filtered(
                    lambda p: p.product_tmpl_id.x_studio_many2one_field_mG9Pn.id == entity_id if entity_id else False
                )
                units_on_hand = sum(p.free_qty or 0 for p in brand_products)
                units_on_hand = round(units_on_hand, 2)
                brand_name = entity_name
            elif group_by == 'category':
                # Sum free_qty for all products in this category within the season
                cat_products = products.filtered(
                    lambda p: p.product_tmpl_id.x_sfcc_primary_category == entity if entity else False
                )
                units_on_hand = sum(p.free_qty or 0 for p in cat_products)
                units_on_hand = round(units_on_hand, 2)
                brand_name = ''
            else:
                units_on_hand = 0
                brand_name = ''

            # Calculate sell-through
            if (units_sold + units_on_hand) > 0:
                sell_through_pct = round((units_sold / (units_sold + units_on_hand)) * 100, 1)
            else:
                sell_through_pct = 0.0

            # Determine status
            if sell_through_pct >= 70:
                status = 'Strong'
            elif sell_through_pct >= 40:
                status = 'Average'
            else:
                status = 'Slow'

            total_sold += units_sold
            total_on_hand += units_on_hand

            row_data = {
                'name': entity_name,
                'units_sold': units_sold,
                'units_on_hand': units_on_hand,
                'sell_through_pct': sell_through_pct,
                'status': status,
            }

            if brand_name:
                row_data['brand'] = brand_name

            rows.append(row_data)

        # Sort by sell-through %
        rows.sort(key=lambda x: x['sell_through_pct'], reverse=True)
        rows = rows[:limit]

        # Calculate overall sell-through
        if (total_sold + total_on_hand) > 0:
            overall_pct = round((total_sold / (total_sold + total_on_hand)) * 100, 1)
        else:
            overall_pct = 0.0

        return {
            'season': season_code,
            'period': {'from': date_from, 'to': date_to},
            'group_by': group_by,
            'summary': {
                'total_sold': round(total_sold, 2),
                'total_on_hand': round(total_on_hand, 2),
                'overall_sell_through_pct': overall_pct,
            },
            'rows': rows,
            'total_results': len(rows),
            'currency': currency,
        }
