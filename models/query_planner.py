# -*- coding: utf-8 -*-
import json
import os
import re
import time
from datetime import datetime, timedelta

from odoo import api, models


class AiAnalystQueryPlanner(models.AbstractModel):
    _name = 'ai.analyst.query.planner'
    _description = 'AI Analyst Query Planner'

    _KB_INDEX_CACHE = {
        'path': '',
        'mtime': 0.0,
        'loaded_at': 0.0,
        'index': None,
    }

    @api.model
    def plan(self, user, question, conversation_context=None, tier='cheap'):
        q = (question or '').strip()
        ql = q.lower()
        tokens = self._tokenize(q)
        terms = [t for t in re.split(r'[^a-zA-Z0-9_]+', q) if len(t) > 2]
        resolver = self.env['ai.analyst.field.resolver']
        resolved = []
        for term in terms[:8]:
            resolved.extend(resolver.resolve(term))

        kb_index = self._load_kb_index()
        model_scores = {}
        for token in tokens:
            for model_name in (kb_index.get('keyword_to_models', {}).get(token) or []):
                model_scores[model_name] = model_scores.get(model_name, 0) + 1

        explicit_model = self._map_intent_to_model(ql)
        primary_model = 'sale.order.line'
        if explicit_model:
            primary_model = explicit_model
            model_scores[primary_model] = model_scores.get(primary_model, 0) + 5
        if resolved and resolved[0].get('model') in self.env:
            primary_model = resolved[0]['model']
            model_scores[primary_model] = model_scores.get(primary_model, 0) + 2
        if model_scores:
            candidate = max(model_scores.items(), key=lambda kv: kv[1])[0]
            if candidate in self.env:
                primary_model = candidate

        fields = []
        for r in resolved[:4]:
            if r['model'] == primary_model:
                fields.append(r['field_path'])
        if not fields:
            if primary_model == 'product.template':
                fields = [f for f in ['name', 'default_code', 'id'] if f in self.env[primary_model]._fields][:2] or ['id']
            else:
                fields = ['id']

        method = 'search_read'
        if any(k in ql for k in ['count', 'how many', 'number of']):
            method = 'search_count'
        if any(k in ql for k in ['by ', 'group', 'per ']):
            method = 'read_group'

        domain = []
        domain += self._extract_time_domain(ql)
        domain += self._extract_keyword_domain(primary_model, ql)
        if primary_model == 'product.template' and self._wants_lifestyle_image_count(ql):
            if self._kb_or_model_has_field(kb_index, primary_model, 'has_lifestyle'):
                domain.append(('has_lifestyle', '=', True))
            elif self._kb_or_model_has_field(kb_index, primary_model, 'studio_shoot_image'):
                domain.append(('studio_shoot_image', '=', True))
            elif self._kb_or_model_has_field(kb_index, primary_model, 'ai_generated_image'):
                domain.append(('ai_generated_image', '=', True))
            elif self._kb_or_model_has_field(kb_index, primary_model, 'image_1920'):
                domain.append(('image_1920', '!=', False))

        step = {
            'id': 'step_1',
            'model': primary_model,
            'method': method,
            'domain': domain,
            'fields': fields,
            'group_by': [fields[0]] if method == 'read_group' else [],
            'aggregations': [{'field': 'id', 'op': 'count', 'alias': 'count'}] if method == 'read_group' else [],
            'limit': 80,
            'order': 'id desc',
        }

        return {
            'steps': [step],
            'computed_metrics': [],
            'output_format': 'table' if method != 'search_count' else 'single_value',
            'meta': {
                'planner_tier': tier,
                'resolved_fields': resolved,
                'explicit_model_match': explicit_model or '',
                'kb_models_considered': sorted(model_scores.items(), key=lambda kv: kv[1], reverse=True)[:5],
                'kb_file_used': kb_index.get('kb_path', ''),
            }
        }

    def _wants_lifestyle_image_count(self, query_lower):
        return ('lifestyle' in query_lower and 'image' in query_lower) or ('has lifestyle' in query_lower)

    def _tokenize(self, text):
        return [t for t in re.findall(r'[a-zA-Z0-9_]+', (text or '').lower()) if len(t) > 1]

    def _map_intent_to_model(self, query_lower):
        # Deterministic routing for business vocabulary used by your users.
        if any(p in query_lower for p in ['online orders', 'online order', 'sales orders', 'sales order', 'sale orders', 'sale order']):
            return 'sale.order'
        if any(p in query_lower for p in ['pos orders', 'pos order', 'store orders', 'store order', 'in store orders', 'in-store orders']):
            return 'pos.order'
        if any(p in query_lower for p in ['skus', 'sku', 'variants', 'variant']):
            return 'product.product'
        if any(p in query_lower for p in ['products', 'product']):
            return 'product.template'
        return False

    def _extract_time_domain(self, query_lower):
        domain = []
        m_days = re.search(r'within\s+last\s+(\d+)\s+day', query_lower)
        if m_days:
            days = int(m_days.group(1))
            dt = datetime.utcnow() - timedelta(days=max(1, days))
            domain.append(('create_date', '>=', dt.strftime('%Y-%m-%d %H:%M:%S')))
            return domain

        if 'last month' in query_lower:
            today = datetime.utcnow().date()
            first_this_month = today.replace(day=1)
            last_month_end = first_this_month - timedelta(days=1)
            last_month_start = last_month_end.replace(day=1)
            domain.append(('create_date', '>=', last_month_start.strftime('%Y-%m-%d 00:00:00')))
            domain.append(('create_date', '<=', last_month_end.strftime('%Y-%m-%d 23:59:59')))
        return domain

    def _extract_keyword_domain(self, model_name, query_lower):
        if model_name not in ('product.template', 'product.product'):
            return []

        # Patterns like "hero products" / "mayoral products"
        m = re.search(r'([a-z0-9_-]{3,})\s+products?\b', query_lower)
        if not m:
            return []
        keyword = (m.group(1) or '').strip()
        if keyword in {'top', 'new', 'all', 'last', 'best'}:
            return []

        model = self.env[model_name]
        text_fields = [f for f in ('name', 'default_code', 'barcode') if f in model._fields]
        if not text_fields:
            return []

        if len(text_fields) == 1:
            return [(text_fields[0], 'ilike', keyword)]

        # OR domain across available text fields.
        domain = []
        for _ in range(len(text_fields) - 1):
            domain.append('|')
        for fname in text_fields:
            domain.append((fname, 'ilike', keyword))
        return domain

    def _kb_or_model_has_field(self, kb_index, model_name, field_name):
        if field_name in (kb_index.get('model_fields', {}).get(model_name) or set()):
            return True
        model = self.env[model_name] if model_name in self.env else None
        return bool(model and field_name in model._fields)

    def _default_kb_path(self):
        module_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
        custom_dir = os.path.abspath(os.path.join(module_dir, os.pardir))
        return os.path.join(custom_dir, 'JuniorCouture_Odoo_KnowledgeBase_merged_v1.json')

    def _load_kb_index(self):
        """Load and cache a compact keyword index from the KB JSON."""
        cache = self._KB_INDEX_CACHE
        kb_path = self.env['ir.config_parameter'].sudo().get_param(
            'ai_analyst.kb_json_path', self._default_kb_path()
        )
        now = time.time()
        try:
            mtime = os.path.getmtime(kb_path)
        except OSError:
            return {'keyword_to_models': {}, 'model_fields': {}, 'kb_path': kb_path}

        if (
            cache.get('index') is not None
            and cache.get('path') == kb_path
            and cache.get('mtime') == mtime
            and (now - (cache.get('loaded_at') or 0.0)) < 300.0
        ):
            return cache['index']

        try:
            with open(kb_path, 'r', encoding='utf-8') as fh:
                payload = json.load(fh)
        except Exception:
            return {'keyword_to_models': {}, 'model_fields': {}, 'kb_path': kb_path}

        models = payload.get('models') or {}
        keyword_to_models = {}
        model_fields = {}
        for model_name, meta in models.items():
            if not isinstance(meta, dict):
                continue
            fields = meta.get('fields') or {}
            if not isinstance(fields, dict):
                continue
            model_fields[model_name] = set(fields.keys())

            terms = set(self._tokenize(model_name))
            terms.update(self._tokenize(meta.get('label') or ''))
            for alias in (meta.get('aliases') or []):
                terms.update(self._tokenize(alias))
            for fname, fmeta in fields.items():
                terms.update(self._tokenize(fname))
                if isinstance(fmeta, dict):
                    terms.update(self._tokenize(fmeta.get('label') or ''))
                    terms.update(self._tokenize(fmeta.get('description') or ''))

            for term in terms:
                keyword_to_models.setdefault(term, set()).add(model_name)

        index = {
            'keyword_to_models': keyword_to_models,
            'model_fields': model_fields,
            'kb_path': kb_path,
        }
        cache.update({
            'path': kb_path,
            'mtime': mtime,
            'loaded_at': now,
            'index': index,
        })
        return index
