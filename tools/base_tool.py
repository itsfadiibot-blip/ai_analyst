# -*- coding: utf-8 -*-
"""
Base Tool — Abstract base class for all AI Analyst tools.
============================================================
Every tool must:
- Be read-only
- Validate parameters against a JSON schema
- Check user access (Odoo groups)
- Execute using with_user() context (never sudo)
- Return structured data
"""
import logging
from abc import ABC, abstractmethod
from datetime import datetime

from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class BaseTool(ABC):
    """Abstract base class for AI Analyst tools.

    Subclasses must define:
        name (str): Unique tool identifier
        description (str): Shown to the AI to explain what the tool does
        parameters_schema (dict): JSON Schema for the tool's parameters

    Optional overrides:
        required_groups (list[str]): Odoo group XML IDs required to use this tool
        max_rows (int): Maximum number of rows the tool may return
        timeout_seconds (int): Per-tool execution timeout
    """

    name: str = ''
    description: str = ''
    parameters_schema: dict = {}
    required_groups: list = []
    max_rows: int = 500
    timeout_seconds: int = 30

    def get_schema(self):
        """Return the tool schema dict for the AI provider."""
        return {
            'name': self.name,
            'description': self.description,
            'parameters': self.parameters_schema,
        }

    def check_access(self, user) -> bool:
        """Check if the user has the required Odoo groups for this tool.

        Args:
            user: res.users record.

        Returns:
            bool: True if the user has access.
        """
        if not self.required_groups:
            return True
        return all(user.has_group(g) for g in self.required_groups)

    def validate_params(self, params: dict) -> dict:
        """Validate and sanitize parameters against the schema.

        Performs:
        - Required field checks
        - Type coercion for dates
        - Enum validation
        - Range clamping for limit/integer fields

        Args:
            params: Raw parameters dict from the AI.

        Returns:
            dict: Validated and sanitized parameters.

        Raises:
            ValidationError: If required params are missing or invalid.
        """
        schema = self.parameters_schema
        properties = schema.get('properties', {})
        required = schema.get('required', [])
        validated = {}

        # Check required fields
        for field_name in required:
            if field_name not in params or params[field_name] is None:
                raise ValidationError(
                    f'Missing required parameter: {field_name}'
                )

        # Validate and coerce each provided parameter
        for field_name, field_schema in properties.items():
            if field_name not in params:
                # Use default if available
                if 'default' in field_schema:
                    validated[field_name] = field_schema['default']
                continue

            value = params[field_name]
            field_type = field_schema.get('type', 'string')
            fmt = field_schema.get('format', '')

            # Date validation
            if field_type == 'string' and fmt == 'date':
                validated[field_name] = self._validate_date(field_name, value)

            # Integer with min/max
            elif field_type == 'integer':
                try:
                    int_val = int(value)
                except (ValueError, TypeError):
                    raise ValidationError(
                        f'Parameter "{field_name}" must be an integer.'
                    )
                minimum = field_schema.get('minimum')
                maximum = field_schema.get('maximum')
                if minimum is not None:
                    int_val = max(int_val, minimum)
                if maximum is not None:
                    int_val = min(int_val, maximum)
                validated[field_name] = int_val

            # Boolean
            elif field_type == 'boolean':
                if isinstance(value, bool):
                    validated[field_name] = value
                elif isinstance(value, str):
                    validated[field_name] = value.lower() in ('true', '1', 'yes')
                else:
                    validated[field_name] = bool(value)

            # Enum (string with allowed values)
            elif field_type == 'string' and 'enum' in field_schema:
                allowed = field_schema['enum']
                if value not in allowed:
                    validated[field_name] = field_schema.get('default', allowed[0])
                else:
                    validated[field_name] = value

            # Array of integers (e.g., IDs)
            elif field_type == 'array':
                if isinstance(value, list):
                    item_type = field_schema.get('items', {}).get('type', 'integer')
                    if item_type == 'integer':
                        try:
                            validated[field_name] = [int(v) for v in value]
                        except (ValueError, TypeError):
                            validated[field_name] = []
                    else:
                        validated[field_name] = value
                else:
                    validated[field_name] = []

            # Plain string
            elif field_type == 'string':
                validated[field_name] = str(value) if value is not None else ''

            else:
                validated[field_name] = value

        return validated

    @abstractmethod
    def execute(self, env, user, params: dict) -> dict:
        """Execute the tool and return structured data.

        Args:
            env: Odoo environment (already scoped to user via env(user=...)).
            user: res.users record (for context like timezone, company).
            params: Validated parameters dict.

        Returns:
            dict: Structured result data.
        """
        pass

    # --- Utility helpers for subclasses ---

    @staticmethod
    def _validate_date(field_name, value):
        """Validate and parse a date string in YYYY-MM-DD format."""
        if isinstance(value, str):
            try:
                datetime.strptime(value, '%Y-%m-%d')
                return value
            except ValueError:
                raise ValidationError(
                    f'Parameter "{field_name}" must be a valid date '
                    f'in YYYY-MM-DD format. Got: "{value}"'
                )
        raise ValidationError(
            f'Parameter "{field_name}" must be a date string in YYYY-MM-DD format.'
        )

    @staticmethod
    def _format_currency(value, currency_name=''):
        """Format a number as currency string."""
        if value is None:
            return '0.00'
        if isinstance(value, (int, float)):
            formatted = f'{value:,.2f}'
            if currency_name:
                return f'{currency_name} {formatted}'
            return formatted
        return str(value)

    @staticmethod
    def _format_percentage(value):
        """Format a number as percentage string."""
        if value is None:
            return '0.0%'
        if isinstance(value, (int, float)):
            return f'{value:.1f}%'
        return str(value)

    @staticmethod
    def _calculate_delta(current, previous):
        """Calculate percentage change between two values."""
        if not previous or previous == 0:
            if current and current > 0:
                return '+100.0%', 'up'
            return '0.0%', 'neutral'
        delta = ((current - previous) / abs(previous)) * 100
        if delta > 0:
            return f'+{delta:.1f}%', 'up'
        elif delta < 0:
            return f'{delta:.1f}%', 'down'
        return '0.0%', 'neutral'
