# -*- coding: utf-8 -*-
from odoo import api, models


class AiAnalystQueryPlanValidator(models.AbstractModel):
    _name = 'ai.analyst.query.plan.validator'
    _description = 'AI Analyst Query Plan Validator'

    ALLOWED_OPS = {'=', '!=', '<', '>', '<=', '>=', 'in', 'not in', 'ilike', 'like', '=like', '=ilike', 'child_of', 'parent_of'}

    @api.model
    def validate(self, user, plan):
        errors = []
        warnings = []
        plan = plan or {}
        for step in plan.get('steps', []):
            model_name = step.get('model')
            if model_name not in self.env:
                errors.append('Unknown model: %s' % model_name)
                continue
            model = self.env[model_name].with_user(user)
            if not model.check_access_rights('read', raise_exception=False):
                errors.append('No read access to model: %s' % model_name)
                continue

            for cond in step.get('domain', []):
                if not isinstance(cond, (list, tuple)) or len(cond) < 3:
                    continue
                op = cond[1]
                if op not in self.ALLOWED_OPS:
                    errors.append('Invalid domain operator: %s' % op)
                if not self._field_exists(model, cond[0]):
                    errors.append('Unknown field path: %s' % cond[0])

            for field in step.get('fields', []):
                if not self._field_exists(model, field):
                    errors.append('Unknown field: %s on %s' % (field, model_name))

            for gb in step.get('group_by', []):
                if not self._field_exists(model, gb):
                    errors.append('Unknown group_by field: %s on %s' % (gb, model_name))

            try:
                est = model.search_count(step.get('domain', []))
                if est > 200000:
                    errors.append('Estimated row count too high (%s) for %s' % (est, model_name))
                elif est > 50000:
                    warnings.append('Large dataset (%s rows) on %s' % (est, model_name))
            except Exception as exc:
                warnings.append('Row count estimation failed on %s: %s' % (model_name, exc))

            if 'company_id' in model._fields and not self._has_company_filter(step.get('domain', [])):
                warnings.append('Missing company_id filter on %s' % model_name)

        return {'valid': not errors, 'errors': errors, 'warnings': warnings}

    def _has_company_filter(self, domain):
        for cond in domain or []:
            if isinstance(cond, (list, tuple)) and len(cond) >= 1 and cond[0] == 'company_id':
                return True
        return False

    def _field_exists(self, model, field_path):
        current_model = model
        parts = (field_path or '').split('.')
        for idx, part in enumerate(parts):
            field = current_model._fields.get(part)
            if not field:
                return False
            if idx < len(parts) - 1:
                if field.type != 'many2one':
                    return False
                current_model = self.env[field.comodel_name]
        return True
