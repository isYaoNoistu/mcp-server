# core/registry.py

import pkgutil
import importlib
import json
from pathlib import Path
from typing import Dict, List, Optional, Any

from tools.config import repo_root as cfg_repo_root, get as cfg_get, as_dict as cfg_as_dict

# All discovered tools (name/alias -> tool object)
_ALL_TOOL_REGISTRY: Dict[str, Any] = {}

# Set of canonical tool names (tool.name) that are enabled.
_ENABLED_TOOLS: set = set()

# File to persist enabled tool names
_TOOL_STATE_FILE = cfg_repo_root() / ".tool_state.json"

def _persist_state() -> None:
    """
    Persist enabled canonical tool names to _TOOL_STATE_FILE.
    Format: {"enabled": ["tool1", "tool2", ...]}
    """
    try:
        data = {"enabled": sorted(list(_ENABLED_TOOLS))}
        _TOOL_STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        # best-effort persistence; avoid crashing server for persistence failures
        pass

def _load_state() -> None:
    """
    Load state file and set _ENABLED_TOOLS accordingly.
    If no state file, leave _ENABLED_TOOLS empty (registry will default-enable during registration).
    """
    global _ENABLED_TOOLS
    if not _TOOL_STATE_FILE.exists():
        return
    try:
        j = json.loads(_TOOL_STATE_FILE.read_text(encoding="utf-8"))
        enabled = j.get("enabled", [])
        if isinstance(enabled, list):
            _ENABLED_TOOLS = set(enabled)
    except Exception:
        # ignore parse errors
        pass

def _val_truth(v: Optional[str]) -> Optional[bool]:
    if v is None:
        return None
    vv = str(v).strip().lower()
    if vv in ("1", "true", "yes", "y", "on"):
        return True
    if vv in ("0", "false", "no", "n", "off"):
        return False
    return None

def _apply_env_overrides_after_registration() -> None:
    """
    Apply .env overrides to enabled/disabled tools.
    Supported keys (case-insensitive):
      - TOOL_<CANONICAL_NAME>=0/1
      - ENABLE_TOOL_<CANONICAL_NAME>=0/1
      - <CANONICAL_NAME>=0/1
      - <CANONICAL_NAME>_TOOL=0/1

    Value truthiness: 1/true/yes/on => enable; 0/false/no/off => disable.

    Called after all tools have been registered, so canonical names are known.
    Persists final state to .tool_state.json.
    """
    all_env = cfg_as_dict()  # includes environment variables and .env file entries
    # Build set of known canonical names (uppercased for matching)
    known = {getattr(t, "name", "").upper(): getattr(t, "name", "") for t in set(_ALL_TOOL_REGISTRY.values())}

    modified = False
    for k, v in all_env.items():
        if not isinstance(k, str):
            continue
        ku = k.strip().upper()
        val_bool = _val_truth(v)
        if val_bool is None:
            continue

        target_name = None
        if ku.startswith("TOOL_"):
            target = ku[len("TOOL_"):]
            if target in known:
                target_name = known[target]
        elif ku.startswith("ENABLE_TOOL_"):
            target = ku[len("ENABLE_TOOL_"):]
            if target in known:
                target_name = known[target]
        elif ku.endswith("_TOOL"):
            target = ku[:-len("_TOOL")]
            if target in known:
                target_name = known[target]
        elif ku in known:
            target_name = known[ku]

        if target_name:
            if val_bool:
                if target_name not in _ENABLED_TOOLS:
                    _ENABLED_TOOLS.add(target_name)
                    modified = True
            else:
                if target_name in _ENABLED_TOOLS:
                    _ENABLED_TOOLS.remove(target_name)
                    modified = True

    if modified:
        _persist_state()

# Load persisted state on import (if exists)
_load_state()

def register_tool(tool: Any) -> None:
    """
    Register a tool object and its aliases into the internal registry.
    A tool object must have:
      - name: str
      - aliases: optional list[str]
    Behavior:
      - If a persisted .tool_state.json existed and listed enabled tools, those stay enabled.
      - New tools are auto-enabled by default (we add canonical name to _ENABLED_TOOLS),
        unless ALLOW_AUTO_ENABLE_NEW_TOOLS is set to a falsy value in .env.
    """
    # register canonical name
    _ALL_TOOL_REGISTRY[tool.name] = tool
    # register aliases to same object
    aliases = getattr(tool, "aliases", []) or []
    for a in aliases:
        # avoid alias collision with other tool objects
        if a in _ALL_TOOL_REGISTRY and _ALL_TOOL_REGISTRY[a] is not tool:
            continue
        _ALL_TOOL_REGISTRY[a] = tool

    # Determine whether to auto-enable new tools
    # Default behavior: auto-enable new tools on startup for convenience
    # But allow override via .env: ALLOW_AUTO_ENABLE_NEW_TOOLS=false
    allow_auto_env = cfg_get("ALLOW_AUTO_ENABLE_NEW_TOOLS")
    allow_auto = True if _val_truth(allow_auto_env) is None else bool(_val_truth(allow_auto_env))

    # If the tool is not present in persisted state, and auto-enable is allowed, enable it
    canon = getattr(tool, "name", None)
    if canon:
        if canon not in _ENABLED_TOOLS and allow_auto:
            _ENABLED_TOOLS.add(canon)
            _persist_state()
        # if allow_auto is False and _ENABLED_TOOLS is non-empty (persisted state existed),
        # do not auto-add the new tool (conservative behavior).

