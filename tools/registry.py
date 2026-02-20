# -*- coding: utf-8 -*-
"""
Tool Registry — Central registry for all AI Analyst tools.
=============================================================
Tools register themselves via the @register_tool decorator.
The gateway queries the registry to get available tools per user.
"""
import logging

_logger = logging.getLogger(__name__)

# Global tool registry: {tool_name: BaseTool instance}
TOOL_REGISTRY = {}


def register_tool(cls):
    """Class decorator to register a tool in the global registry.

    Usage:
        @register_tool
        class MyTool(BaseTool):
            name = 'my_tool'
            ...
    """
    instance = cls()
    if not instance.name:
        raise ValueError(f'Tool class {cls.__name__} must define a "name" attribute.')
    if instance.name in TOOL_REGISTRY:
        _logger.warning(
            'Tool "%s" is already registered. Overwriting.', instance.name
        )
    TOOL_REGISTRY[instance.name] = instance
    _logger.debug('Registered tool: %s', instance.name)
    return cls


def get_all_tools():
    """Return all registered tools.

    Returns:
        dict: {tool_name: BaseTool instance}
    """
    return dict(TOOL_REGISTRY)


def get_available_tools_for_user(user):
    """Return tools available to a specific user based on group access.

    Args:
        user: res.users record.

    Returns:
        dict: {tool_name: BaseTool instance} for tools the user can access.
    """
    available = {}
    for name, tool in TOOL_REGISTRY.items():
        if tool.check_access(user):
            available[name] = tool
    return available


def get_tool(name):
    """Get a specific tool by name.

    Args:
        name (str): Tool name.

    Returns:
        BaseTool instance or None.
    """
    return TOOL_REGISTRY.get(name)
