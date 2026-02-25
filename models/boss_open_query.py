# -*- coding: utf-8 -*-
import base64
import csv
import io
import json
import time
import uuid
from datetime import datetime, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class AiAnalystBossOpenQueryService(models.AbstractModel):
    _name = 'ai.analyst.boss.open.query.service'
    _description = 'AI Analyst Boss Open Query Service'

    INLINE_MAX_ROWS = 500
    ASYNC_THRESHOLD_ROWS = 10000
    PAGINATED_MAX_TOTAL = 50000
    MAX_FIELDS = 50
    MAX_AGGS = 20
    MAX_GROUP_BY = 10
    MAX_DEPTH = 5
    CURSOR_TTL_SECONDS = 3600
    ALLOWED_DOMAIN_OPERATORS = {
        '=', '!=', '>', '>=', '<', '<=', '=?', '=like', '=ilike',
        'like', 'not like', 'ilike', 'not ilike', 'in', 'not in', 'child_of', 'parent_of'
    }
    ALLOWED_LOGICAL = {'&', '|', '!'}
    ALLOWED_AGG_OPS = {'sum', 'avg', 'count', 'count_distinct', 'min', 'max'}

    def _check_boss_access(self, user=None):
        user = user or self.env.user
        if not user.has_group('ai_analyst.group_boss_open_query'):
            raise AccessError(_('boss_open_query requires AI Analyst Boss Open Query Access.'))

    def validate_and_normalize_plan(self, plan):
        self._check_boss_access()
        if not isinstance(plan, dict):
            raise ValidationError(_('query_plan must be an object.'))

        normalized = {
            'version': str(plan.get('version') or '1.0'),
            'target_model': plan.get('target_model'),
            'domain': plan.get('domain') or [],
            'fields': plan.get('fields') or [],
            'aggregations': plan.get('aggregations') or [],
            'group_by': plan.get('group_by') or [],
            'order_by': plan.get('order_by') or [],
            'pagination': plan.get('pagination') or {},
            'options': plan.get('options') or {},
        }
        if normalized['version'] != '1.0':
            raise ValidationError(_('Unsupported query plan version.'))
        model_name = normalized['target_model']
        if not model_name or not isinstance(model_name, str) or model_name not in self.env:
            raise ValidationError(_('Invalid target_model.'))

        model = self.env[model_name]
        if not model.check_access_rights('read', raise_exception=False):
            raise AccessError(_('No read access to model %s') % model_name)

        self._validate_domain(model, normalized['domain'])
        self._normalize_fields(model, normalized)
        self._normalize_aggregations(model, normalized)
        self._normalize_group_by(model, normalized)
        self._normalize_order_by(normalized)
        self._normalize_pagination(normalized)
        self._normalize_options(normalized)
        return normalized

    def _resolve_field(self, model, field_path):
        parts = (field_path or '').split('.')
        if len(parts) > self.MAX_DEPTH:
            raise ValidationError(_('Field path depth exceeded for %s') % field_path)
        current_model = model
        current_field = None
        for idx, part in enumerate(parts):
            current_field = current_model._fields.get(part)
            if not current_field:
                raise ValidationError(_('Field %s not found on %s') % (field_path, current_model._name))
            if idx < len(parts) - 1:
                if current_field.type not in ('many2one',):
                    raise ValidationError(_('Only many2one traversal is allowed for %s') % field_path)
                current_model = self.env[current_field.comodel_name]
        return current_field

    def _validate_domain(self, model, domain):
        if not isinstance(domain, list):
            raise ValidationError(_('Domain must be an array.'))
        for term in domain:
            if isinstance(term, str):
                if term not in self.ALLOWED_LOGICAL:
                    raise ValidationError(_('Invalid logical operator in domain: %s') % term)
                continue
            if not isinstance(term, (list, tuple)) or len(term) < 3:
                raise ValidationError(_('Invalid domain term: %s') % str(term))
            field_name, op = term[0], term[1]
            self._resolve_field(model, field_name)
            if op not in self.ALLOWED_DOMAIN_OPERATORS:
                raise ValidationError(_('Operator %s is not allowed.') % op)
        model.search_count(domain)

    def _normalize_fields(self, model, normalized):
        fields_spec = normalized['fields']
        if not isinstance(fields_spec, list):
            raise ValidationError(_('fields must be an array.'))
        if len(fields_spec) > self.MAX_FIELDS:
            raise ValidationError(_('Too many fields. Max %s') % self.MAX_FIELDS)
        out = []
        for f in fields_spec:
            if not isinstance(f, dict) or not f.get('name'):
                raise ValidationError(_('Each field descriptor requires name.'))
            self._resolve_field(model, f['name'])
            out.append({
                'name': f['name'],
                'alias': f.get('alias') or f['name'].replace('.', '_'),
                'extract': f.get('extract') or False,
            })
        normalized['fields'] = out

    def _normalize_aggregations(self, model, normalized):
        aggs = normalized['aggregations']
        if not isinstance(aggs, list):
            raise ValidationError(_('aggregations must be an array.'))
        if len(aggs) > self.MAX_AGGS:
            raise ValidationError(_('Too many aggregations.'))
        out = []
        for a in aggs:
            if not isinstance(a, dict):
                raise ValidationError(_('Invalid aggregation descriptor.'))
            field_name = a.get('field')
            op = a.get('operator')
            if not field_name or op not in self.ALLOWED_AGG_OPS:
                raise ValidationError(_('Invalid aggregation descriptor.'))
            self._resolve_field(model, field_name)
            alias = a.get('alias') or ('%s_%s' % (field_name.replace('.', '_'), op))
            out.append({'field': field_name, 'operator': op, 'alias': alias})
        normalized['aggregations'] = out

    def _normalize_group_by(self, model, normalized):
        gb = normalized['group_by']
        if not isinstance(gb, list):
            raise ValidationError(_('group_by must be an array.'))
        if len(gb) > self.MAX_GROUP_BY:
            raise ValidationError(_('Too many group_by fields.'))
        out = []
        for g in gb:
            if not isinstance(g, dict) or not g.get('field'):
                raise ValidationError(_('Invalid group_by descriptor.'))
            fld = self._resolve_field(model, g['field'])
            granularity = g.get('granularity')
            if granularity and fld.type not in ('date', 'datetime'):
                raise ValidationError(_('Granularity is only valid for date/datetime fields.'))
            out.append({
                'field': g['field'],
                'granularity': granularity or False,
                'alias': g.get('alias') or g['field'].replace('.', '_'),
            })
        normalized['group_by'] = out
        if normalized['aggregations'] and normalized['fields'] and not out:
            raise ValidationError(_('Aggregations with fields requires group_by.'))

    def _normalize_order_by(self, normalized):
        order_by = normalized['order_by']
        if not isinstance(order_by, list):
            raise ValidationError(_('order_by must be an array.'))
        out = []
        for o in order_by[:10]:
            if not isinstance(o, dict) or not o.get('field'):
                continue
            out.append({'field': o['field'], 'direction': 'desc' if o.get('direction') == 'desc' else 'asc'})
        normalized['order_by'] = out

    def _normalize_pagination(self, normalized):
        p = normalized['pagination'] if isinstance(normalized['pagination'], dict) else {}
        mode = p.get('mode') or 'offset'
        if mode not in ('offset', 'cursor'):
            raise ValidationError(_('pagination.mode must be offset or cursor.'))
        limit = int(p.get('limit') or 100)
        limit = max(1, min(1000, limit))
        offset = int(p.get('offset') or 0)
        offset = max(0, min(100000, offset))
        cursor = p.get('cursor')
        if mode == 'cursor':
            decoded = self.decode_cursor(cursor) if cursor else {'offset': 0}
            offset = int(decoded.get('offset') or 0)
        normalized['pagination'] = {'mode': mode, 'limit': limit, 'offset': offset, 'cursor': cursor or False}

    def _normalize_options(self, normalized):
        opts = normalized['options'] if isinstance(normalized['options'], dict) else {}
        normalized['options'] = {
            'preview_only': bool(opts.get('preview_only', False)),
            'preview_limit': max(1, min(100, int(opts.get('preview_limit', 10) or 10))),
            'include_metadata': bool(opts.get('include_metadata', True)),
            'chart_request': opts.get('chart_request') or {},
            'format': opts.get('format') if opts.get('format') in ('json', 'csv', 'xlsx') else 'json',
        }

    def estimate_cost(self, normalized):
        model = self.env[normalized['target_model']]
        start = time.time()
        try:
            est_rows = model.search_count(normalized['domain'])
        except Exception:
            est_rows = 10000
        complexity = min(len(normalized['fields']), 20)
        complexity += min(len(normalized['aggregations']) * 3 + len(normalized['group_by']) * 5, 25)
        complexity += min(sum([len((f.get('name') or '').split('.')) for f in normalized['fields']]) * 2, 25)
        complexity += min(len(normalized['domain']) * 2, 30)
        est_seconds = round(0.1 + (est_rows * 0.001 * (max(complexity, 1) / 50.0)), 2)
        if normalized['options']['preview_only']:
            mode = 'inline'
        elif est_rows > self.ASYNC_THRESHOLD_ROWS or est_rows > self.PAGINATED_MAX_TOTAL:
            mode = 'async_export'
        elif est_rows > self.INLINE_MAX_ROWS:
            mode = 'paginated'
        else:
            mode = 'inline'
        return {
            'estimated_rows': est_rows,
            'complexity_score': complexity,
            'estimated_seconds': est_seconds,
            'recommended_mode': mode,
            'estimation_time_ms': int((time.time() - start) * 1000),
        }

    def execute_page(self, normalized):
        model = self.env[normalized['target_model']]
        if normalized['aggregations']:
            return self._execute_aggregated(model, normalized)
        return self._execute_list(model, normalized)

    def _execute_list(self, model, normalized):
        p = normalized['pagination']
        records = model.search(normalized['domain'], limit=p['limit'], offset=p['offset'], order=self._order_string(normalized))
        fields_to_read = []
        for f in normalized['fields']:
            base = f['name'].split('.')[0]
            if base not in fields_to_read:
                fields_to_read.append(base)
        raw_rows = records.read(fields_to_read)
        out = []
        for rec in raw_rows:
            row = {}
            for f in normalized['fields']:
                row[f['alias']] = self._extract_path_value(model, rec, f['name'])
            out.append(row)
        return out

    def _extract_path_value(self, model, rec, path):
        parts = path.split('.')
        current_model = model
        current_value = rec
        for idx, part in enumerate(parts):
            if isinstance(current_value, dict):
                value = current_value.get(part)
            else:
                value = False
            field = current_model._fields.get(part)
            if idx == len(parts) - 1:
                if isinstance(value, tuple):
                    return value[1]
                return value
            if not field or field.type != 'many2one':
                return False
            if isinstance(value, tuple) and value:
                rel_rec = self.env[field.comodel_name].browse(value[0]).read([parts[idx + 1]])
                current_value = rel_rec[0] if rel_rec else {}
            else:
                return False
            current_model = self.env[field.comodel_name]
        return False

    def _execute_aggregated(self, model, normalized):
        p = normalized['pagination']
        agg_fields = []
        for a in normalized['aggregations']:
            if a['operator'] == 'count':
                agg_fields.append('__count')
            elif a['operator'] == 'count_distinct':
                agg_fields.append('%s:count_distinct' % a['field'])
            else:
                agg_fields.append('%s:%s' % (a['field'], a['operator']))
        groupby = []
        for g in normalized['group_by']:
            if g['granularity']:
                groupby.append('%s:%s' % (g['field'], g['granularity']))
            else:
                groupby.append(g['field'])
        rows = model.read_group(
            normalized['domain'],
            agg_fields + [g['field'] for g in normalized['group_by']],
            groupby,
            offset=p['offset'],
            limit=p['limit'],
            orderby=self._orderby_for_read_group(normalized),
            lazy=False,
        )
        out = []
        for rr in rows:
            row = {}
            for g in normalized['group_by']:
                val = rr.get(g['field'])
                if isinstance(val, tuple):
                    val = val[1]
                row[g['alias']] = val
            for a in normalized['aggregations']:
                if a['operator'] == 'count':
                    row[a['alias']] = rr.get('__count', 0)
                elif a['operator'] == 'count_distinct':
                    row[a['alias']] = rr.get('%s_count_distinct' % a['field'], 0)
                else:
                    row[a['alias']] = rr.get('%s_%s' % (a['field'], a['operator']), 0)
            out.append(row)
        return out

    def _order_string(self, normalized):
        order_by = normalized.get('order_by') or []
        parts = ['%s %s' % (o['field'], o['direction']) for o in order_by]
        return ', '.join(parts) if parts else 'id desc'

    def _orderby_for_read_group(self, normalized):
        return ', '.join(['%s %s' % (o['field'], o['direction']) for o in (normalized.get('order_by') or [])])

    def encode_cursor(self, offset):
        payload = {
            'offset': int(offset),
            'exp': int((datetime.utcnow() + timedelta(seconds=self.CURSOR_TTL_SECONDS)).timestamp()),
        }
        return base64.b64encode(json.dumps(payload).encode('utf-8')).decode('utf-8')

    def decode_cursor(self, cursor):
        if not cursor:
            return {'offset': 0}
        try:
            payload = json.loads(base64.b64decode(cursor).decode('utf-8'))
            exp = int(payload.get('exp') or 0)
            if exp and exp < int(datetime.utcnow().timestamp()):
                raise ValidationError(_('Cursor token expired.'))
            return payload
        except Exception:
            raise ValidationError(_('Invalid cursor token.'))


