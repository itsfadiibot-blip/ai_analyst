# -*- coding: utf-8 -*-
import json
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class AiAnalystSavedReport(models.Model):
    _name = 'ai.analyst.saved.report'
    _description = 'AI Analyst Saved Report'
    _order = 'write_date desc'

    name = fields.Char(
        string='Report Name',
        required=True,
    )
    conversation_id = fields.Many2one(
        'ai.analyst.conversation',
        string='Source Conversation',
        ondelete='set null',
    )
    message_id = fields.Many2one(
        'ai.analyst.message',
        string='Source Message',
        ondelete='set null',
    )
    user_query = fields.Text(
        string='Original Query',
        help='The user question that generated this report',
    )
    structured_response = fields.Text(
        string='Response Data (JSON)',
        help='Snapshot of the structured JSON response at save time',
    )
    tool_name = fields.Char(
        string='Tool Name',
        help='Original tool used to generate this report',
    )
    tool_args_json = fields.Text(
        string='Tool Args JSON',
        help='Serialized tool parameters used for dynamic dashboard execution',
    )
    user_id = fields.Many2one(
        'res.users',
        string='Saved By',
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
    is_pinned = fields.Boolean(
        string='Pinned to Dashboard',
        default=False,
        help='Show this report as a widget on the AI Analyst dashboard',
    )

    def get_response_dict(self):
        """Parse structured_response JSON into dict."""
        self.ensure_one()
        if not self.structured_response:
            return {}
        try:
            return json.loads(self.structured_response)
        except (json.JSONDecodeError, TypeError):
            return {}
