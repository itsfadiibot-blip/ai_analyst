# -*- coding: utf-8 -*-
"""
OpenAI Provider — Skeleton for GPT integration.
==================================================
This is a Phase-1 skeleton. The full implementation follows the same
pattern as AnthropicProvider but maps to OpenAI's function-calling API.

To activate, install the openai package: pip install openai
"""
import json
import logging

from odoo.exceptions import ValidationError

from .base_provider import BaseProvider, ProviderResponse, ToolCall

_logger = logging.getLogger(__name__)

try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


class OpenAIProvider(BaseProvider):
    """OpenAI GPT provider implementation (skeleton).

    Uses OpenAI's Chat Completions API with function calling.
    """

    def __init__(self, config):
        super().__init__(config)
        if not HAS_OPENAI:
            raise ValidationError(
                'The "openai" Python package is required for OpenAI provider. '
                'Install it with: pip install openai'
            )
        client_kwargs = {
            'api_key': self.api_key,
            'timeout': float(self.timeout),
            'max_retries': self.max_retries,
        }
        if self.api_base_url:
            client_kwargs['base_url'] = self.api_base_url

        self.client = openai.OpenAI(**client_kwargs)

    def chat(self, system, messages, tools=None, max_tokens=4096,
             temperature=0.1, **kwargs) -> ProviderResponse:
        """Send a chat request to OpenAI with optional tools."""
        # Build OpenAI messages (system message is a regular message)
        api_messages = [{'role': 'system', 'content': system}]
        api_messages.extend(self._convert_messages(messages))

        # Build tools in OpenAI function-calling format
        api_tools = self._convert_tools(tools) if tools else None

        try:
            request_kwargs = {
                'model': self.model_name,
                'messages': api_messages,
                'max_tokens': max_tokens,
                'temperature': temperature,
            }
            if api_tools:
                request_kwargs['tools'] = api_tools
                request_kwargs['tool_choice'] = 'auto'

            response = self.client.chat.completions.create(**request_kwargs)

            return self._parse_response(response)

        except openai.AuthenticationError as e:
            raise ValidationError(
                'OpenAI authentication failed. Please check the API key.'
            ) from e
        except openai.RateLimitError as e:
            raise ValidationError(
                'OpenAI rate limit exceeded. Please try again shortly.'
            ) from e
        except openai.APITimeoutError as e:
            raise ValidationError(
                'OpenAI request timed out. Please try again.'
            ) from e
        except openai.APIError as e:
            raise ValidationError(f'OpenAI API error: {str(e)}') from e

    def validate_config(self) -> bool:
        """Validate the OpenAI configuration."""
        try:
            self.client.chat.completions.create(
                model=self.model_name,
                max_tokens=10,
                messages=[{'role': 'user', 'content': 'Hi'}],
            )
            return True
        except Exception as e:
            raise ValidationError(
                f'OpenAI configuration validation failed: {str(e)}'
            ) from e

    def _convert_messages(self, messages):
        """Convert generic messages to OpenAI format."""
        api_messages = []
        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')

            if isinstance(content, list):
                # Tool results
                if content and isinstance(content[0], dict) and 'tool_use_id' in content[0]:
                    for item in content:
                        api_messages.append({
                            'role': 'tool',
                            'tool_call_id': item['tool_use_id'],
                            'content': item.get('content', ''),
                        })
                    continue
                # Raw content blocks (assistant with tool_calls)
                api_messages.append({'role': role, 'content': json.dumps(content)})
                continue

            api_messages.append({
                'role': role,
                'content': str(content) if content else '',
            })
        return api_messages

    def _convert_tools(self, tools):
        """Convert generic tool schemas to OpenAI function-calling format."""
        api_tools = []
        for tool in tools:
            api_tools.append({
                'type': 'function',
                'function': {
                    'name': tool['name'],
                    'description': tool.get('description', ''),
                    'parameters': tool.get('parameters', {
                        'type': 'object', 'properties': {}
                    }),
                },
            })
        return api_tools

    def _parse_response(self, response):
        """Parse OpenAI response into unified ProviderResponse."""
        choice = response.choices[0] if response.choices else None
        if not choice:
            return ProviderResponse(content='No response from model.')

        message = choice.message
        text_content = message.content or ''
        tool_calls = []

        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    params = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    params = {}
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    parameters=params,
                ))

        usage = {}
        if response.usage:
            usage = {
                'input_tokens': response.usage.prompt_tokens,
                'output_tokens': response.usage.completion_tokens,
            }

        return ProviderResponse(
            content=text_content,
            tool_calls=tool_calls,
            stop_reason='tool_use' if tool_calls else 'end_turn',
            usage=usage,
            raw_response=response.model_dump() if hasattr(response, 'model_dump') else {},
            raw_content=message.model_dump() if hasattr(message, 'model_dump') else {},
        )
