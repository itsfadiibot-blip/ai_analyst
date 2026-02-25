# -*- coding: utf-8 -*-
import logging
import os
from odoo import models, fields, api
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class AiAnalystProviderConfig(models.Model):
    _name = 'ai.analyst.provider.config'
    _description = 'AI Analyst Provider Configuration'
    _order = 'sequence, name'

    name = fields.Char(
        string='Name',
        required=True,
        help='Human-readable name, e.g. "Claude Sonnet (Production)"',
    )
    sequence = fields.Integer(string='Sequence', default=10)

    provider_type = fields.Selection([
        ('anthropic', 'Anthropic (Claude)'),
        ('openai', 'OpenAI (GPT)'),
        ('azure_openai', 'Azure OpenAI'),
        ('bedrock', 'AWS Bedrock'),
        ('local', 'Local (Ollama / vLLM)'),
    ], string='Provider Type', required=True, default='anthropic')

    model_name = fields.Char(
        string='Model Name',
        required=True,
        default='claude-sonnet-4-6-latest',
        help='Model identifier, e.g. claude-sonnet-4-6-latest, gpt-4o, etc.',
    )

    # --- API Configuration ---
    api_key_param = fields.Char(
        string='API Key Parameter',
        help='Name of ir.config_parameter or environment variable holding the API key. '
             'Prefix with "env:" to read from environment variable, e.g. "env:ANTHROPIC_API_KEY". '
             'Otherwise reads from ir.config_parameter with this key name.',
    )
    api_base_url = fields.Char(
        string='API Base URL',
        help='Override the default API endpoint (for Azure, local, or proxy setups)',
    )

    # --- Model Parameters ---
    temperature = fields.Float(
        string='Temperature',
        default=0.1,
        help='Controls randomness. Lower = more deterministic. Range: 0.0 - 1.0',
    )
    max_tokens = fields.Integer(
        string='Max Output Tokens',
        default=4096,
        help='Maximum number of tokens in the AI response',
    )
    timeout_seconds = fields.Integer(
        string='Timeout (seconds)',
        default=60,
        help='Maximum wait time for provider API response',
    )
    max_retries = fields.Integer(
        string='Max Retries',
        default=2,
        help='Number of retry attempts on transient errors',
    )

    # --- Status ---
    is_active = fields.Boolean(
        string='Active',
        default=True,
    )
    is_default = fields.Boolean(
        string='Default Provider',
        default=False,
        help='Use this provider by default for the company',
    )

    # --- Company ---
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
    )

    # --- Fallback ---
    fallback_provider_id = fields.Many2one(
        'ai.analyst.provider.config',
        string='Fallback Provider',
        help='If this provider fails after retries, try this one',
        domain="[('id', '!=', id), ('is_active', '=', True)]",
    )

    @api.constrains('is_default', 'company_id')
    def _check_single_default(self):
        """Ensure only one default provider per company."""
        for rec in self:
            if rec.is_default:
                existing = self.search([
                    ('is_default', '=', True),
                    ('company_id', '=', rec.company_id.id),
                    ('id', '!=', rec.id),
                ])
                if existing:
                    raise ValidationError(
                        f'Only one default provider per company is allowed. '
                        f'"{existing[0].name}" is already the default.'
                    )

    @api.constrains('temperature')
    def _check_temperature(self):
        for rec in self:
            if rec.temperature < 0.0 or rec.temperature > 1.0:
                raise ValidationError('Temperature must be between 0.0 and 1.0')

    def get_api_key(self):
        """Resolve the API key from config parameter or environment variable.

        Returns:
            str: The API key value.

        Raises:
            ValidationError: If the API key is not configured.
        """
        self.ensure_one()
        if not self.api_key_param:
            raise ValidationError(
                f'API key parameter not configured for provider "{self.name}"'
            )

        key_ref = self.api_key_param.strip()

        # Environment variable
        if key_ref.startswith('env:'):
            env_var = key_ref[4:].strip()
            value = os.environ.get(env_var)
            if not value:
                raise ValidationError(
                    f'Environment variable "{env_var}" is not set or empty'
                )
            return value

        # Odoo system parameter
        value = self.env['ir.config_parameter'].sudo().get_param(key_ref)
        if not value:
            raise ValidationError(
                f'System parameter "{key_ref}" is not set or empty'
            )
        return value

    @api.model
    def get_default_provider(self, company_id=None):
        """Get the default active provider for the given company.

        Args:
            company_id: Optional company ID. Defaults to current company.

        Returns:
            ai.analyst.provider.config record or empty recordset.
        """
        if company_id is None:
            company_id = self.env.company.id

        provider = self.search([
            ('is_default', '=', True),
            ('is_active', '=', True),
            ('company_id', '=', company_id),
        ], limit=1)

        if not provider:
            # Fall back to any active provider for the company
            provider = self.search([
                ('is_active', '=', True),
                ('company_id', '=', company_id),
            ], limit=1, order='sequence')

        return provider
