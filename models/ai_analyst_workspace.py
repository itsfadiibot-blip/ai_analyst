# -*- coding: utf-8 -*-
"""
AI Analyst Workspaces
======================
Workspaces scope the AI experience per team: which tools are available,
which prompts are suggested, and what system-prompt context is injected.
The underlying engine (gateway, providers, tool registry) is shared.
"""
import logging

from odoo import models, fields, api
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class AiAnalystWorkspace(models.Model):
    _name = 'ai.analyst.workspace'
    _description = 'AI Analyst Workspace'
    _order = 'sequence, name'

    name = fields.Char(string='Name', required=True)
    code = fields.Char(
        string='Code', required=True, copy=False,
        help='Unique short code, e.g. "sales", "buying", "pos", "cs"',
    )
    description = fields.Text(
        string='Description',
        help='Workspace purpose — shown to admins only.',
    )
    icon = fields.Char(
        string='Icon',
        default='fa-briefcase',
        help='Font Awesome icon class for the UI.',
    )
    color = fields.Integer(string='Color Index', default=0)
    sequence = fields.Integer(string='Sequence', default=10)
    is_active = fields.Boolean(string='Active', default=True)
    is_all_tools = fields.Boolean(
        string='All Tools Workspace',
        default=False,
        help='When enabled, this workspace is always admin-only regardless of group configuration.',
    )
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company,
        index=True,
    )

    # ------------------------------------------------------------------
    # Access — which Odoo groups can access this workspace
    # ------------------------------------------------------------------
    required_group_ids = fields.Many2many(
        'res.groups', 'ai_workspace_required_group_rel',
        'workspace_id', 'group_id',
        string='Required Groups',
        help='User must have ANY one of these groups to access this workspace. '
             'If empty, only AI Analyst admins can access (default deny).',
    )

    # ------------------------------------------------------------------
    # Tool scoping — which tools are available in this workspace
    # ------------------------------------------------------------------
    tool_ref_ids = fields.One2many(
        'ai.analyst.workspace.tool.ref', 'workspace_id',
        string='Tool Allowlist',
    )

    # ------------------------------------------------------------------
    # Prompt packs — suggested prompts shown in the welcome screen
    # ------------------------------------------------------------------
    prompt_pack_ids = fields.One2many(
        'ai.analyst.workspace.prompt.pack', 'workspace_id',
        string='Suggested Prompts',
    )

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------
    default_dashboard_id = fields.Many2one(
        'ai.analyst.dashboard',
        string='Default Dashboard',
        ondelete='set null',
    )

    # ------------------------------------------------------------------
    # System prompt context injected after the base system prompt
    # ------------------------------------------------------------------
    system_prompt_extra = fields.Text(
        string='System Prompt Context',
        help='Injected into the AI system prompt when this workspace is active. '
             'Use this to give the AI domain knowledge, focus areas, '
             'and constraints specific to this team.',
    )

    # ------------------------------------------------------------------
    # Query budget overrides
    # ------------------------------------------------------------------
    max_tool_calls = fields.Integer(
        string='Max Tool Calls',
        default=0,
        help='Override max tool calls per query for this workspace. 0 = use global default.',
    )
    max_inline_rows = fields.Integer(
        string='Max Inline Rows',
        default=0,
        help='Override max inline preview rows. 0 = use global default.',
    )

    # ------------------------------------------------------------------
    # Computed / helpers
    # ------------------------------------------------------------------
    tool_count = fields.Integer(
        string='Tool Count',
        compute='_compute_tool_count',
    )
    prompt_count = fields.Integer(
        string='Prompt Count',
        compute='_compute_prompt_count',
    )
    conversation_count = fields.Integer(
        string='Conversations',
        compute='_compute_conversation_count',
    )

    _sql_constraints = [
        ('code_company_unique', 'unique(code, company_id)',
         'Workspace code must be unique per company.'),
    ]

    @api.depends('tool_ref_ids')
    def _compute_tool_count(self):
        for rec in self:
            rec.tool_count = len(rec.tool_ref_ids.filtered('is_active'))

    @api.depends('prompt_pack_ids')
    def _compute_prompt_count(self):
        for rec in self:
            rec.prompt_count = len(rec.prompt_pack_ids.filtered('is_active'))

    def _compute_conversation_count(self):
        for rec in self:
            rec.conversation_count = self.env['ai.analyst.conversation'].search_count([
                ('workspace_id', '=', rec.id),
            ])

    @api.constrains('code')
    def _check_code_format(self):
        import re
        for rec in self:
            if rec.code and not re.match(r'^[a-z][a-z0-9_]*$', rec.code):
                raise ValidationError(
                    'Workspace code must start with a lowercase letter and '
                    'contain only lowercase letters, digits, and underscores.'
                )

    def user_has_access(self, user=None):
        """Check if the given user can access this workspace.

        Policy:
        - AI Analyst admins can access all workspaces.
        - "All Tools" workspace is always admin-only.
        - Non-admin users need group_ai_user and ANY required_group_ids.
        - If required_group_ids is empty, deny for non-admin users.
        """
        self.ensure_one()
        user = user or self.env.user

        is_admin = user.has_group('ai_analyst.group_ai_admin')
        if is_admin:
            return True

        if self.is_all_tools:
            return False

        if not user.has_group('ai_analyst.group_ai_user'):
            return False

        if not self.required_group_ids:
            return False

        user_group_ids = set(user.groups_id.ids)
        required_group_ids = set(self.required_group_ids.ids)
        return bool(user_group_ids.intersection(required_group_ids))

    @api.model
    def get_access_domain_for_user(self, user=None):
        """Domain for workspaces accessible to a given user.

        This domain is used by controllers and can be reused by other callers.
        """
        user = user or self.env.user
        if user.has_group('ai_analyst.group_ai_admin'):
            return []
        return [
            ('is_all_tools', '=', False),
            ('required_group_ids', 'in', user.groups_id.ids),
        ]

    @api.model
    def get_accessible_workspaces(self, user=None, include_inactive=False):
        """Return accessible workspace records for the given user."""
        user = user or self.env.user
        domain = []
        if not include_inactive:
            domain.append(('is_active', '=', True))
        domain += [
            '|',
            ('company_id', '=', False),
            ('company_id', '=', user.company_id.id),
        ]
        domain += self.get_access_domain_for_user(user)
        return self.search(domain, order='sequence, name')

    def get_allowed_tool_names(self):
        """Return the set of tool names allowed in this workspace.

        Returns an empty set if no restrictions (all tools allowed).
        """
        self.ensure_one()
        active_refs = self.tool_ref_ids.filtered('is_active')
        if not active_refs:
            return set()  # empty = no restriction
        return set(active_refs.mapped('tool_name'))

    def get_prompt_packs(self):
        """Return active prompt packs grouped by category."""
        self.ensure_one()
        prompts = self.prompt_pack_ids.filtered('is_active').sorted('sequence')
        result = {}
        for prompt in prompts:
            category = prompt.category or 'General'
            result.setdefault(category, []).append({
                'text': prompt.prompt_text,
                'description': prompt.description or '',
                'icon': prompt.icon or '',
            })
        return result


