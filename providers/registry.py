# -*- coding: utf-8 -*-
"""
Provider Registry — Maps provider_type to provider class.
============================================================
"""
import logging
from odoo.exceptions import ValidationError

from .anthropic_provider import AnthropicProvider
from .openai_provider import OpenAIProvider

_logger = logging.getLogger(__name__)

# Provider type -> class mapping
PROVIDER_MAP = {
    'anthropic': AnthropicProvider,
    'openai': OpenAIProvider,
    # Phase 2:
    # 'azure_openai': AzureOpenAIProvider,
    # 'bedrock': BedrockProvider,
    # 'local': LocalProvider,
}


def get_provider(config):
    """Instantiate the correct provider class based on config.

    Args:
        config: ai.analyst.provider.config record.

    Returns:
        BaseProvider subclass instance.

    Raises:
        ValidationError: If provider type is not supported.
    """
    provider_type = config.provider_type
    provider_cls = PROVIDER_MAP.get(provider_type)

    if not provider_cls:
        raise ValidationError(
            f'Unsupported provider type: "{provider_type}". '
            f'Available providers: {", ".join(PROVIDER_MAP.keys())}'
        )

    return provider_cls(config)
