# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AiAnalystDimension(models.Model):
    _name = 'ai.analyst.dimension'
    _description = 'AI Analyst Dimension'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    model_name = fields.Char(required=True, default='sale.order.line')
    field_name = fields.Char(required=True)
    is_active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
        index=True,
    )
    synonym_ids = fields.One2many(
        'ai.analyst.dimension.synonym',
        'dimension_id',
        string='Synonyms',
    )

    _sql_constraints = [
        ('ai_analyst_dimension_code_uniq', 'unique(code, company_id)', 'Dimension code must be unique per company.'),
    ]


class AiAnalystDimensionSynonym(models.Model):
    _name = 'ai.analyst.dimension.synonym'
    _description = 'AI Analyst Dimension Synonym'
    _order = 'priority, id'

    dimension_id = fields.Many2one('ai.analyst.dimension', required=True, ondelete='cascade', index=True)
    synonym = fields.Char(required=True, index=True)
    canonical_value = fields.Char(required=True, index=True)
    match_type = fields.Selection(
        [
            ('exact', 'Exact'),
            ('prefix', 'Prefix'),
            ('contains', 'Contains'),
            ('regex', 'Regex'),
        ],
        required=True,
        default='exact',
    )
    priority = fields.Integer(default=10)
    is_active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        related='dimension_id.company_id',
        store=True,
        index=True,
        readonly=True,
    )

    _sql_constraints = [
        ('ai_analyst_dimension_synonym_uniq', 'unique(dimension_id, synonym, canonical_value, match_type)', 'Duplicate synonym mapping is not allowed.'),
    ]


class AiAnalystSeasonConfig(models.Model):
    _name = 'ai.analyst.season.config'
    _description = 'AI Analyst Season Config'
    _order = 'name, id'

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    is_active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company,
        index=True,
    )
    tag_pattern_ids = fields.One2many(
        'ai.analyst.season.tag.pattern',
        'season_config_id',
        string='Tag Patterns',
    )

    _sql_constraints = [
        ('ai_analyst_season_config_code_uniq', 'unique(code, company_id)', 'Season code must be unique per company.'),
    ]

    @api.model
    def find_by_tag(self, tag_value):
        """Resolve a tag (e.g., AW25) into a configured season code."""
        value = (tag_value or '').strip()
        if not value:
            return False
        value_l = value.lower()
        seasons = self.search([
            ('is_active', '=', True),
            '|', ('company_id', '=', False), ('company_id', '=', self.env.company.id),
        ])
        for season in seasons:
            for pattern in season.tag_pattern_ids.filtered(lambda p: p.is_active).sorted('id'):
                p = (pattern.pattern or '').strip()
                if not p:
                    continue
                p_l = p.lower()
                if pattern.match_type == 'exact' and value_l == p_l:
                    return season
                if pattern.match_type == 'prefix' and value_l.startswith(p_l):
                    return season
                if pattern.match_type == 'contains' and p_l in value_l:
                    return season
                if pattern.match_type == 'regex':
                    import re
                    if re.search(p, value, flags=re.IGNORECASE):
                        return season
        return False


class AiAnalystSeasonTagPattern(models.Model):
    _name = 'ai.analyst.season.tag.pattern'
    _description = 'AI Analyst Season Tag Pattern'
    _order = 'id'

    season_config_id = fields.Many2one('ai.analyst.season.config', required=True, ondelete='cascade', index=True)
    pattern = fields.Char(required=True, index=True)
    match_type = fields.Selection(
        [
            ('exact', 'Exact'),
            ('prefix', 'Prefix'),
            ('contains', 'Contains'),
            ('regex', 'Regex'),
        ],
        required=True,
        default='exact',
    )
    is_active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        related='season_config_id.company_id',
        store=True,
        index=True,
        readonly=True,
    )