def apply_env_overrides() -> None:
    """
    Public wrapper to re-apply .env overrides at runtime.
    This will read .env (via tools.config) and apply TOOL_* keys,
    then persist the effective state to .tool_state.json.
    Useful for applying .env without restarting the server.
    """
    _apply_env_overrides_after_registration()

def _canonical_name_for(name_or_alias: str) -> Optional[str]:
    """
    Resolve an alias or name to canonical tool.name, or None if not found.
    """
    t = _ALL_TOOL_REGISTRY.get(name_or_alias)
    if not t:
        return None
    return getattr(t, "name", None)

def enable_tool(name_or_alias: str) -> bool:
    """
    Enable a tool by its canonical name or alias.
    Returns True if success, False if tool not known.
    Persists new state.
    """
    canon = _canonical_name_for(name_or_alias)
    if not canon:
        return False
    _ENABLED_TOOLS.add(canon)
    _persist_state()
    return True

def disable_tool(name_or_alias: str) -> bool:
    """
    Disable a tool by name or alias. Returns True if success, False if not found.
    Persists new state.
    """
    canon = _canonical_name_for(name_or_alias)
    if not canon:
        return False
    if canon in _ENABLED_TOOLS:
        _ENABLED_TOOLS.remove(canon)
        _persist_state()
    return True

def is_enabled(name_or_alias: str) -> bool:
    """
    Check whether a tool (by name or alias) is currently enabled.
    Unknown tools return False.
    """
    canon = _canonical_name_for(name_or_alias)
    if not canon:
        return False
    return canon in _ENABLED_TOOLS

def list_tools() -> List[Any]:
    """
    Return unique enabled tool objects (de-duplicated by identity).
    This is used by mcp_server.py to respond to tools/list.
    """
    seen = set()
    unique_tools = []
    for key, tool in _ALL_TOOL_REGISTRY.items():
        canon = getattr(tool, "name", None)
        if not canon:
            continue
        if canon not in _ENABLED_TOOLS:
            continue  # skip disabled tools
        if id(tool) in seen:
            continue
        seen.add(id(tool))
        unique_tools.append(tool)
    return unique_tools

def list_all_tools(include_status: bool = False) -> List[Dict[str, Any]]:
    """
    Return a list of all known tools (enabled or disabled) with metadata.
    If include_status=True, each entry includes 'enabled' boolean.
    """
    seen = set()
    out = []
    for key, tool in _ALL_TOOL_REGISTRY.items():
        if id(tool) in seen:
            continue
        seen.add(id(tool))
        entry = {
            "name": getattr(tool, "name", key),
            "description": getattr(tool, "description", ""),
            "input_schema": getattr(tool, "input_schema", {}),
            "aliases": getattr(tool, "aliases", []) or []
        }
        if include_status:
            entry["enabled"] = entry["name"] in _ENABLED_TOOLS
        out.append(entry)
    return out

def _normalize_arguments_from_params(params: dict):
    """
    Standardize input params. Keep original logic for compatibility.
    Supports 'arguments', 'input', 'args', 'parameters' or top-level keys.
    """
    if not params or not isinstance(params, dict):
        return {}
    for key in ("arguments", "input", "args", "parameters"):
        if key in params and isinstance(params[key], dict):
            return params[key]
    if any(k != "name" for k in params.keys()):
        return {k: v for k, v in params.items() if k != "name"}
    return {}

def call_tool(name: str, params: dict):
    """
    Call a tool by name or alias but only if it is enabled.
    Raises KeyError if tool not found or disabled.
    """
    if not name or name not in _ALL_TOOL_REGISTRY:
        raise KeyError(f"Tool not found: {name}")
    tool = _ALL_TOOL_REGISTRY[name]
    canon = getattr(tool, "name", None)
    if not canon or canon not in _ENABLED_TOOLS:
        raise KeyError(f"Tool not enabled: {name}")
    args = _normalize_arguments_from_params(params or {})
    return tool.run(args)

def load_tools():
    """
    Auto-load tools under tools package and register them.
    After registration, apply .env overrides (TOOL_* keys) to set enabled/disabled state.
    """
    import tools  # must exist
    for _, module_name, _ in pkgutil.iter_modules(tools.__path__):
        module = importlib.import_module(f"tools.{module_name}")
        if hasattr(module, "tool"):
            register_tool(module.tool)

    # After all tools registered, apply .env overrides (if any)
    _apply_env_overrides_after_registration()