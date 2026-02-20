# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ai_analyst_max_tool_calls = fields.Integer(
        string='Max Tool Calls Per Request',
        config_parameter='ai_analyst.max_tool_calls',
        default=8,
    )
    ai_analyst_max_history_messages = fields.Integer(
        string='Max Conversation History Messages',
        config_parameter='ai_analyst.max_history_messages',
        default=20,
    )
    ai_analyst_rate_limit_per_minute = fields.Integer(
        string='Rate Limit (requests/min/user)',
        config_parameter='ai_analyst.rate_limit_per_minute',
        default=20,
    )
    ai_analyst_max_input_chars = fields.Integer(
        string='Max Input Characters',
        config_parameter='ai_analyst.max_input_chars',
        default=8000,
    )
    ai_analyst_log_retention_days = fields.Integer(
        string='Audit Log Retention (days)',
        config_parameter='ai_analyst.log_retention_days',
        default=90,
    )
    ai_analyst_default_provider_id = fields.Many2one(
        'ai.analyst.provider.config',
        string='Default AI Provider',
        compute='_compute_default_provider',
        inverse='_inverse_default_provider',
    )

    def _compute_default_provider(self):
        for rec in self:
            rec.ai_analyst_default_provider_id = self.env[
                'ai.analyst.provider.config'
            ].get_default_provider(company_id=self.env.company.id)

    def _inverse_default_provider(self):
        for rec in self:
            if rec.ai_analyst_default_provider_id:
                # Unset previous default
                self.env['ai.analyst.provider.config'].search([
                    ('is_default', '=', True),
                    ('company_id', '=', self.env.company.id),
                ]).write({'is_default': False})
                # Set new default
                rec.ai_analyst_default_provider_id.write({'is_default': True})
