# -*- coding: utf-8 -*-
import json
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AiAnalystSchemaRegistry(models.AbstractModel):
    _name = 'ai.analyst.schema.registry'
    _description = 'AI Analyst Schema Registry'

    CACHE_KEY = 'ai_analyst.schema_cache'
    CACHE_TS_KEY = 'ai_analyst.schema_cache_ts'
    MAX_FIELDS_PER_MODEL = 500

    DEFAULT_WHITELIST = [
        'product.template', 'product.product', 'sale.order', 'sale.order.line',
        'stock.quant', 'stock.move', 'account.move', 'account.move.line',
        'pos.order', 'pos.order.line', 'purchase.order', 'purchase.order.line',
        'product.category',
    ]

    @api.model
    def discover_models(self, whitelist=None):
        model_names = set(whitelist or self.DEFAULT_WHITELIST)
        custom_models = self.env['ir.model'].sudo().search([('model', '=like', 'x_%')]).mapped('model')
        model_names.update(custom_models)

        cache = {}
        for model_name in sorted(model_names):
            if model_name not in self.env:
                continue
            model = self.env[model_name]
            try:
                fields_meta = model.fields_get()
            except Exception:
                _logger.exception('Schema discovery failed for %s', model_name)
                continue

            entries = []
            for fname, meta in list(fields_meta.items())[: self.MAX_FIELDS_PER_MODEL]:
                entries.append({
                    'name': fname,
                    'string': meta.get('string') or fname,
                    'type': meta.get('type'),
                    'relation': meta.get('relation') or False,
                    'selection': meta.get('selection') or [],
                    'stored': bool(meta.get('store', True)),
                    'required': bool(meta.get('required', False)),
                    'help': meta.get('help') or '',
                    'is_custom': fname.startswith('x_'),
                })
            cache[model_name] = entries

        icp = self.env['ir.config_parameter'].sudo()
        icp.set_param(self.CACHE_KEY, json.dumps(cache))
        icp.set_param(self.CACHE_TS_KEY, fields.Datetime.now().isoformat())
        return cache

    @api.model
    def _load_cache(self):
        raw = self.env['ir.config_parameter'].sudo().get_param(self.CACHE_KEY)
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except Exception:
            return {}

    @api.model
    def _cache_is_stale(self):
        ts = self.env['ir.config_parameter'].sudo().get_param(self.CACHE_TS_KEY)
        if not ts:
            return True
        try:
            dt = fields.Datetime.from_string(ts)
            return fields.Datetime.now() - dt > timedelta(hours=24)
        except Exception:
            return True

    @api.model
    def get_schema(self, model_name):
        cache = self._load_cache()
        if self._cache_is_stale() or model_name not in cache:
            cache = self.discover_models()
        return cache.get(model_name, [])

    @api.model
    def get_prompt_context(self, model_names):
        cache = self._load_cache() or self.discover_models()
        lines = []
        for model_name in model_names or []:
            fields_meta = [f for f in cache.get(model_name, []) if f.get('stored')]
            chunks = []
            for f in fields_meta[:200]:
                chunks.append('%s (%s, %s)' % (f['name'], f['type'], f['string']))
            lines.append('%s: %s' % (model_name, ' | '.join(chunks)))
        return '\n'.join(lines)
