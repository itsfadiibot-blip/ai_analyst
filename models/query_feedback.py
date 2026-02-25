# -*- coding: utf-8 -*-
from odoo import fields, models


class AiAnalystQueryFeedback(models.Model):
    _name = 'ai.analyst.query.feedback'
    _description = 'AI Analyst Query Feedback'
    _order = 'create_date desc'

    message_id = fields.Many2one('ai.analyst.message', required=True, ondelete='cascade')
    user_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user)
    rating = fields.Selection([('up', 'Thumbs Up'), ('down', 'Thumbs Down')], required=True)
    notes = fields.Text()
    plan_json = fields.Text()
    escalation_context = fields.Text()
