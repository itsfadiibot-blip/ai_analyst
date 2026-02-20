# -*- coding: utf-8 -*-
from odoo.exceptions import AccessError

from .base_tool import BaseTool
from .registry import register_tool


@register_tool
class BossOpenQueryTool(BaseTool):
    name = 'boss_open_query'
    description = 'Boss-only direct read-only query plan execution over ORM with pagination and async export.'
    required_groups = ['ai_analyst.group_boss_open_query']
    parameters_schema = {
        'type': 'object',
        'properties': {
            'user_query': {'type': 'string'},
            'query_plan': {'type': 'object'},
            'mode': {'type': 'string', 'enum': ['auto', 'inline', 'paginated', 'async_export'], 'default': 'auto'},
            'force_export': {'type': 'boolean', 'default': False},
        },
        'required': ['query_plan'],
    }

    def validate_params(self, params):
        validated = super().validate_params(params)
        qp = params.get('query_plan')
        if not isinstance(qp, dict):
            raise ValueError('query_plan must be an object.')
        validated['query_plan'] = qp
        return validated

    def execute(self, env, user, params):
        if not user.has_group('ai_analyst.group_boss_open_query'):
            raise AccessError('boss_open_query requires group_boss_open_query')

        svc = env['ai.analyst.boss.open.query.service'].with_user(user)
        user_query = (params.get('user_query') or '').strip()
        plan = svc.validate_and_normalize_plan(params['query_plan'])
        cost = svc.estimate_cost(plan)
        field_mapping = svc.build_field_mapping_meta(user_query, plan)

        requested_mode = params.get('mode') or 'auto'
        mode = cost['recommended_mode'] if requested_mode == 'auto' else requested_mode
        if params.get('force_export'):
            mode = 'async_export'

        if plan['options'].get('preview_only'):
            mode = 'inline'
            plan['pagination']['limit'] = plan['options']['preview_limit']

        if mode == 'async_export':
            job = env['ai.analyst.boss.export.job'].with_user(user).create({
                'name': 'Boss Open Query Export',
                'requested_by': user.id,
                'query_plan': plan,
                'state': 'queued',
            })
            actions = [
                {
                    'id': 'check_export_status',
                    'type': 'export',
                    'label': 'Check Export Status',
                    'enabled': True,
                    'params': {'job_id': job.id, 'job_token': job.job_token},
                }
            ]
            return self._response(
                answer='Export job queued. Use the action to check status or download when completed.',
                kpis=[{'label': 'Estimated Rows', 'value': str(cost['estimated_rows'])}],
                table={'columns': [], 'rows': [], 'total_row': None},
                chart={},
                actions=actions,
                meta={'mode': mode, 'cost_estimate': cost, 'export_job_id': job.id, 'export_job_token': job.job_token, 'field_mapping': field_mapping, 'query_plan_validated': True},
            )

        rows = svc.execute_page(plan)
        total_count = svc.count_total(plan)
        limit = plan['pagination']['limit']
        offset = plan['pagination']['offset']
        has_more = (offset + len(rows)) < total_count
        next_offset = offset + limit if has_more else offset
        next_cursor = svc.encode_cursor(next_offset) if has_more else False

        actions = []
        if has_more:
            actions.append({
                'id': 'next_page',
                'type': 'pagination',
                'label': 'Load Next %s' % limit,
                'enabled': True,
                'params': {
                    'query_plan': {**plan, 'pagination': {**plan['pagination'], 'offset': next_offset, 'cursor': next_cursor}},
                    'mode': mode,
                },
            })
        actions.append({
            'id': 'export_csv',
            'type': 'export',
            'label': 'Export CSV',
            'enabled': True,
            'params': {'query_plan': plan, 'mode': 'async_export'},
        })

        columns = []
        if rows:
            columns = [
                {'key': k, 'label': k.replace('_', ' ').title(), 'type': 'string', 'align': 'left'}
                for k in rows[0].keys()
            ]
        table = {'columns': columns, 'rows': rows, 'total_row': None}

        chart = {}
        chart_request = (plan.get('options') or {}).get('chart_request') or {}
        if chart_request and rows:
            x_field = chart_request.get('x_axis')
            y_field = chart_request.get('y_axis')
            if x_field and y_field:
                chart = {
                    'type': chart_request.get('type') or 'bar',
                    'title': chart_request.get('title') or 'Chart',
                    'labels': [str(r.get(x_field)) for r in rows],
                    'datasets': [{'label': y_field, 'data': [r.get(y_field, 0) for r in rows]}],
                }

        return self._response(
            answer='Query executed successfully.',
            kpis=[
                {'label': 'Rows Returned', 'value': str(len(rows))},
                {'label': 'Estimated Total', 'value': str(cost['estimated_rows'])},
            ],
            table=table,
            chart=chart,
            actions=actions,
            meta={
                'mode': mode,
                'cost_estimate': cost,
                'pagination': {
                    'total': total_count,
                    'offset': offset,
                    'limit': limit,
                    'has_more': has_more,
                    'next_offset': next_offset if has_more else False,
                    'next_cursor': next_cursor,
                },
                'field_mapping': field_mapping,
                'query_plan_validated': True,
            },
        )

    def _response(self, answer, kpis, table, chart, actions, meta):
        return {
            'answer': answer,
            'kpis': kpis,
            'table': table,
            'chart': chart,
            'actions': actions,
            'meta': meta,
        }
