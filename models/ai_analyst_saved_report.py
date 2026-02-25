# -*- coding: utf-8 -*-
import json
import logging
from odoo import models, fields, api
from odoo.exceptions import ValidationError

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
    pinned_widget_id = fields.Many2one(
        'ai.analyst.dashboard.widget',
        string='Pinned Widget',
        ondelete='set null',
        copy=False,
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

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.is_pinned:
                rec._ensure_pinned_widget()
        return records

    def write(self, vals):
        pin_before = {rec.id: bool(rec.is_pinned) for rec in self}
        res = super().write(vals)
        if 'is_pinned' in vals:
            for rec in self:
                before = pin_before.get(rec.id, False)
                after = bool(rec.is_pinned)
                if not before and after:
                    rec._ensure_pinned_widget()
                elif before and not after:
                    rec._remove_pinned_widget()
        return res

    def _ensure_pinned_widget(self):
        self.ensure_one()
        if self.pinned_widget_id and self.pinned_widget_id.exists():
            if not self.pinned_widget_id.active:
                self.pinned_widget_id.write({'active': True})
            return self.pinned_widget_id

        if not self.tool_name:
            raise ValidationError('This report cannot be pinned dynamically because no tool metadata is available.')

        user = self.user_id or self.env.user
        dashboard = self.env['ai.analyst.dashboard'].with_user(user.id).get_or_create_default(user)
        refresh_default = int(self.env['ir.config_parameter'].sudo().get_param(
            'ai_analyst.dashboard_default_refresh_seconds', '300'
        ) or 300)

        existing = self.env['ai.analyst.dashboard.widget'].with_user(user.id).search([
            ('dashboard_id', '=', dashboard.id),
            ('user_id', '=', user.id),
            ('tool_name', '=', self.tool_name),
            ('tool_args_json', '=', self.tool_args_json or '{}'),
            ('title', '=', self.name or self.user_query or 'Dashboard Widget'),
            ('active', '=', True),
        ], limit=1)

        widget = existing
        if not widget:
            widget = self.env['ai.analyst.dashboard.widget'].with_user(user.id).create({
                'dashboard_id': dashboard.id,
                'user_id': user.id,
                'company_id': user.company_id.id,
                'tool_name': self.tool_name,
                'tool_args_json': self.tool_args_json or '{}',
                'title': self.name or self.user_query or 'Dashboard Widget',
                'sequence': 10,
                'width': 6,
                'height': 4,
                'refresh_interval_seconds': max(60, refresh_default),
                'active': True,
            })
        self.with_user(user.id).write({'pinned_widget_id': widget.id})
        return widget

    def _remove_pinned_widget(self):
        self.ensure_one()
        widget = self.pinned_widget_id
        if widget and widget.exists():
            widget.with_user(self.user_id or self.env.user).unlink()
        self.write({'pinned_widget_id': False})

