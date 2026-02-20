# -*- coding: utf-8 -*-
import json
import logging
from odoo import models, fields

_logger = logging.getLogger(__name__)


class AiAnalystToolCallLog(models.Model):
    _name = 'ai.analyst.tool.call.log'
    _description = 'AI Analyst Tool Call Log'
    _order = 'create_date desc'

    message_id = fields.Many2one(
        'ai.analyst.message',
        string='Message',
        required=True,
        ondelete='cascade',
        index=True,
    )
    conversation_id = fields.Many2one(
        related='message_id.conversation_id',
        store=True,
        index=True,
    )
    tool_name = fields.Char(
        string='Tool Name',
        required=True,
        index=True,
    )
    parameters_json = fields.Text(
        string='Parameters (JSON)',
        help='The parameters passed to the tool',
    )
    result_summary = fields.Text(
        string='Result Summary',
        help='Truncated result for audit purposes (max 2000 chars)',
    )
    execution_time_ms = fields.Integer(
        string='Execution Time (ms)',
        default=0,
    )
    success = fields.Boolean(
        string='Success',
        default=True,
    )
    error_message = fields.Text(
        string='Error Message',
    )
    user_id = fields.Many2one(
        related='message_id.user_id',
        store=True,
        index=True,
    )
    company_id = fields.Many2one(
        related='message_id.company_id',
        store=True,
        index=True,
    )
    row_count = fields.Integer(
        string='Rows Returned',
        default=0,
    )

    def get_parameters_dict(self):
        """Parse parameters_json into a dict."""
        self.ensure_one()
        if not self.parameters_json:
            return {}
        try:
            return json.loads(self.parameters_json)
        except (json.JSONDecodeError, TypeError):
            return {}
