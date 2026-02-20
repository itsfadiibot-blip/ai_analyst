# -*- coding: utf-8 -*-
"""Tool: get_pos_vs_online_summary — Compare POS vs Online sales side-by-side."""
import logging

from .base_tool import BaseTool
from .registry import register_tool

_logger = logging.getLogger(__name__)


@register_tool
class POSvsOnlineTool(BaseTool):
    name = 'get_pos_vs_online_summary'
    description = (
        'Compare POS sales vs Online (Website/Ecommerce) sales for a given period. '
        'Returns both channels side by side with revenue, count, and percentage split. '
        'Can group by day, week, or month for trend comparison.'
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
                'enum': ['day', 'week', 'month'],
                'default': 'month',
            },
        },
        'required': ['date_from', 'date_to'],
    }

    def execute(self, env, user, params):
        date_from = params['date_from']
        date_to = params['date_to']
        group_by = params.get('group_by', 'month')
        company_id = user.company_id.id
        currency = user.company_id.currency_id.name or 'USD'

        # --- Online sales (sale.order) ---
        online_domain = [
            ('state', 'in', ['sale', 'done']),
            ('date_order', '>=', date_from),
            ('date_order', '<=', date_to + ' 23:59:59'),
            ('company_id', '=', company_id),
        ]
        SaleOrder = env['sale.order']
        online_agg = SaleOrder.read_group(
            online_domain,
            fields=['amount_total:sum', 'id:count'],
            groupby=[],
        )
        online_revenue = (online_agg[0]['amount_total'] or 0) if online_agg else 0
        online_count = online_agg[0]['__count'] if online_agg else 0

        # Online time series
        group_field = f'date_order:{group_by}'
        online_series = SaleOrder.read_group(
            online_domain,
            fields=['amount_total:sum', 'id:count'],
            groupby=[group_field],
            orderby=group_field,
            limit=self.max_rows,
        )

        # --- POS sales ---
        pos_domain = [
            ('state', 'in', ['paid', 'done', 'invoiced']),
            ('date_order', '>=', date_from + ' 00:00:00'),
            ('date_order', '<=', date_to + ' 23:59:59'),
            ('company_id', '=', company_id),
        ]
        PosOrder = env['pos.order']
        pos_agg = PosOrder.read_group(
            pos_domain,
            fields=['amount_total:sum', 'id:count'],
            groupby=[],
        )
        pos_revenue = (pos_agg[0]['amount_total'] or 0) if pos_agg else 0
        pos_count = pos_agg[0]['__count'] if pos_agg else 0

        # POS time series
        pos_group_field = f'date_order:{group_by}'
        pos_series = PosOrder.read_group(
            pos_domain,
            fields=['amount_total:sum', 'id:count'],
            groupby=[pos_group_field],
            orderby=pos_group_field,
            limit=self.max_rows,
        )

        # --- Combined totals ---
        grand_total = online_revenue + pos_revenue
        online_pct = (online_revenue / grand_total * 100) if grand_total > 0 else 0
        pos_pct = (pos_revenue / grand_total * 100) if grand_total > 0 else 0

        result = {
            'period': {'from': date_from, 'to': date_to},
            'summary': {
                'grand_total_revenue': round(grand_total, 2),
                'online': {
                    'revenue': round(online_revenue, 2),
                    'order_count': online_count,
                    'percentage': round(online_pct, 1),
                    'avg_order_value': round(online_revenue / online_count, 2) if online_count > 0 else 0,
                },
                'pos': {
                    'revenue': round(pos_revenue, 2),
                    'transaction_count': pos_count,
                    'percentage': round(pos_pct, 1),
                    'avg_ticket': round(pos_revenue / pos_count, 2) if pos_count > 0 else 0,
                },
            },
            'time_series': {
                'online': [
                    {
                        'period': row.get(group_field, ''),
                        'revenue': round(row.get('amount_total', 0) or 0, 2),
                        'count': row.get('__count', 0),
                    }
                    for row in online_series
                ],
                'pos': [
                    {
                        'period': row.get(pos_group_field, ''),
                        'revenue': round(row.get('amount_total', 0) or 0, 2),
                        'count': row.get('__count', 0),
                    }
                    for row in pos_series
                ],
            },
            'currency': currency,
        }

        return result
