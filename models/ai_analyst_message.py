# -*- coding: utf-8 -*-
import json
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class AiAnalystMessage(models.Model):
    _name = 'ai.analyst.message'
    _description = 'AI Analyst Message'
    _order = 'create_date asc'

    conversation_id = fields.Many2one(
        'ai.analyst.conversation',
        string='Conversation',
        required=True,
        ondelete='cascade',
        index=True,
    )
    role = fields.Selection([
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    ], string='Role', required=True, index=True)

    content = fields.Text(
        string='Content',
        help='The text content of the message (user question or AI answer text)',
    )
    structured_response = fields.Text(
        string='Structured Response (JSON)',
        help='Full structured JSON response for assistant messages',
    )

    # --- Audit / metadata fields ---
    tool_call_ids = fields.One2many(
        'ai.analyst.tool.call.log',
        'message_id',
        string='Tool Calls',
    )
    tokens_input = fields.Integer(string='Input Tokens', default=0)
    tokens_output = fields.Integer(string='Output Tokens', default=0)
    provider_model = fields.Char(string='Provider / Model')
    processing_time_ms = fields.Integer(string='Processing Time (ms)', default=0)

    # --- Relations ---
    user_id = fields.Many2one(
        related='conversation_id.user_id',
        store=True,
        index=True,
    )
    company_id = fields.Many2one(
        related='conversation_id.company_id',
        store=True,
        index=True,
    )

    def get_structured_response_dict(self):
        """Parse and return the structured_response as a Python dict."""
        self.ensure_one()
        if not self.structured_response:
            return {}
        try:
            return json.loads(self.structured_response)
        except (json.JSONDecodeError, TypeError):
            _logger.warning(
                'Invalid JSON in structured_response for message %s', self.id
            )
            return {}
