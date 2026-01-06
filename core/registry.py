# -*- coding: utf-8 -*-
import importlib
import pkgutil
from typing import Dict, Any

# name_or_alias -> tool object
_TOOL_REGISTRY: Dict[str, object] = {}


def register_tool(tool: Any):
    """
    Register a tool under its main name and any aliases it exposes.

    Tool objects should have:
      - name: str
      - description: str (optional)
      - input_schema: dict (optional)
      - run(params: dict) -> str
      - aliases: list[str] (optional)
    """
    # register primary name
    _TOOL_REGISTRY[tool.name] = tool
    # register aliases if provided
    aliases = getattr(tool, "aliases", []) or []
    for a in aliases:
        # avoid overwriting an existing different tool registered under same alias
        if a in _TOOL_REGISTRY and _TOOL_REGISTRY[a] is not tool:
            continue
        _TOOL_REGISTRY[a] = tool


def load_tools():
    """
    Import all modules under the tools package and register any `tool` object.
    """
    import tools
    for _, module_name, _ in pkgutil.iter_modules(tools.__path__):
        module = importlib.import_module(f"tools.{module_name}")
        if hasattr(module, "tool"):
            register_tool(module.tool)


def list_tools():
    """
    Return unique tool objects (de-duplicated by object identity).
    """
    seen = set()
    unique_tools = []
    for t in _TOOL_REGISTRY.values():
        if id(t) in seen:
            continue
        seen.add(id(t))
        unique_tools.append(t)
    return unique_tools


def _normalize_arguments_from_params(params: dict):
    """
    Agents may put the tool input in different fields.
    Accept common variants: 'arguments', 'input', 'args', 'parameters'.
    If params is already the raw arguments dict, return it.
    If params contains other keys (besides 'name'), treat them as arguments.
    """
    if not params or not isinstance(params, dict):
        return {}
    for key in ("arguments", "input", "args", "parameters"):
        if key in params and isinstance(params[key], dict):
            return params[key]
    # If params contains keys other than 'name', treat it as the args dict
    if any(k != "name" for k in params.keys()):
        return {k: v for k, v in params.items() if k != "name"}
    return {}


def call_tool(name: str, params: dict):
    """
    Find tool by name (or alias) and call its run() with normalized arguments.
    Raises KeyError if tool not found.
    """
    if not name or name not in _TOOL_REGISTRY:
        raise KeyError(f"Tool not found: {name}")
    tool = _TOOL_REGISTRY[name]
    args = _normalize_arguments_from_params(params or {})
    return tool.run(args)