# -*- coding: utf-8 -*-
import logging
from odoo import models, fields

_logger = logging.getLogger(__name__)


class AiAnalystAuditLog(models.Model):
    _name = 'ai.analyst.audit.log'
    _description = 'AI Analyst Audit Log'
    _order = 'create_date desc'

    user_id = fields.Many2one(
        'res.users',
        string='User',
        required=True,
        index=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        index=True,
    )
    conversation_id = fields.Many2one(
        'ai.analyst.conversation',
        string='Conversation',
        index=True,
        ondelete='set null',
    )
    event_type = fields.Selection([
        ('query', 'User Query'),
        ('response', 'AI Response'),
        ('tool_call', 'Tool Call'),
        ('provider_call', 'Provider API Call'),
        ('error', 'Error'),
        ('rate_limit', 'Rate Limit Hit'),
        ('access_denied', 'Access Denied'),
    ], string='Event Type', required=True, index=True)

    summary = fields.Text(
        string='Summary',
        help='Human-readable summary of the event',
    )
    detail_json = fields.Text(
        string='Detail (JSON)',
        help='Structured details of the event',
    )
    provider = fields.Char(string='Provider')
    model_name = fields.Char(string='Model')
    tokens_input = fields.Integer(string='Input Tokens', default=0)
    tokens_output = fields.Integer(string='Output Tokens', default=0)
    latency_ms = fields.Integer(string='Latency (ms)', default=0)
    status_code = fields.Integer(string='HTTP Status Code')
    error_message = fields.Text(string='Error Message')
    ip_address = fields.Char(string='IP Address')
