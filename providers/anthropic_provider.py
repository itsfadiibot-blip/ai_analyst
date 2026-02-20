# -*- coding: utf-8 -*-
"""
Anthropic Provider — Claude integration for AI Analyst.
=========================================================
Uses the official `anthropic` Python SDK for tool-calling.
"""
import json
import logging
import time

from odoo.exceptions import ValidationError

from .base_provider import BaseProvider, ProviderResponse, ToolCall

_logger = logging.getLogger(__name__)

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False
    _logger.warning(
        'anthropic Python package not installed. '
        'Install it with: pip install anthropic'
    )


class AnthropicProvider(BaseProvider):
    """Anthropic Claude provider implementation.

    Supports Claude's native tool-calling via the Messages API.
    """

    def __init__(self, config):
        super().__init__(config)
        if not HAS_ANTHROPIC:
            raise ValidationError(
                'The "anthropic" Python package is required. '
                'Install it with: pip install anthropic'
            )
        client_kwargs = {
            'api_key': self.api_key,
            'timeout': float(self.timeout),
            'max_retries': self.max_retries,
        }
        if self.api_base_url:
            client_kwargs['base_url'] = self.api_base_url

        self.client = anthropic.Anthropic(**client_kwargs)

    def chat(self, system, messages, tools=None, max_tokens=4096,
             temperature=0.1, **kwargs) -> ProviderResponse:
        """Send a chat request to Claude with optional tools.

        Converts our generic message/tool format to Anthropic's API format.
        """
        # Build Anthropic messages format
        api_messages = self._convert_messages(messages)

        # Build tool schemas in Anthropic format
        api_tools = None
        if tools:
            api_tools = self._convert_tools(tools)

        # Make the API call
        try:
            request_kwargs = {
                'model': self.model_name,
                'max_tokens': max_tokens,
                'temperature': temperature,
                'system': system,
                'messages': api_messages,
            }
            if api_tools:
                request_kwargs['tools'] = api_tools

            response = self.client.messages.create(**request_kwargs)

            return self._parse_response(response)

        except anthropic.AuthenticationError as e:
            _logger.error('Anthropic authentication failed: %s', str(e))
            raise ValidationError(
                'AI provider authentication failed. Please check the API key.'
            ) from e
        except anthropic.RateLimitError as e:
            _logger.warning('Anthropic rate limit hit: %s', str(e))
            raise ValidationError(
                'AI provider rate limit exceeded. Please try again shortly.'
            ) from e
        except anthropic.APITimeoutError as e:
            _logger.warning('Anthropic API timeout: %s', str(e))
            raise ValidationError(
                'AI provider request timed out. Please try again.'
            ) from e
        except anthropic.APIError as e:
            _logger.error('Anthropic API error: %s', str(e))
            raise ValidationError(
                f'AI provider error: {str(e)}'
            ) from e

    def validate_config(self) -> bool:
        """Validate the Anthropic configuration by making a minimal API call."""
        try:
            self.client.messages.create(
                model=self.model_name,
                max_tokens=10,
                messages=[{'role': 'user', 'content': 'Hi'}],
            )
            return True
        except Exception as e:
            raise ValidationError(
                f'Anthropic configuration validation failed: {str(e)}'
            ) from e

    def _convert_messages(self, messages):
        """Convert our generic message format to Anthropic's format.

        Handles:
        - Simple text messages (user/assistant)
        - Tool results (user messages with list content containing tool_use_id)
        - Assistant messages with tool_use blocks (raw_content from previous response)
        """
        api_messages = []

        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')

            if isinstance(content, list):
                # Could be tool results or raw content blocks
                if content and isinstance(content[0], dict):
                    if 'tool_use_id' in content[0]:
                        # These are tool results
                        api_messages.append({
                            'role': 'user',
                            'content': [
                                {
                                    'type': 'tool_result',
                                    'tool_use_id': item['tool_use_id'],
                                    'content': item.get('content', ''),
                                }
                                for item in content
                            ],
                        })
                        continue
                    else:
                        # Raw content blocks from a previous AI response
                        api_messages.append({
                            'role': role,
                            'content': content,
                        })
                        continue

            # Simple text message
            if role in ('user', 'assistant'):
                api_messages.append({
                    'role': role,
                    'content': str(content) if content else '',
                })

        return api_messages

    def _convert_tools(self, tools):
        """Convert our generic tool schemas to Anthropic's tool format.

        Our format:
            {"name": "...", "description": "...", "parameters": {...}}
        Anthropic format:
            {"name": "...", "description": "...", "input_schema": {...}}
        """
        api_tools = []
        for tool in tools:
            api_tools.append({
                'name': tool['name'],
                'description': tool.get('description', ''),
                'input_schema': tool.get('parameters', {'type': 'object', 'properties': {}}),
            })
        return api_tools

    def _parse_response(self, response):
        """Parse Anthropic's response into our unified ProviderResponse."""
        text_content = ''
        tool_calls = []
        raw_content = []

        for block in response.content:
            raw_block = block.model_dump() if hasattr(block, 'model_dump') else {}
            raw_content.append(raw_block)

            if block.type == 'text':
                text_content += block.text
            elif block.type == 'tool_use':
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    parameters=block.input if isinstance(block.input, dict) else {},
                ))

        return ProviderResponse(
            content=text_content,
            tool_calls=tool_calls,
            stop_reason=response.stop_reason or 'end_turn',
            usage={
                'input_tokens': response.usage.input_tokens,
                'output_tokens': response.usage.output_tokens,
            },
            raw_response=response.model_dump() if hasattr(response, 'model_dump') else {},
            raw_content=raw_content,
        )
