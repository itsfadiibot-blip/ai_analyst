# -*- coding: utf-8 -*-
import re

from odoo.exceptions import AccessError, ValidationError

from .base_tool import BaseTool
from .registry import register_tool


@register_tool
class BossSqlReadonlyTool(BaseTool):
    name = 'boss_sql_readonly'
    description = (
        'Boss-only direct SQL read tool (strictly read-only). '
        'Use for flexible ad-hoc analytics when predefined tools cannot answer. '
        'Only single SELECT/CTE queries are allowed, with row/time limits and blocked sensitive tables.'
    )
    required_groups = ['ai_analyst.group_boss_open_query']
    parameters_schema = {
        'type': 'object',
        'properties': {
            'sql': {'type': 'string'},
            'limit': {'type': 'integer', 'minimum': 1, 'maximum': 500, 'default': 200},
        },
        'required': ['sql'],
    }

    # Strong deny-list for mutation/escalation vectors and sensitive internals
    _BLOCKED_KEYWORDS = {
        'insert', 'update', 'delete', 'drop', 'alter', 'truncate', 'create', 'replace',
        'grant', 'revoke', 'comment', 'vacuum', 'analyze', 'reindex', 'refresh',
        'copy', 'call', 'do', 'set', 'reset', 'show', 'explain', 'lock',
    }
    _BLOCKED_TABLE_PATTERNS = [
        r'\bir_attachment\b',
        r'\bres_users\b',
        r'\bmail_message\b',
        r'\bir_config_parameter\b',
        r'\bir_model_access\b',
        r'\bir_rule\b',
    ]

    def validate_params(self, params):
        validated = super().validate_params(params)
        sql = (validated.get('sql') or '').strip()
        if not sql:
            raise ValidationError('sql is required.')
        validated['sql'] = self._sanitize_sql(sql)
        return validated

    def execute(self, env, user, params):
        if not user.has_group('ai_analyst.group_boss_open_query'):
            raise AccessError('boss_sql_readonly requires group_boss_open_query')

        sql = params['sql']
        limit = params.get('limit', 200)

        # Statement timeout guard at transaction level
        env.cr.execute('SET LOCAL statement_timeout = %s', [10000])  # 10s

        wrapped = f"SELECT * FROM ({sql}) AS aiq LIMIT %s"
        env.cr.execute(wrapped, [limit])
        rows = env.cr.dictfetchall() or []

        columns = []
        if rows:
            columns = [
                {'key': k, 'label': k.replace('_', ' ').title(), 'type': 'string', 'align': 'left'}
                for k in rows[0].keys()
            ]

        return {
            'answer': 'Read-only SQL query executed successfully.',
            'kpis': [
                {'label': 'Rows Returned', 'value': str(len(rows))},
                {'label': 'Row Limit', 'value': str(limit)},
            ],
            'table': {'columns': columns, 'rows': rows, 'total_row': None},
            'chart': {},
            'actions': [],
            'meta': {
                'tool': self.name,
                'read_only': True,
                'applied_limit': limit,
            },
        }

    def _sanitize_sql(self, sql):
        # one statement only
        if ';' in sql.strip().rstrip(';'):
            raise ValidationError('Only one SQL statement is allowed.')

        normalized = re.sub(r'\s+', ' ', sql.strip()).lower()
        if not (normalized.startswith('select ') or normalized.startswith('with ')):
            raise ValidationError('Only SELECT/CTE read queries are allowed.')

        # keywords
        for kw in self._BLOCKED_KEYWORDS:
            if re.search(rf'\b{re.escape(kw)}\b', normalized):
                raise ValidationError(f'Blocked SQL keyword detected: {kw}')

        # comment channels
        if '--' in sql or '/*' in sql or '*/' in sql:
            raise ValidationError('SQL comments are not allowed.')

        # sensitive tables
        for pat in self._BLOCKED_TABLE_PATTERNS:
            if re.search(pat, normalized):
                raise ValidationError('Query touches restricted system/sensitive tables.')

        return sql
