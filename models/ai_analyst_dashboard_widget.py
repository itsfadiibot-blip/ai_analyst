# -*- coding: utf-8 -*-
import logging
from odoo import models, fields

_logger = logging.getLogger(__name__)


class AiAnalystDashboardWidget(models.Model):
    _name = 'ai.analyst.dashboard.widget'
    _description = 'AI Analyst Dashboard Widget'
    _order = 'sequence, create_date desc'

    name = fields.Char(string='Widget Title', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    saved_report_id = fields.Many2one(
        'ai.analyst.saved.report',
        string='Saved Report',
        required=True,
        ondelete='cascade',
    )
    widget_type = fields.Selection([
        ('kpi', 'KPI Cards'),
        ('table', 'Data Table'),
        ('chart', 'Chart'),
        ('full', 'Full Report'),
    ], string='Widget Type', default='full', required=True)
    size = fields.Selection([
        ('small', 'Small (1/3 width)'),
        ('medium', 'Medium (1/2 width)'),
        ('large', 'Large (Full width)'),
    ], string='Size', default='medium')
    user_id = fields.Many2one(
        'res.users',
        string='Owner',
        required=True,
        default=lambda self: self.env.user,
        index=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    auto_refresh = fields.Boolean(
        string='Auto Refresh',
        default=False,
        help='Re-run the original query periodically to keep data fresh (Phase 2)',
    )