class AiAnalystWorkspaceToolRef(models.Model):
    _name = 'ai.analyst.workspace.tool.ref'
    _description = 'Workspace Tool Reference'
    _order = 'sequence, tool_name'

    workspace_id = fields.Many2one(
        'ai.analyst.workspace', string='Workspace',
        required=True, ondelete='cascade', index=True,
    )
    tool_name = fields.Char(
        string='Tool Name', required=True,
        help='Must match a registered tool name in the tool registry.',
    )
    is_active = fields.Boolean(string='Active', default=True)
    sequence = fields.Integer(string='Sequence', default=10)

    _sql_constraints = [
        ('workspace_tool_unique', 'unique(workspace_id, tool_name)',
         'Each tool can only appear once per workspace.'),
    ]

    @api.constrains('tool_name')
    def _check_tool_exists(self):
        from odoo.addons.ai_analyst.tools.registry import get_tool
        for rec in self:
            if rec.tool_name and not get_tool(rec.tool_name):
                _logger.warning(
                    'Tool "%s" referenced in workspace "%s" is not registered. '
                    'It may be added later or the name may be incorrect.',
                    rec.tool_name, rec.workspace_id.name,
                )


class AiAnalystWorkspacePromptPack(models.Model):
    _name = 'ai.analyst.workspace.prompt.pack'
    _description = 'Workspace Suggested Prompt'
    _order = 'sequence, id'

    workspace_id = fields.Many2one(
        'ai.analyst.workspace', string='Workspace',
        required=True, ondelete='cascade', index=True,
    )
    category = fields.Char(
        string='Category',
        default='General',
        help='Group label for the prompt, e.g. "Quick Stats", "Deep Dive".',
    )
    prompt_text = fields.Text(
        string='Prompt Text', required=True,
        help='The suggested prompt shown to the user.',
    )
    description = fields.Char(
        string='Short Label',
        help='Short label shown on the prompt chip in the UI.',
    )
    icon = fields.Char(string='Icon', help='Optional Font Awesome icon class.')
    sequence = fields.Integer(string='Sequence', default=10)
    is_active = fields.Boolean(string='Active', default=True)