class AiAnalystBossExportJob(models.Model):
    _name = 'ai.analyst.boss.export.job'
    _description = 'AI Analyst Boss Export Job'
    _order = 'create_date desc'

    name = fields.Char(required=True, default=lambda self: _('Boss Export'))
    job_token = fields.Char(required=True, copy=False, index=True, default=lambda self: uuid.uuid4().hex)
    state = fields.Selection([('queued', 'Queued'), ('processing', 'Processing'), ('completed', 'Completed'), ('failed', 'Failed')], default='queued', index=True)
    requested_by = fields.Many2one('res.users', required=True, default=lambda self: self.env.user, index=True)
    query_plan = fields.Json(required=True)
    total_rows = fields.Integer(default=0)
    processed_rows = fields.Integer(default=0)
    progress_percent = fields.Float(default=0.0)
    csv_content = fields.Binary(attachment=True)
    csv_filename = fields.Char()
    error_message = fields.Text()
    finished_at = fields.Datetime()

    def action_process(self):
        for job in self:
            if job.state in ('completed', 'failed'):
                continue
            job._run_export()

    @api.model
    def cron_process_queued_exports(self, limit=5):
        jobs = self.search([('state', '=', 'queued')], limit=limit)
        jobs.action_process()

    def _run_export(self):
        self.ensure_one()
        svc = self.env['ai.analyst.boss.open.query.service'].with_user(self.requested_by)
        try:
            self.write({'state': 'processing', 'error_message': False})
            plan = dict(self.query_plan or {})
            plan['pagination'] = {'mode': 'offset', 'limit': 1000, 'offset': 0}
            normalized = svc.validate_and_normalize_plan(plan)
            total = self.env[normalized['target_model']].search_count(normalized['domain'])
            self.write({'total_rows': total})

            output = io.StringIO()
            writer = csv.writer(output)
            wrote_header = False
            offset = 0
            while True:
                normalized['pagination']['offset'] = offset
                rows = svc.execute_page(normalized)
                if not rows:
                    break
                if not wrote_header:
                    writer.writerow(list(rows[0].keys()))
                    wrote_header = True
                for row in rows:
                    writer.writerow([row.get(k) for k in row.keys()])
                offset += len(rows)
                pct = 100.0 if total <= 0 else min(99.0, (offset / float(total)) * 100.0)
                self.write({'processed_rows': offset, 'progress_percent': pct})
                if not self.env.registry.in_test_mode():
                    self.env.cr.commit()

            payload = output.getvalue().encode('utf-8-sig')
            self.write({
                'csv_content': base64.b64encode(payload),
                'csv_filename': 'boss_open_query_%s.csv' % fields.Date.today(),
                'state': 'completed',
                'progress_percent': 100.0,
                'processed_rows': offset,
                'finished_at': fields.Datetime.now(),
            })
        except Exception as e:
            self.write({'state': 'failed', 'error_message': str(e), 'finished_at': fields.Datetime.now()})
