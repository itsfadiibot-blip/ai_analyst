# -*- coding: utf-8 -*-
import hashlib
import json
import logging
import re
import time

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from odoo.addons.ai_analyst.tools.field_kb_cache import _FIELD_KB_CACHE, invalidate_field_kb_cache, is_field_kb_cache_expired

_logger = logging.getLogger(__name__)

STOPWORDS = {'is', 'has', 'the', 'a', 'an', 'of', 'for', 'in', 'on', 'to', 'by', 'with', 'and', 'or'}
SENSITIVE_PATTERNS = [
    'password', 'passwd', 'token', 'secret', 'api_key', 'apikey', 'private_key',
    'credential', 'oauth', 'access_token', 'refresh_token', 'encryption', 'pin',
    'cvv', 'ssn', 'social_security',
]


class AiAnalystFieldKbModel(models.Model):
    _name = 'ai.analyst.field.kb.model'
    _description = 'AI Analyst Field KB Model'
    _order = 'name'

    name = fields.Char(required=True, index=True)
    model_description = fields.Char()
    module_ids = fields.Char()
    is_transient_model = fields.Boolean(default=False, string='Is Transient')
    is_abstract_model = fields.Boolean(default=False, string='Is Abstract')
    company_dependent = fields.Boolean(default=False)
    record_count_approx = fields.Integer(default=0)
    semantic_tags = fields.Char()
    admin_notes = fields.Text()
    synonyms = fields.Char()
    is_queryable = fields.Boolean(default=True)
    signature = fields.Char(index=True)
    last_refreshed_at = fields.Datetime()
    company_id = fields.Many2one('res.company', default=lambda s: s.env.company)
    field_ids = fields.One2many('ai.analyst.field.kb.field', 'kb_model_id', string='Fields')
    field_count = fields.Integer(compute='_compute_field_count')

    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Model name must be unique in Field KB.'),
    ]

    def _compute_field_count(self):
        for rec in self:
            rec.field_count = len(rec.field_ids)

    def action_rebuild_kb(self):
        self.env['ai.analyst.field.kb.service'].sudo().rebuild_kb(model_names=self.mapped('name') or None, full=not bool(self))
        return True

    @api.model
    def cron_refresh_kb(self):
        return self.env['ai.analyst.field.kb.service'].sudo().cron_refresh_kb()


class AiAnalystFieldKbField(models.Model):
    _name = 'ai.analyst.field.kb.field'
    _description = 'AI Analyst Field KB Field'
    _order = 'kb_model_id, name'

    kb_model_id = fields.Many2one('ai.analyst.field.kb.model', required=True, ondelete='cascade', index=True)
    name = fields.Char(required=True, index=True)
    field_label = fields.Char()
    ttype = fields.Selection([
        ('boolean', 'Boolean'), ('char', 'Char'), ('integer', 'Integer'), ('float', 'Float'), ('monetary', 'Monetary'),
        ('date', 'Date'), ('datetime', 'Datetime'), ('many2one', 'Many2one'), ('one2many', 'One2many'), ('many2many', 'Many2many'),
        ('selection', 'Selection'), ('text', 'Text'), ('html', 'Html'), ('binary', 'Binary'), ('reference', 'Reference'),
        ('many2one_reference', 'Many2one Reference'), ('id', 'ID'), ('serialized', 'Serialized'),
        ('properties', 'Properties'), ('properties_definition', 'Properties Definition'),
        ('json', 'JSON'),
    ], required=True)
    relation = fields.Char()
    relation_field = fields.Char()
    selection_keys = fields.Text()
    store = fields.Boolean(default=False)
    index = fields.Boolean(default=False)
    required = fields.Boolean(default=False)
    readonly = fields.Boolean(default=False)
    company_dependent = fields.Boolean(default=False)
    help_text = fields.Text()
    short_description = fields.Char()
    semantic_tags = fields.Char()
    sensitivity = fields.Selection([('normal', 'Normal'), ('sensitive', 'Sensitive'), ('hidden', 'Hidden')], default='normal', required=True, index=True)
    admin_notes = fields.Text()
    is_custom = fields.Boolean(default=False)
    source_module = fields.Char()
    translated_labels = fields.Text()
    signature = fields.Char(index=True)
    last_refreshed_at = fields.Datetime()
    company_id = fields.Many2one('res.company', default=lambda s: s.env.company)
    synonym_ids = fields.One2many('ai.analyst.field.kb.synonym', 'kb_field_id', string='Synonyms')
    synonym_count = fields.Integer(compute='_compute_synonym_count')

    _sql_constraints = [
        ('kb_model_field_unique', 'unique(kb_model_id, name)', 'Field name must be unique per KB model.'),
    ]

    def _compute_synonym_count(self):
        for rec in self:
            rec.synonym_count = len(rec.synonym_ids)

    def write(self, vals):
        res = super().write(vals)
        if 'sensitivity' in vals and vals['sensitivity'] in ('sensitive', 'hidden'):
            self.mapped('synonym_ids').unlink()
            invalidate_field_kb_cache()
        return res


