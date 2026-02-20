# -*- coding: utf-8 -*-
"""Tool: get_refund_return_impact — Analyze refunds/returns and their impact on revenue."""
import logging

from .base_tool import BaseTool
from .registry import register_tool

_logger = logging.getLogger(__name__)


@register_tool
class RefundReturnTool(BaseTool):
    name = 'get_refund_return_impact'
    description = (
        'Analyze refunds and returns: count, total value, refund rate as a percentage '
        'of gross sales, and top refunded products. Covers credit notes / refund invoices '
        'and optionally POS refunds.'
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
                'enum': ['product', 'reason', 'month', 'salesperson'],
                'default': 'product',
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
        group_by = params.get('group_by', 'product')
        limit = params.get('limit', 20)
        company_id = user.company_id.id
        currency = user.company_id.currency_id.name or 'USD'

        AccountMove = env['account.move']

        # --- Gross sales (out_invoice, posted) ---
        sales_domain = [
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
            ('company_id', '=', company_id),
        ]
        sales_agg = AccountMove.read_group(
            sales_domain,
            fields=['amount_total_signed:sum', 'id:count'],
            groupby=[],
        )
        gross_sales = abs(sales_agg[0]['amount_total_signed'] or 0) if sales_agg else 0
        sales_count = sales_agg[0]['__count'] if sales_agg else 0

        # --- Credit notes / refunds (out_refund, posted) ---
        refund_domain = [
            ('move_type', '=', 'out_refund'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
            ('company_id', '=', company_id),
        ]
        refund_agg = AccountMove.read_group(
            refund_domain,
            fields=['amount_total_signed:sum', 'id:count'],
            groupby=[],
        )
        refund_total = abs(refund_agg[0]['amount_total_signed'] or 0) if refund_agg else 0
        refund_count = refund_agg[0]['__count'] if refund_agg else 0

        # Refund rate
        refund_rate = round(
            (refund_total / gross_sales * 100) if gross_sales > 0 else 0, 2
        )
        net_revenue = round(gross_sales - refund_total, 2)

        # --- Breakdown by selected dimension ---
        AML = env['account.move.line']
        refund_line_domain = [
            ('move_id.move_type', '=', 'out_refund'),
            ('move_id.state', '=', 'posted'),
            ('move_id.invoice_date', '>=', date_from),
            ('move_id.invoice_date', '<=', date_to),
            ('move_id.company_id', '=', company_id),
            ('display_type', '=', 'product'),
        ]

        if group_by == 'product':
            orm_groupby = 'product_id'
        elif group_by == 'month':
            orm_groupby = 'move_id.invoice_date:month'
        elif group_by == 'salesperson':
            orm_groupby = 'move_id.invoice_user_id'
        else:
            orm_groupby = 'product_id'

        breakdown_data = AML.read_group(
            refund_line_domain,
            fields=['price_subtotal:sum', 'quantity:sum'],
            groupby=[orm_groupby],
            orderby='price_subtotal desc',
            limit=limit,
        )

        breakdown = []
        for row in breakdown_data:
            entity = row.get(orm_groupby)
            entity_name = 'Unknown'
            if isinstance(entity, (list, tuple)) and len(entity) >= 2:
                entity_name = entity[1]
            elif isinstance(entity, str):
                entity_name = entity
            elif entity:
                entity_name = str(entity)

            amount = abs(round(row.get('price_subtotal', 0) or 0, 2))
            qty = abs(round(row.get('quantity', 0) or 0, 2))

            breakdown.append({
                'name': entity_name,
                'refund_amount': amount,
                'refund_quantity': qty,
                'pct_of_total_refunds': round(
                    (amount / refund_total * 100) if refund_total > 0 else 0, 1
                ),
            })

        return {
            'period': {'from': date_from, 'to': date_to},
            'summary': {
                'gross_sales': round(gross_sales, 2),
                'total_refunds': round(refund_total, 2),
                'net_revenue': net_revenue,
                'refund_count': refund_count,
                'sales_count': sales_count,
                'refund_rate_pct': refund_rate,
                'revenue_impact_pct': round(
                    (refund_total / gross_sales * 100) if gross_sales > 0 else 0, 1
                ),
            },
            'breakdown': breakdown,
            'grouped_by': group_by,
            'currency': currency,
        }
