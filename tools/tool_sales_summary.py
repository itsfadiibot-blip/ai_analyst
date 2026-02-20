# -*- coding: utf-8 -*-
"""Tool: get_sales_summary — Sales revenue, order count, AOV with period comparison."""
import logging
from datetime import datetime, timedelta

from .base_tool import BaseTool
from .registry import register_tool

_logger = logging.getLogger(__name__)


@register_tool
class SalesSummaryTool(BaseTool):
    name = 'get_sales_summary'
    description = (
        'Get total sales revenue, order count, average order value, and optional '
        'comparison to a previous period of equal length. '
        'Covers confirmed sale orders (Website/Ecommerce channel). '
        'Can group results by day, week, or month.'
    )
    parameters_schema = {
        'type': 'object',
        'properties': {
            'date_from': {
                'type': 'string',
                'format': 'date',
                'description': 'Start date (YYYY-MM-DD)',
            },
            'date_to': {
                'type': 'string',
                'format': 'date',
                'description': 'End date (YYYY-MM-DD)',
            },
            'compare_previous': {
                'type': 'boolean',
                'description': 'If true, also return metrics for the preceding period of equal length',
                'default': False,
            },
            'group_by': {
                'type': 'string',
                'enum': ['day', 'week', 'month'],
                'description': 'Time granularity for breakdown',
                'default': 'month',
            },
        },
        'required': ['date_from', 'date_to'],
    }

    def execute(self, env, user, params):
        date_from = params['date_from']
        date_to = params['date_to']
        compare = params.get('compare_previous', False)
        group_by = params.get('group_by', 'month')
        company_id = user.company_id.id
        currency = user.company_id.currency_id.name or 'USD'

        # Build domain for confirmed sales
        domain = [
            ('state', 'in', ['sale', 'done']),
            ('date_order', '>=', date_from),
            ('date_order', '<=', date_to + ' 23:59:59'),
            ('company_id', '=', company_id),
        ]

        SaleOrder = env['sale.order']

        # Aggregate current period
        current = self._aggregate_sales(SaleOrder, domain, group_by)

        result = {
            'period': {'from': date_from, 'to': date_to},
            'summary': current['summary'],
            'breakdown': current['breakdown'],
        }

        # Compare with previous period
        if compare:
            dt_from = datetime.strptime(date_from, '%Y-%m-%d')
            dt_to = datetime.strptime(date_to, '%Y-%m-%d')
            period_days = (dt_to - dt_from).days + 1
            prev_to = dt_from - timedelta(days=1)
            prev_from = prev_to - timedelta(days=period_days - 1)

            prev_domain = [
                ('state', 'in', ['sale', 'done']),
                ('date_order', '>=', prev_from.strftime('%Y-%m-%d')),
                ('date_order', '<=', prev_to.strftime('%Y-%m-%d') + ' 23:59:59'),
                ('company_id', '=', company_id),
            ]
            previous = self._aggregate_sales(SaleOrder, prev_domain, group_by)
            result['previous_period'] = {
                'from': prev_from.strftime('%Y-%m-%d'),
                'to': prev_to.strftime('%Y-%m-%d'),
                'summary': previous['summary'],
            }

            # Calculate deltas
            cur_s = current['summary']
            prev_s = previous['summary']
            result['deltas'] = {
                'revenue': self._calculate_delta(cur_s['total_revenue'], prev_s['total_revenue']),
                'order_count': self._calculate_delta(cur_s['order_count'], prev_s['order_count']),
                'avg_order_value': self._calculate_delta(cur_s['avg_order_value'], prev_s['avg_order_value']),
            }

        result['currency'] = currency
        return result

    def _aggregate_sales(self, SaleOrder, domain, group_by):
        """Aggregate sales data for the given domain."""
        # Overall summary
        group_data = SaleOrder.read_group(
            domain,
            fields=['amount_total:sum', 'id:count'],
            groupby=[],
        )

        total_revenue = group_data[0]['amount_total'] if group_data else 0
        order_count = group_data[0]['__count'] if group_data else 0
        avg_order_value = total_revenue / order_count if order_count > 0 else 0

        summary = {
            'total_revenue': round(total_revenue, 2),
            'order_count': order_count,
            'avg_order_value': round(avg_order_value, 2),
        }

        # Time breakdown
        group_field = f'date_order:{group_by}'
        breakdown_data = SaleOrder.read_group(
            domain,
            fields=['amount_total:sum', 'id:count'],
            groupby=[group_field],
            orderby=group_field,
            limit=self.max_rows,
        )

        breakdown = []
        for row in breakdown_data:
            period_label = row.get(group_field, 'Unknown')
            rev = row.get('amount_total', 0) or 0
            cnt = row.get('__count', 0)
            breakdown.append({
                'period': period_label,
                'revenue': round(rev, 2),
                'order_count': cnt,
                'avg_order_value': round(rev / cnt, 2) if cnt > 0 else 0,
            })

        return {
            'summary': summary,
            'breakdown': breakdown,
        }