class AiAnalystFieldKbSynonym(models.Model):
    _name = 'ai.analyst.field.kb.synonym'
    _description = 'AI Analyst Field KB Synonym'
    _order = 'term'

    kb_field_id = fields.Many2one('ai.analyst.field.kb.field', required=True, ondelete='cascade', index=True)
    term = fields.Char(required=True, index=True)
    source = fields.Selection([('auto', 'Auto'), ('llm', 'LLM'), ('admin', 'Admin')], required=True, default='auto')
    confidence = fields.Float(default=1.0)
    company_id = fields.Many2one('res.company', default=lambda s: s.env.company)

    _sql_constraints = [
        ('kb_field_term_unique', 'unique(kb_field_id, term)', 'Synonym already exists for this field.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['term'] = (vals.get('term') or '').strip().lower()
            if vals.get('source') == 'admin' and not vals.get('confidence'):
                vals['confidence'] = 1.0
        recs = super().create(vals_list)
        invalidate_field_kb_cache()
        return recs

    def write(self, vals):
        if 'term' in vals:
            vals['term'] = (vals.get('term') or '').strip().lower()
        res = super().write(vals)
        invalidate_field_kb_cache()
        return res

    def unlink(self):
        res = super().unlink()
        invalidate_field_kb_cache()
        return res


class AiAnalystFieldKbUnmappedLog(models.Model):
    _name = 'ai.analyst.field.kb.unmapped.log'
    _description = 'AI Analyst Field KB Unmapped Term Log'
    _order = 'occurrence_count desc, last_seen_at desc'

    term = fields.Char(required=True, index=True)
    user_id = fields.Many2one('res.users')
    query_text = fields.Text()
    suggested_model = fields.Char()
    occurrence_count = fields.Integer(default=1)
    first_seen_at = fields.Datetime(required=True, default=fields.Datetime.now)
    last_seen_at = fields.Datetime(required=True, default=fields.Datetime.now)
    resolved = fields.Boolean(default=False)


class AiAnalystFieldKbService(models.AbstractModel):
    _name = 'ai.analyst.field.kb.service'
    _description = 'AI Analyst Field KB Service'

    def _excluded_patterns(self):
        raw = self.env['ir.config_parameter'].sudo().get_param('ai_analyst.field_kb_excluded_models', default='[]')
        try:
            items = json.loads(raw)
        except Exception:
            items = []
        return items or ['ir.actions.*', 'ir.ui.*', 'ir.cron', 'ir.config_parameter', 'ir.logging', 'bus.bus']

    def _model_is_excluded(self, model_name):
        for pattern in self._excluded_patterns():
            if pattern.endswith('*') and model_name.startswith(pattern[:-1]):
                return True
            if model_name == pattern:
                return True
        return False

    def _safe_count(self, model_name):
        """Safely get record count for a model, handling abstract/mixin models without tables."""
        try:
            if model_name not in self.env:
                return 0
            model = self.env[model_name]
            # Skip models without actual database tables (abstract, mixin)
            if not hasattr(model, '_auto') or not model._auto:
                return 0
            if hasattr(model, '_abstract') and model._abstract:
                return 0
            return model.sudo().search_count([])
        except Exception:
            return 0

    def _field_signature(self, f):
        selection = ''
        if getattr(f, 'selection', False):
            try:
                selection = json.dumps(list(f.selection), sort_keys=True)
            except Exception:
                selection = str(f.selection)
        payload = [f.name, f.ttype, f.relation or '', bool(f.store), bool(f.required), selection]
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode('utf-8')).hexdigest()

    def _model_signature(self, fields_rs):
        payload = []
        for f in fields_rs.sorted('name'):
            payload.append([f.name, f.ttype, f.relation or '', bool(f.store), bool(f.required), self._field_signature(f)])
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode('utf-8')).hexdigest()

    def _compute_sensitivity(self, name, ttype):
        low = (name or '').lower()
        if any(p in low for p in SENSITIVE_PATTERNS):
            return 'sensitive'
        if ttype == 'binary' and any(k in low for k in ('file', 'content', 'document', 'datas')):
            return 'hidden'
        return 'normal'

    def _generate_auto_synonyms(self, model_name, field_name, field_label, ttype, selection):
        terms = set()
        n = (field_name or '').lower()
        parts = [p for p in n.split('_') if p]
        if parts:
            terms.add(' '.join(parts))
            for p in parts:
                if len(p) > 2 and p not in STOPWORDS:
                    terms.add(p)
        if ttype == 'boolean':
            for prefix in ('is_', 'has_', 'allow_', 'can_', 'x_is_', 'x_has_'):
                if n.startswith(prefix):
                    concept = n[len(prefix):].replace('_', ' ').strip()
                    if concept:
                        terms.add(concept)
                        terms.add(concept.replace(' ', ''))
        if field_label:
            lp = re.findall(r'[a-z0-9]+', field_label.lower())
            filtered = [t for t in lp if t not in STOPWORDS and len(t) > 2]
            if filtered:
                terms.add(' '.join(filtered))
                terms.update(filtered)
        if ttype == 'selection' and selection:
            try:
                values = json.loads(selection)
            except Exception:
                values = []
            for item in values:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    terms.add(str(item[1]).strip().lower())
                    terms.add(str(item[0]).strip().lower())
        if ttype in ('many2one', 'many2many') and field_name.endswith('_id'):
            terms.add(field_name[:-3].replace('_', ' '))
        return [t.strip().lower() for t in terms if t and len(t.strip()) > 1]

    @api.model
    def rebuild_kb(self, model_names=None, full=False):
        start = time.time()
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('ai_analyst.field_kb_rebuilding', 'True')
        model_domain = []
        if model_names:
            model_domain.append(('model', 'in', list(set(model_names))))
        ir_models = self.env['ir.model'].sudo().search(model_domain)
        kb_model_obj = self.env['ai.analyst.field.kb.model'].sudo()
        kb_field_obj = self.env['ai.analyst.field.kb.field'].sudo()
        kb_syn_obj = self.env['ai.analyst.field.kb.synonym'].sudo()

        scanned_models, scanned_fields = 0, 0
        seen_models = set()

        for ir_model in ir_models:
            model_name = ir_model.model
            if not model_name or self._model_is_excluded(model_name):
                continue
            if model_name not in self.env:
                continue
            # Skip abstract/mixin models without actual database tables
            model_cls = self.env[model_name]
            if not getattr(model_cls, '_auto', True) or getattr(model_cls, '_abstract', False):
                continue
            seen_models.add(model_name)
            field_defs = self.env['ir.model.fields'].sudo().search([('model', '=', model_name)])
            model_sig = self._model_signature(field_defs)
            kb_model = kb_model_obj.search([('name', '=', model_name)], limit=1)
            vals_model = {
                'name': model_name,
                'model_description': ir_model.name,
                'module_ids': ir_model.modules,
                'is_transient_model': bool(ir_model.transient),
                'is_abstract_model': bool(getattr(ir_model, '_abstract', False)),
                'is_queryable': not self._model_is_excluded(model_name),
                'signature': model_sig,
                'last_refreshed_at': fields.Datetime.now(),
                'company_id': self.env.company.id,
                'record_count_approx': self._safe_count(model_name),
            }
            if kb_model:
                if kb_model.signature == model_sig and not full:
                    continue
                kb_model.write(vals_model)
            else:
                kb_model = kb_model_obj.create(vals_model)

            scanned_models += 1
            live_fields = set()
            for f in field_defs:
                live_fields.add(f.name)
                scanned_fields += 1
                selection = False
                if f.ttype == 'selection':
                    try:
                        selection = json.dumps(self.env[model_name]._fields[f.name].selection or [])
                    except Exception:
                        selection = '[]'
                sensitivity = self._compute_sensitivity(f.name, f.ttype)
                vals_field = {
                    'kb_model_id': kb_model.id,
                    'name': f.name,
                    'field_label': f.field_description,
                    'ttype': f.ttype,
                    'relation': f.relation,
                    'relation_field': f.relation_field,
                    'selection_keys': selection or False,
                    'store': bool(f.store),
                    'index': bool(f.index),
                    'required': bool(f.required),
                    'readonly': bool(f.readonly),
                    'company_dependent': bool(getattr(f, 'company_dependent', False)),
                    'help_text': f.help,
                    'is_custom': f.name.startswith('x_'),
                    'source_module': f.modules,
                    'signature': self._field_signature(f),
                    'last_refreshed_at': fields.Datetime.now(),
                    'sensitivity': sensitivity,
                    'company_id': self.env.company.id,
                }
                kb_field = kb_field_obj.search([('kb_model_id', '=', kb_model.id), ('name', '=', f.name)], limit=1)
                if kb_field:
                    kb_field.write(vals_field)
                else:
                    kb_field = kb_field_obj.create(vals_field)

                if sensitivity == 'normal':
                    auto_terms = self._generate_auto_synonyms(model_name, f.name, f.field_description, f.ttype, selection)
                    existing = set(kb_field.synonym_ids.filtered(lambda s: s.source in ('auto', 'admin', 'llm')).mapped('term'))
                    for term in auto_terms:
                        if term in existing:
                            continue
                        kb_syn_obj.create({
                            'kb_field_id': kb_field.id,
                            'term': term,
                            'source': 'auto',
                            'confidence': 1.0,
                            'company_id': self.env.company.id,
                        })
                else:
                    kb_field.synonym_ids.unlink()

            stale = kb_field_obj.search([('kb_model_id', '=', kb_model.id), ('name', 'not in', list(live_fields) or [''])])
            if stale:
                stale.unlink()

        if not model_names:
            stale_models = kb_model_obj.search([('name', 'not in', list(seen_models) or [''])])
            if stale_models:
                stale_models.unlink()

        ICP.set_param('ai_analyst.field_kb_last_built_at', fields.Datetime.now())
        ICP.set_param('ai_analyst.field_kb_rebuilding', 'False')
        ICP.set_param('ai_analyst.field_kb_needs_refresh', 'False')
        invalidate_field_kb_cache()

        self.env['ai.analyst.audit.log'].sudo().create({
            'user_id': self.env.user.id,
            'company_id': self.env.company.id,
            'event_type': 'response',
            'summary': 'Field KB rebuild complete',
            'error_message': json.dumps({
                'models_scanned': scanned_models,
                'fields_scanned': scanned_fields,
                'duration_ms': int((time.time() - start) * 1000),
            }),
        })
        return {'models_scanned': scanned_models, 'fields_scanned': scanned_fields}

    @api.model
    def cron_refresh_kb(self):
        return self.rebuild_kb(full=False)

    @api.model
    def ensure_cache_loaded(self):
        if not is_field_kb_cache_expired() and _FIELD_KB_CACHE.get('models'):
            return _FIELD_KB_CACHE

        ttl = int(self.env['ir.config_parameter'].sudo().get_param('ai_analyst.field_kb_cache_ttl', default='3600') or 3600)
        _FIELD_KB_CACHE['ttl_seconds'] = ttl
        model_rows = self.env['ai.analyst.field.kb.model'].sudo().search([('is_queryable', '=', True)])
        field_rows = self.env['ai.analyst.field.kb.field'].sudo().search([('kb_model_id.is_queryable', '=', True), ('sensitivity', '!=', 'hidden')])
        syn_rows = self.env['ai.analyst.field.kb.synonym'].sudo().search([('kb_field_id.sensitivity', '=', 'normal'), ('kb_field_id.kb_model_id.is_queryable', '=', True)])

        models_map, fields_map, syn_index = {}, {}, {}
        for m in model_rows:
            models_map[m.name] = {
                'model': m.name,
                'label': m.model_description,
                'queryable': m.is_queryable,
                'synonyms': [s.strip().lower() for s in (m.synonyms or '').split(',') if s.strip()],
            }
            if m.model_description:
                models_map[m.name]['synonyms'].append((m.model_description or '').lower())

        for f in field_rows:
            fields_map.setdefault(f.kb_model_id.name, {})[f.name] = {
                'field': f.name,
                'label': f.field_label,
                'ttype': f.ttype,
                'store': f.store,
                'sensitivity': f.sensitivity,
                'relation': f.relation,
                'semantic_tags': [t.strip().lower() for t in (f.semantic_tags or '').split(',') if t.strip()],
            }

        for s in syn_rows:
            term = (s.term or '').strip().lower()
            if not term:
                continue
            payload = {
                'model': s.kb_field_id.kb_model_id.name,
                'field': s.kb_field_id.name,
                'field_label': s.kb_field_id.field_label,
                'ttype': s.kb_field_id.ttype,
                'match_type': 'synonym',
                'confidence': s.confidence or 0.95,
            }
            syn_index.setdefault(term, []).append(payload)

        _FIELD_KB_CACHE['models'] = models_map
        _FIELD_KB_CACHE['fields'] = fields_map
        _FIELD_KB_CACHE['synonym_index'] = syn_index
        _FIELD_KB_CACHE['loaded_at'] = time.time()
        return _FIELD_KB_CACHE

    @api.model
    def _tokenize(self, text):
        return [t for t in re.findall(r'[a-zA-Z0-9_]+', (text or '').lower()) if len(t) > 1 and t not in STOPWORDS]

    @api.model
    def resolve_query_terms(self, user_query):
        cache = self.ensure_cache_loaded()
        tokens = self._tokenize(user_query)
        resolutions, unresolved = [], []

        for token in tokens:
            found = False
            for model_name, model_meta in cache['models'].items():
                if token == model_name or token in model_meta.get('synonyms', []):
                    resolutions.append({
                        'user_token': token,
                        'resolved_to': {
                            'model': model_name,
                            'model_label': model_meta.get('label'),
                            'match_type': 'model_synonym',
                            'confidence': 1.0,
                        }
                    })
                    found = True
                    break
            if found:
                continue

            matches = cache['synonym_index'].get(token, [])
            if matches:
                best = sorted(matches, key=lambda m: m.get('confidence', 0), reverse=True)[0]
                resolutions.append({'user_token': token, 'resolved_to': best})
                found = True
            if not found:
                unresolved.append(token)

        return resolutions, unresolved

    @api.model
    def build_field_context_text(self, user_query, max_fields=30):
        cache = self.ensure_cache_loaded()
        resolutions, unresolved = self.resolve_query_terms(user_query)
        model_name = False
        for r in resolutions:
            if r['resolved_to'].get('model') and not r['resolved_to'].get('field'):
                model_name = r['resolved_to']['model']
                break
        if not model_name:
            for r in resolutions:
                if r['resolved_to'].get('model'):
                    model_name = r['resolved_to']['model']
                    break
        if not model_name:
            model_name = 'product.template' if 'product.template' in cache['models'] else next(iter(cache['models']), False)

        context_fields = []
        if model_name and model_name in cache['fields']:
            for fname, meta in cache['fields'][model_name].items():
                if meta.get('sensitivity') != 'normal':
                    continue
                if meta.get('ttype') in ('binary', 'html'):
                    continue
                context_fields.append((fname, meta))

        context_fields = context_fields[:max_fields]
        lines = []
        if model_name:
            lines.append('FIELD CONTEXT FOR THIS QUERY:')
            lines.append('Detected target model(s): %s (%s)' % (model_name, cache['models'][model_name].get('label') or model_name))
            lines.append('Relevant fields:')
            for fname, meta in context_fields:
                lines.append('  - %s: %s, label="%s", stored=%s' % (fname, meta.get('ttype'), meta.get('label') or fname, bool(meta.get('store'))))
            lines.append('Use ONLY fields listed above in your query_plan. Do not invent field names.')

        for term in unresolved:
            self.log_unmapped_term(term, user_query, model_name)

        return {
            'prompt_block': '\n'.join(lines),
            'resolutions': resolutions,
            'unresolved_tokens': unresolved,
            'context_fields_sent': len(context_fields),
            'target_model': model_name,
        }

    @api.model
    def log_unmapped_term(self, term, query_text, suggested_model=None):
        if not term:
            return
        rec = self.env['ai.analyst.field.kb.unmapped.log'].sudo().search([('term', '=', term)], limit=1)
        if rec:
            rec.write({'occurrence_count': rec.occurrence_count + 1, 'last_seen_at': fields.Datetime.now(), 'query_text': query_text, 'suggested_model': suggested_model})
        else:
            self.env['ai.analyst.field.kb.unmapped.log'].sudo().create({
                'term': term,
                'user_id': self.env.user.id,
                'query_text': query_text,
                'suggested_model': suggested_model,
                'first_seen_at': fields.Datetime.now(),
                'last_seen_at': fields.Datetime.now(),
                'occurrence_count': 1,
            })
