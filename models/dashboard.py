# -*- coding: utf-8 -*-
import json
import time
import hashlib
import threading
from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

_CACHE = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL_SECONDS = 60


class AiAnalystDashboard(models.Model):
    _name = 'ai.analyst.dashboard'
    _description = 'AI Analyst Dashboard'
    _order = 'id desc'

    name = fields.Char(required=True, default='My Dashboard')
    user_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user, index=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    is_default = fields.Boolean(default=True)
    widget_ids = fields.One2many('ai.analyst.dashboard.widget', 'dashboard_id', string='Widgets')

    @api.model
    def get_or_create_default(self, user=None):
        user = user or self.env.user
        dashboard = self.search([
            ('user_id', '=', user.id),
            ('company_id', '=', user.company_id.id),
            ('is_default', '=', True),
        ], limit=1)
        if dashboard:
            return dashboard
        return self.create({
            'name': 'My Dashboard',
            'user_id': user.id,
            'company_id': user.company_id.id,
            'is_default': True,
        })


class AiAnalystDashboardWidget(models.Model):
    _name = 'ai.analyst.dashboard.widget'
    _description = 'AI Analyst Dashboard Widget'
    _order = 'sequence asc, id asc'

    dashboard_id = fields.Many2one('ai.analyst.dashboard', required=True, ondelete='cascade', index=True)
    user_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user, index=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)

    tool_name = fields.Char(required=True)
    tool_args_json = fields.Text(required=True, default='{}')

    title = fields.Char(required=True, default='Widget')
    sequence = fields.Integer(default=10)
    width = fields.Integer(default=6)
    height = fields.Integer(default=4)
    refresh_interval_seconds = fields.Integer(default=300)
    last_run_at = fields.Datetime()
    active = fields.Boolean(default=True)

    @api.constrains('width', 'height')
    def _check_dimensions(self):
        for rec in self:
            if rec.width < 1 or rec.width > 12:
                raise ValidationError('Width must be between 1 and 12.')
            if rec.height < 1 or rec.height > 24:
                raise ValidationError('Height must be between 1 and 24.')

    def _parse_args(self):
        self.ensure_one()
        try:
            args = json.loads(self.tool_args_json or '{}')
            if not isinstance(args, dict):
                return {}
            return args
        except Exception:
            return {}

    def _cache_key(self, user):
        self.ensure_one()
        args_text = self.tool_args_json or '{}'
        payload = f"{user.id}:{self.company_id.id}:{self.tool_name}:{args_text}"
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def _cache_get(self, key):
        now = time.time()
        with _CACHE_LOCK:
            item = _CACHE.get(key)
            if not item:
                return None
            if now - item['ts'] > _CACHE_TTL_SECONDS:
                _CACHE.pop(key, None)
                return None
            return item['value']

    def _cache_set(self, key, value):
        with _CACHE_LOCK:
            _CACHE[key] = {'ts': time.time(), 'value': value}

    def _normalize_result(self, tool_name, args, raw):
        if isinstance(raw, dict) and any(k in raw for k in ('answer', 'kpis', 'table', 'chart', 'actions', 'error')):
            out = dict(raw)
            out.setdefault('answer', out.get('answer') or 'Result generated.')
            out.setdefault('meta', {})
            out['meta'].setdefault('tool_calls', [{'tool': tool_name, 'params': args}])
            return out

        response = {
            'answer': f'Result for tool {tool_name}.',
            'kpis': [],
            'meta': {
                'tool_calls': [{'tool': tool_name, 'params': args}],
            },
        }

        if isinstance(raw, dict):
            summary = raw.get('summary') or {}
            currency = raw.get('currency') or ''
            if isinstance(summary, dict):
                for key, value in summary.items():
                    if isinstance(value, (int, float, str)):
                        label = key.replace('_', ' ').title()
                        if isinstance(value, (int, float)) and 'revenue' in key and currency:
                            val = f"{currency} {value:,.2f}"
                        else:
                            val = str(value)
                        response['kpis'].append({'label': label, 'value': val})

            if tool_name == 'get_pos_vs_online_summary' and isinstance(summary, dict):
                pos = (summary.get('pos') or {})
                online = (summary.get('online') or {})
                table = {
                    'columns': [
                        {'key': 'channel', 'label': 'Channel', 'type': 'string', 'align': 'left'},
                        {'key': 'revenue', 'label': 'Revenue', 'type': 'number', 'align': 'right'},
                        {'key': 'count', 'label': 'Count', 'type': 'number', 'align': 'right'},
                        {'key': 'avg', 'label': 'Avg Value', 'type': 'number', 'align': 'right'},
                        {'key': 'pct', 'label': '% of Total', 'type': 'percentage', 'align': 'right'},
                    ],
                    'rows': [
                        {
                            'channel': 'POS',
                            'revenue': pos.get('revenue', 0),
                            'count': pos.get('transaction_count', 0),
                            'avg': pos.get('avg_ticket', 0),
                            'pct': pos.get('percentage', 0),
                        },
                        {
                            'channel': 'Online',
                            'revenue': online.get('revenue', 0),
                            'count': online.get('order_count', 0),
                            'avg': online.get('avg_order_value', 0),
                            'pct': online.get('percentage', 0),
                        },
                    ],
                }
                response['table'] = table
                response['chart'] = {
                    'type': 'doughnut',
                    'title': 'Revenue Split',
                    'labels': ['POS', 'Online'],
                    'datasets': [
                        {
                            'label': 'Revenue',
                            'data': [pos.get('revenue', 0), online.get('revenue', 0)],
                        }
                    ],
                }

            elif isinstance(raw.get('rows'), list):
                rows = raw.get('rows', [])
                if rows:
                    first = rows[0]
                    cols = []
                    for k in first.keys():
                        cols.append({'key': k, 'label': str(k).replace('_', ' ').title(), 'type': 'string', 'align': 'left'})
                    response['table'] = {'columns': cols, 'rows': rows[:200]}

            if not response['kpis'] and 'table' not in response:
                response['answer'] = json.dumps(raw, default=str)[:1200]

        return response

    def execute_dynamic(self, user=None, bypass_cache=False):
        self.ensure_one()
        user = user or self.env.user

        if self.user_id.id != user.id and not user.has_group('ai_analyst.group_ai_admin'):
            raise AccessError('Access denied.')

        args = self._parse_args()
        cache_key = self._cache_key(user)

        if not bypass_cache:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

        from odoo.addons.ai_analyst.tools.registry import get_available_tools_for_user
        tools = get_available_tools_for_user(user)
        if self.tool_name not in tools:
            result = {
                'answer': f'Tool "{self.tool_name}" is no longer available.',
                'error': f'Tool "{self.tool_name}" is no longer available.',
                'meta': {'tool_calls': [{'tool': self.tool_name, 'params': args}]},
            }
            self._cache_set(cache_key, result)
            return result

        tool = tools[self.tool_name]
        try:
            params = tool.validate_params(args)
            env_as_user = self.env(user=user.id)
            raw = tool.execute(env_as_user, user, params)
            normalized = self._normalize_result(self.tool_name, params, raw)
        except Exception as e:
            normalized = {
                'answer': 'Widget execution failed.',
                'error': str(e),
                'meta': {'tool_calls': [{'tool': self.tool_name, 'params': args}]},
            }

        # Bug #4 fix: Use user.id instead of user recordset
        user_id = user.id if hasattr(user, 'id') else int(user)
        self.with_user(user_id).write({'last_run_at': fields.Datetime.now()})
        self._cache_set(cache_key, normalized)
        return normalized
