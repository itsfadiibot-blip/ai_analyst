# -*- coding: utf-8 -*-
"""Tool: get_pos_summary — POS sales summary with optional config filter."""
import logging
from datetime import datetime, timedelta

from .base_tool import BaseTool
from .registry import register_tool

_logger = logging.getLogger(__name__)


@register_tool
class POSSummaryTool(BaseTool):
    name = 'get_pos_summary'
    description = (
        'Get POS (Point of Sale) sales summary: total revenue, transaction count, '
        'average ticket value. Can filter by specific POS config (shop/terminal) and '
        'compare to a previous period.'
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
            'pos_config_ids': {
                'type': 'array',
                'items': {'type': 'integer'},
                'description': 'Filter by specific POS config IDs (optional)',
            },
            'compare_previous': {
                'type': 'boolean',
                'default': False,
                'description': 'Compare to previous period of equal length',
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
        compare = params.get('compare_previous', False)
        group_by = params.get('group_by', 'month')
        pos_config_ids = params.get('pos_config_ids', [])
        company_id = user.company_id.id
        currency = user.company_id.currency_id.name or 'USD'

        domain = [
            ('state', 'in', ['paid', 'done', 'invoiced']),
            ('date_order', '>=', date_from + ' 00:00:00'),
            ('date_order', '<=', date_to + ' 23:59:59'),
            ('company_id', '=', company_id),
        ]
        if pos_config_ids:
            domain.append(('config_id', 'in', pos_config_ids))

        PosOrder = env['pos.order']
        current = self._aggregate_pos(PosOrder, domain, group_by)

        result = {
            'period': {'from': date_from, 'to': date_to},
            'summary': current['summary'],
            'by_config': current['by_config'],
            'breakdown': current['breakdown'],
            'currency': currency,
        }

        if compare:
            dt_from = datetime.strptime(date_from, '%Y-%m-%d')
            dt_to = datetime.strptime(date_to, '%Y-%m-%d')
            period_days = (dt_to - dt_from).days + 1
            prev_to = dt_from - timedelta(days=1)
            prev_from = prev_to - timedelta(days=period_days - 1)

            prev_domain = [
                ('state', 'in', ['paid', 'done', 'invoiced']),
                ('date_order', '>=', prev_from.strftime('%Y-%m-%d') + ' 00:00:00'),
                ('date_order', '<=', prev_to.strftime('%Y-%m-%d') + ' 23:59:59'),
                ('company_id', '=', company_id),
            ]
            if pos_config_ids:
                prev_domain.append(('config_id', 'in', pos_config_ids))

            previous = self._aggregate_pos(PosOrder, prev_domain, group_by)
            result['previous_period'] = {
                'from': prev_from.strftime('%Y-%m-%d'),
                'to': prev_to.strftime('%Y-%m-%d'),
                'summary': previous['summary'],
            }
            cur_s = current['summary']
            prev_s = previous['summary']
            result['deltas'] = {
                'revenue': self._calculate_delta(cur_s['total_revenue'], prev_s['total_revenue']),
                'transaction_count': self._calculate_delta(cur_s['transaction_count'], prev_s['transaction_count']),
                'avg_ticket': self._calculate_delta(cur_s['avg_ticket'], prev_s['avg_ticket']),
            }

        return result

    def _aggregate_pos(self, PosOrder, domain, group_by):
        """Aggregate POS data."""
        # Overall
        agg = PosOrder.read_group(
            domain,
            fields=['amount_total:sum', 'id:count'],
            groupby=[],
        )
        total_revenue = agg[0]['amount_total'] if agg else 0
        count = agg[0]['__count'] if agg else 0
        avg_ticket = total_revenue / count if count > 0 else 0

        summary = {
            'total_revenue': round(total_revenue or 0, 2),
            'transaction_count': count,
            'avg_ticket': round(avg_ticket, 2),
        }

        # By POS config
        by_config_data = PosOrder.read_group(
            domain,
            fields=['amount_total:sum', 'id:count'],
            groupby=['config_id'],
            limit=50,
        )
        by_config = []
        for row in by_config_data:
            config_name = row.get('config_id', [None, 'Unknown'])
            rev = row.get('amount_total', 0) or 0
            cnt = row.get('__count', 0)
            by_config.append({
                'config_id': config_name[0] if isinstance(config_name, (list, tuple)) else None,
                'config_name': config_name[1] if isinstance(config_name, (list, tuple)) else str(config_name),
                'revenue': round(rev, 2),
                'transaction_count': cnt,
                'avg_ticket': round(rev / cnt, 2) if cnt > 0 else 0,
            })

        # Time breakdown
        group_field = f'date_order:{group_by}'
        breakdown_data = PosOrder.read_group(
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
                'transaction_count': cnt,
                'avg_ticket': round(rev / cnt, 2) if cnt > 0 else 0,
            })

        return {
            'summary': summary,
            'by_config': by_config,
            'breakdown': breakdown,
        }
