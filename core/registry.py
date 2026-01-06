# -*- coding: utf-8 -*-
import importlib
import pkgutil
from typing import Dict

_TOOL_REGISTRY: Dict[str, object] = {}


def register_tool(tool):
    _TOOL_REGISTRY[tool.name] = tool


def load_tools():
    import tools
    for _, module_name, _ in pkgutil.iter_modules(tools.__path__):
        module = importlib.import_module(f"tools.{module_name}")
        if hasattr(module, "tool"):
            register_tool(module.tool)


def list_tools():
    return _TOOL_REGISTRY.values()


def call_tool(name, params):
    if name not in _TOOL_REGISTRY:
        raise KeyError(f"Tool not found: {name}")
    return _TOOL_REGISTRY[name].run(params)
