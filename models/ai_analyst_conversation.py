# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class AiAnalystConversation(models.Model):
    _name = 'ai.analyst.conversation'
    _description = 'AI Analyst Conversation'
    _order = 'write_date desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Title',
        compute='_compute_name',
        store=True,
        readonly=False,
    )
    user_id = fields.Many2one(
        'res.users',
        string='User',
        required=True,
        default=lambda self: self.env.user,
        index=True,
        ondelete='cascade',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    workspace_id = fields.Many2one(
        'ai.analyst.workspace',
        string='Workspace',
        index=True,
        ondelete='set null',
        help='The workspace context for this conversation.',
    )
    message_ids = fields.One2many(
        'ai.analyst.message',
        'conversation_id',
        string='Messages',
    )
    message_count = fields.Integer(
        string='Message Count',
        compute='_compute_message_count',
        store=True,
    )
    state = fields.Selection([
        ('active', 'Active'),
        ('archived', 'Archived'),
    ], string='State', default='active', required=True, index=True)

    @api.depends('message_ids')
    def _compute_name(self):
        for rec in self:
            if not rec.name and rec.message_ids:
                first_user_msg = rec.message_ids.filtered(
                    lambda m: m.role == 'user'
                )[:1]
                if first_user_msg:
                    text = first_user_msg.content or ''
                    rec.name = text[:80] + ('...' if len(text) > 80 else '')
                else:
                    rec.name = f'Conversation #{rec.id}'
            elif not rec.name:
                rec.name = 'New Conversation'

    @api.depends('message_ids')
    def _compute_message_count(self):
        for rec in self:
            rec.message_count = len(rec.message_ids)

    def action_archive(self):
        self.write({'state': 'archived'})

    def action_unarchive(self):
        self.write({'state': 'active'})

    def get_history_for_ai(self, max_messages=20):
        """Return conversation history formatted for the AI provider.

        Returns list of dicts with 'role' and 'content' keys.
        Limits to the most recent max_messages messages.
        """
        self.ensure_one()
        messages = self.message_ids.sorted('create_date')[-max_messages:]
        history = []
        for msg in messages:
            if msg.role in ('user', 'assistant'):
                history.append({
                    'role': msg.role,
                    'content': msg.content or '',
                })
        return history
