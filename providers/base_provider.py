# -*- coding: utf-8 -*-
"""
Base Provider — Abstract interface for AI model providers.
============================================================
All providers must implement this interface to be compatible
with the AI Analyst gateway.
"""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

_logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """Represents a single tool call requested by the AI."""
    id: str               # Unique ID for this tool call (provider-specific)
    name: str             # Tool name
    parameters: dict      # Parsed parameters dict


@dataclass
class ProviderResponse:
    """Unified response from any AI provider."""
    content: str = ''                          # Text content (may be empty if tool_use)
    tool_calls: list = field(default_factory=list)  # List of ToolCall objects
    stop_reason: str = 'end_turn'             # "end_turn", "tool_use", "max_tokens"
    usage: dict = field(default_factory=dict)  # {"input_tokens": N, "output_tokens": M}
    raw_response: dict = field(default_factory=dict)  # Original API response
    raw_content: list = field(default_factory=list)    # Raw content blocks for tool loop


class BaseProvider(ABC):
    """Abstract base class for AI model providers.

    All providers must implement:
    - chat(): Send messages + tools, return ProviderResponse
    - validate_config(): Verify API key / endpoint
    - get_model_info(): Return model capabilities
    """

    def __init__(self, config):
        """
        Args:
            config: ai.analyst.provider.config record
        """
        self.config = config
        self.api_key = config.get_api_key()
        self.model_name = config.model_name
        self.timeout = config.timeout_seconds
        self.max_retries = config.max_retries
        self.api_base_url = config.api_base_url or None

    @abstractmethod
    def chat(self, system, messages, tools=None, max_tokens=4096,
             temperature=0.1, **kwargs) -> ProviderResponse:
        """Send messages with optional tool schemas to the AI model.

        Args:
            system (str): System prompt.
            messages (list): List of message dicts with 'role' and 'content'.
            tools (list, optional): List of tool schema dicts.
            max_tokens (int): Max output tokens.
            temperature (float): Sampling temperature.

        Returns:
            ProviderResponse: Unified response object.
        """
        pass

    @abstractmethod
    def validate_config(self) -> bool:
        """Check that the provider is properly configured.

        Returns:
            bool: True if configuration is valid.

        Raises:
            ValidationError: If configuration is invalid.
        """
        pass

    def get_model_info(self) -> dict:
        """Return information about the model.

        Returns:
            dict with keys: model_name, max_tokens, supports_tools,
                           supports_streaming, provider_type
        """
        return {
            'model_name': self.model_name,
            'provider_type': self.config.provider_type,
            'max_tokens': self.config.max_tokens,
            'supports_tools': True,
            'supports_streaming': False,
        }
