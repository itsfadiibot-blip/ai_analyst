# -*- coding: utf-8 -*-
import hashlib
import json
from datetime import timedelta

from odoo import api, fields, models


class AiAnalystQueryCache(models.Model):
    _name = 'ai.analyst.query.cache'
    _description = 'AI Analyst Query Cache'
    _order = 'write_date desc'

    key = fields.Char(required=True, index=True)
    payload = fields.Text(required=True)
    expires_at = fields.Datetime(required=True, index=True)

    _sql_constraints = [('uq_cache_key', 'unique(key)', 'Cache key must be unique')]

    @api.model
    def build_key(self, plan):
        src = json.dumps(plan or {}, sort_keys=True, default=str)
        return hashlib.sha256(src.encode('utf-8')).hexdigest()

    @api.model
    def get_cached(self, plan):
        key = self.build_key(plan)
        rec = self.search([('key', '=', key), ('expires_at', '>', fields.Datetime.now())], limit=1)
        return json.loads(rec.payload) if rec else None

    @api.model
    def set_cached(self, plan, payload, ttl_seconds=300):
        key = self.build_key(plan)
        expires = fields.Datetime.now() + timedelta(seconds=ttl_seconds)
        rec = self.search([('key', '=', key)], limit=1)
        vals = {'payload': json.dumps(payload, default=str), 'expires_at': expires}
        if rec:
            rec.write(vals)
        else:
            self.create(dict(vals, key=key))

    @api.model
    def purge_expired(self):
        self.search([('expires_at', '<=', fields.Datetime.now())]).unlink()
