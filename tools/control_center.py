# tools/control_center.py
# A tool to manage which tools are enabled/disabled at runtime.
# Exposes a module-level `tool` object with run(params) -> str (markdown).
#
# Supported actions:
#  - action = "list"             -> list all known tools with enabled flag
#  - action = "enable"           -> enable a tool by name or alias; params: { "name": "<tool>" }
#  - action = "disable"          -> disable a tool by name or alias; params: { "name": "<tool>" }
#  - action = "status"           -> show enabled status for a tool; params: { "name": "<tool>" }
#
# Note: enabling/disabling persists into <repo_root>/.tool_state.json (via core.registry).
# This tool must be allowed to run by mcp-server's access control in production.

from typing import Any, Dict
import json

# import core registry
from core import registry as core_registry

class ControlCenterTool:
    name = "control_center"
    aliases = ["control.center", "tools_control"]
    description = "Control which tools are enabled/disabled at runtime (admin)."
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "enable", "disable", "status"], "default": "list"},
            "name": {"type": "string"}
        },
        "required": []
    }

    def run(self, params: Dict[str, Any]) -> str:
        try:
            if not isinstance(params, dict):
                return "Error: params must be a dict"
            action = (params.get("action") or "list").lower()
            if action == "list":
                return self._list_all()
            if action in ("enable", "disable", "status"):
                target = params.get("name")
                if not target:
                    return "Error: 'name' param required for enable/disable/status"
                if action == "status":
                    return self._status(target)
                elif action == "enable":
                    ok = core_registry.enable_tool(target)
                    return f"Enabled tool '{target}': {ok}"
                else:
                    ok = core_registry.disable_tool(target)
                    return f"Disabled tool '{target}': {ok}"
            return "Error: unknown action"
        except Exception as e:
            return f"Error: exception: {str(e)}"

    def _list_all(self) -> str:
        tools = core_registry.list_all_tools(include_status=True)
        lines = ["# Registered tools (including enabled state)", ""]
        for t in sorted(tools, key=lambda x: x.get("name", "")):
            lines.append(f"- **{t.get('name')}**: {t.get('description','')}")
            lines.append(f"  - aliases: {t.get('aliases', [])}")
            lines.append(f"  - enabled: {t.get('enabled')}")
            lines.append("")
        return "\n".join(lines)

    def _status(self, name: str) -> str:
        enabled = core_registry.is_enabled(name)
        return json.dumps({"name": name, "enabled": enabled}, ensure_ascii=False)

tool = ControlCenterTool()