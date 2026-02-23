# -*- coding: utf-8 -*-
from difflib import SequenceMatcher

from odoo import api, models


class AiAnalystFieldResolver(models.AbstractModel):
    _name = 'ai.analyst.field.resolver'
    _description = 'AI Analyst Field Resolver'

    @api.model
    def resolve(self, user_term, context_models=None):
        term = (user_term or '').strip().lower()
        if not term:
            return []

        matches = []
        matches.extend(self._resolve_dimension(term))
        matches.extend(self._resolve_schema(term, context_models=context_models))

        dedup = {}
        for m in sorted(matches, key=lambda x: x.get('confidence', 0), reverse=True):
            key = (m['model'], m['field_path'])
            dedup.setdefault(key, m)
        return list(dedup.values())[:3]

    def _resolve_dimension(self, term):
        out = []
        dims = self.env['ai.analyst.dimension'].search([('is_active', '=', True)])
        for d in dims:
            if (d.code or '').lower() == term:
                out.append(self._dimension_match(d, 0.99, 'dimension_code'))
            syns = d.synonym_ids.filtered(lambda s: s.is_active)
            for syn in syns:
                sval = (syn.synonym or '').lower()
                if sval == term or (syn.match_type == 'contains' and term in sval):
                    out.append(self._dimension_match(d, 0.95, 'dimension_synonym'))
        return out

    def _dimension_match(self, dim, confidence, source):
        path = dim.sale_line_path or dim.field_name
        return {
            'model': dim.model_name,
            'field_path': path,
            'field_type': dim.field_type or 'char',
            'confidence': confidence,
            'source': source,
        }

    def _resolve_schema(self, term, context_models=None):
        out = []
        registry = self.env['ai.analyst.schema.registry']
        model_names = context_models or registry.DEFAULT_WHITELIST
        for model_name in model_names:
            for f in registry.get_schema(model_name):
                label = (f.get('string') or '').lower()
                name = (f.get('name') or '').lower()
                score = 0.0
                if term in name:
                    score = max(score, 0.75)
                if term in label:
                    score = max(score, 0.8)
                score = max(score, SequenceMatcher(None, term, label).ratio() * 0.7)
                if score >= 0.55:
                    out.append({
                        'model': model_name,
                        'field_path': f['name'],
                        'field_type': f.get('type') or 'char',
                        'confidence': round(score, 4),
                        'source': 'schema_fuzzy',
                    })
        return out
