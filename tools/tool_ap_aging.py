# -*- coding: utf-8 -*-
"""Tool: get_ap_aging — Accounts Payable aging summary with aging buckets."""
import logging
from datetime import datetime, date as date_type

from .base_tool import BaseTool
from .registry import register_tool

_logger = logging.getLogger(__name__)


@register_tool
class APAgingTool(BaseTool):
    name = 'get_ap_aging'
    description = (
        'Accounts Payable aging summary. Groups outstanding vendor bills '
        'into aging buckets: Current (not yet due), 1-30 days overdue, 31-60, 61-90, '
        'and 90+ days overdue. Shows amounts by vendor.'
    )
    parameters_schema = {
        'type': 'object',
        'properties': {
            'as_of_date': {
                'type': 'string',
                'format': 'date',
                'description': 'Aging as of this date (default: today)',
            },
            'partner_ids': {
                'type': 'array',
                'items': {'type': 'integer'},
                'description': 'Filter by specific vendor IDs (optional)',
            },
            'limit': {
                'type': 'integer',
                'minimum': 1,
                'maximum': 200,
                'default': 50,
            },
        },
        'required': [],
    }

    def execute(self, env, user, params):
        as_of = params.get('as_of_date')
        if as_of:
            as_of_date = datetime.strptime(as_of, '%Y-%m-%d').date()
        else:
            as_of_date = date_type.today()

        partner_ids = params.get('partner_ids', [])
        limit = params.get('limit', 50)
        company_id = user.company_id.id
        currency = user.company_id.currency_id.name or 'USD'

        AccountMove = env['account.move']

        # Find open vendor bills
        domain = [
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('company_id', '=', company_id),
        ]
        if partner_ids:
            domain.append(('partner_id', 'in', partner_ids))

        open_bills = AccountMove.search_read(
            domain,
            fields=[
                'partner_id', 'name', 'invoice_date', 'invoice_date_due',
                'amount_residual', 'amount_total',
            ],
            order='amount_residual desc',
            limit=500,
        )

        buckets = {
            'current': {'label': 'Current (Not Due)', 'total': 0, 'count': 0},
            '1_30': {'label': '1-30 Days', 'total': 0, 'count': 0},
            '31_60': {'label': '31-60 Days', 'total': 0, 'count': 0},
            '61_90': {'label': '61-90 Days', 'total': 0, 'count': 0},
            '90_plus': {'label': '90+ Days', 'total': 0, 'count': 0},
        }

        vendor_aging = {}
        grand_total = 0

        for bill in open_bills:
            due_date = bill.get('invoice_date_due') or bill.get('invoice_date')
            if not due_date:
                continue

            if hasattr(due_date, 'date'):
                due_date = due_date.date()
            elif isinstance(due_date, str):
                due_date = datetime.strptime(due_date[:10], '%Y-%m-%d').date()

            days_overdue = (as_of_date - due_date).days
            amount = abs(bill.get('amount_residual', 0) or 0)
            grand_total += amount

            if days_overdue <= 0:
                bucket_key = 'current'
            elif days_overdue <= 30:
                bucket_key = '1_30'
            elif days_overdue <= 60:
                bucket_key = '31_60'
            elif days_overdue <= 90:
                bucket_key = '61_90'
            else:
                bucket_key = '90_plus'

            buckets[bucket_key]['total'] += amount
            buckets[bucket_key]['count'] += 1

            partner = bill.get('partner_id')
            partner_id = partner[0] if isinstance(partner, (list, tuple)) else None
            partner_name = partner[1] if isinstance(partner, (list, tuple)) else 'Unknown'

            if partner_id not in vendor_aging:
                vendor_aging[partner_id] = {
                    'vendor_name': partner_name,
                    'current': 0, '1_30': 0, '31_60': 0, '61_90': 0, '90_plus': 0,
                    'total': 0,
                }
            vendor_aging[partner_id][bucket_key] += amount
            vendor_aging[partner_id]['total'] += amount

        vendor_rows = sorted(
            vendor_aging.values(),
            key=lambda x: x['total'],
            reverse=True
        )[:limit]

        for key in buckets:
            buckets[key]['total'] = round(buckets[key]['total'], 2)

        for row in vendor_rows:
            for key in ['current', '1_30', '31_60', '61_90', '90_plus', 'total']:
                row[key] = round(row[key], 2)

        return {
            'as_of_date': as_of_date.isoformat(),
            'buckets': buckets,
            'by_vendor': vendor_rows,
            'grand_total': round(grand_total, 2),
            'total_vendors': len(vendor_rows),
            'currency': currency,
        }
