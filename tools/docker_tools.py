# docker_tools.py
# Extracted and enhanced from container_check in command_tools.py
# Maintains identical interface, security model, and execution logic.
#
# Provides:
#   tool = DockerTool()
#   tool.run({"action": "list"}) -> markdown list
#   tool.run({"action": "run", "command": "...", "params": {...}})
#
# Supports original commands: docker_ps, docker_stats, docker_images
# Plus new: docker_container_inspect, docker_image_inspect, docker_container_logs,
#           docker_networks, docker_volumes, etc.

import shutil
import subprocess
import json
import re
import os
from typing import Any, Dict, List, Optional, Tuple

from tools.config import get as cfg_get

# --- Copied safety & execution helpers (minimal necessary subset) ---

_SAFE_TOKEN_RE = re.compile(r"^[\w\-\./:=@]+$")

def _is_safe_token(tok: str) -> bool:
    return isinstance(tok, str) and bool(_SAFE_TOKEN_RE.fullmatch(tok))

def _safe_join_args(args: List[str]) -> Tuple[bool, List[str], Optional[str]]:
    out = []
    for a in args:
        if not isinstance(a, str) or not _is_safe_token(a):
            return False, [], f"unsafe token: {a!r}"
        out.append(a)
    return True, out, None

def _run_command_local(argv: List[str], timeout: int = 30) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
        out = proc.stdout.decode("utf-8", errors="replace")
        err = proc.stderr.decode("utf-8", errors="replace")
        return proc.returncode, out, err
    except FileNotFoundError:
        return 127, "", f"executable not found: {argv[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", "command timed out"
    except Exception as e:
        return 125, "", f"execution error: {str(e)}"

def _run_command_ssh(host: str, ssh_user: Optional[str], ssh_key: Optional[str], ssh_port: Optional[int], remote_argv: List[str], timeout: int = 60) -> Tuple[int, str, str]:
    ssh_bin = shutil.which("ssh")
    if not ssh_bin:
        return 127, "", "ssh binary not available"
    ssh_cmd = [ssh_bin, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no"]
    if ssh_key:
        ssh_cmd += ["-i", ssh_key]
    if ssh_port:
        ssh_cmd += ["-p", str(ssh_port)]
    target = f"{ssh_user}@{host}" if ssh_user else host
    ssh_cmd += [target, "--"] + remote_argv
    return _run_command_local(ssh_cmd, timeout=timeout)

def _shlex_quote(s: str) -> str:
    if re.search(r"[ \t\n'\"`]", s):
        return "'" + s.replace("'", "'\"'\"'") + "'"
    return s

def _format_result_md(command_line: str, exit_code: int, stdout: str, stderr: str) -> str:
    header = f"**Command:** `{command_line}`\n\n**Exit code:** {exit_code}\n\n"
    parts = [header]
    if stdout.strip():
        parts.append("**Stdout:**\n```\n" + stdout.strip() + "\n```\n")
    else:
        parts.append("**Stdout:** (empty)\n\n")
    if stderr.strip():
        parts.append("**Stderr:**\n```\n" + stderr.strip() + "\n```\n")
    else:
        parts.append("**Stderr:** (empty)\n\n")
    return "".join(parts)

def _should_run_remote(requested_host: Optional[str]) -> Tuple[bool, Optional[str], Optional[str], Optional[int], Optional[str]]:
    allow_remote_env = str(cfg_get("ALLOW_REMOTE_EXEC") or "false").lower() in ("1", "true", "yes", "y")
    if not allow_remote_env:
        return False, None, None, None, None
    host = requested_host or cfg_get("REMOTE_DEFAULT_HOST") or None
    if not host:
        return False, None, None, None, None
    allowed_csv = cfg_get("REMOTE_ALLOWED_HOSTS") or ""
    allowed = [h.strip() for h in allowed_csv.split(",") if h.strip()]
    if allowed and host not in allowed:
        return False, None, None, None, None
    ssh_user = cfg_get("REMOTE_SSH_USER") or None
    ssh_key = cfg_get("REMOTE_SSH_KEY") or None
    ssh_port = cfg_get("REMOTE_SSH_PORT") or None
    try:
        ssh_port_i = int(ssh_port) if ssh_port else None
    except Exception:
        ssh_port_i = None
    return True, host, ssh_user, ssh_port_i, ssh_key


class DockerTool:
    name = "docker"
    aliases = ["container.docker"]
    description = "Docker container, image, network, and volume inspection."

    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "run"], "default": "list"},
            "command": {"type": "string"},
            "params": {"type": "object"},
            "extra_args": {"type": "array", "items": {"type": "string"}},
            "host": {"type": "string"}
        },
        "required": []
    }

    # Command registry – original + extended
    _CMDS = {
        # Original commands (keep for compatibility)
        "docker_ps": {
            "description": "List all containers (docker ps -a --format json per line)",
            "cmd": ["docker", "ps", "-a", "--format", "{{json .}}"],
            "params": {}
        },
        "docker_stats": {
            "description": "Container resource stats snapshot",
            "cmd": ["docker", "stats", "--no-stream", "--format", "{{json .}}"],
            "params": {}
        },
        "docker_images": {
            "description": "List all images (docker images -a --format json per line)",
            "cmd": ["docker", "images", "-a", "--format", "{{json .}}"],
            "params": {}
        },
        # New extended commands
        "docker_container_inspect": {
            "description": "Inspect a container by name or ID",
            "cmd": ["docker", "inspect"],
            "params": {"container": {"type": "str", "required": True}}
        },
        "docker_image_inspect": {
            "description": "Inspect an image by name or ID",
            "cmd": ["docker", "inspect"],
            "params": {"image": {"type": "str", "required": True}}
        },
        "docker_container_logs": {
            "description": "Fetch logs from a container",
            "cmd": ["docker", "logs"],
            "params": {
                "container": {"type": "str", "required": True},
                "tail": {"type": "int", "default": 100}
            }
        },
        "docker_networks": {
            "description": "List Docker networks",
            "cmd": ["docker", "network", "ls", "--format", "{{json .}}"],
            "params": {}
        },
        "docker_network_inspect": {
            "description": "Inspect a Docker network",
            "cmd": ["docker", "network", "inspect"],
            "params": {"network": {"type": "str", "required": True}}
        },
        "docker_volumes": {
            "description": "List Docker volumes",
            "cmd": ["docker", "volume", "ls", "--format", "{{json .}}"],
            "params": {}
        },
        "docker_volume_inspect": {
            "description": "Inspect a Docker volume",
            "cmd": ["docker", "volume", "inspect"],
            "params": {"volume": {"type": "str", "required": True}}
        },
    }

    def run(self, params: Dict[str, Any]) -> str:
        if not isinstance(params, dict):
            return "**Error:** params must be a dictionary"

        action = (params.get("action") or "list").lower()
        if action == "list":
            return self._list_commands_markdown()
        elif action == "run":
            cmd_key = params.get("command")
            if not cmd_key:
                return "**Error:** 'command' is required when action=run"
            named_params = params.get("params") or {}
            extra_args = params.get("extra_args") or []
            host = params.get("host")
            return self._execute_command(cmd_key, named_params, extra_args, host)
        else:
            return f"**Error:** unsupported action '{action}'"

    def _list_commands_markdown(self) -> str:
        lines = ["# Docker Inspection Commands", ""]
        for k, v in sorted(self._CMDS.items()):
            desc = v["description"]
            params = v.get("params", {})
            if params:
                pdesc = ", ".join(
                    [f"{p}" + (" (required)" if spec.get("required") else "") for p, spec in params.items()])
            else:
                pdesc = "none"
            lines.append(f"- **{k}**: {desc}  \n  params: {pdesc}")
        lines.append("")
        lines.append("To run: `{\"action\": \"run\", \"command\": \"...\", \"params\": {...}}`")
        allow_remote = str(cfg_get("ALLOW_REMOTE_EXEC") or "false").lower() in ("1", "true", "yes", "y")
        if allow_remote:
            lines.append("> Remote execution enabled.")
        else:
            lines.append("> Remote execution disabled.")
        return "\n".join(lines)

    def _execute_command(self, cmd_key: str, named_params: Dict[str, Any], extra_args: List[str],
                         requested_host: Optional[str]) -> str:
        entry = self._CMDS.get(cmd_key)
        if not entry:
            return f"**Error:** unknown docker command '{cmd_key}'"

        base_cmd = list(entry["cmd"])
        bin0 = base_cmd[0]
        use_remote, host, ssh_user, ssh_port, ssh_key = _should_run_remote(requested_host)
        if not use_remote and not shutil.which(bin0):
            return f"**Error:** required binary not found: {bin0}"

        argv = list(base_cmd)
        params_spec = entry.get("params", {})

        # Validate required params
        for pname, spec in params_spec.items():
            if spec.get("required") and pname not in named_params:
                return f"**Error:** missing required parameter '{pname}'"

        # Build command with params
        if cmd_key == "docker_container_inspect":
            container = named_params["container"]
            if not _is_safe_token(container):
                return "**Error:** invalid container name"
            argv.append(container)
        elif cmd_key == "docker_image_inspect":
            image = named_params["image"]
            if not _is_safe_token(image):
                return "**Error:** invalid image name"
            argv.append(image)
        elif cmd_key == "docker_container_logs":
            container = named_params["container"]
            tail = named_params.get("tail", 100)
            if not _is_safe_token(container) or not isinstance(tail, int) or tail < 0:
                return "**Error:** invalid container or tail value"
            argv.extend(["--tail", str(tail), container])
        elif cmd_key == "docker_network_inspect":
            net = named_params["network"]
            if not _is_safe_token(net):
                return "**Error:** invalid network name"
            argv.append(net)
        elif cmd_key == "docker_volume_inspect":
            vol = named_params["volume"]
            if not _is_safe_token(vol):
                return "**Error:** invalid volume name"
            argv.append(vol)

        # Extra args (rarely used for docker, but kept for compatibility)
        if extra_args:
            ok, safe_extra, why = _safe_join_args(extra_args)
            if not ok:
                return f"**Error:** {why}"
            argv.extend(safe_extra)

        # Execute
        if use_remote:
            if not _is_safe_token(host):
                return "**Error:** unsafe remote host"
            code, out, err = _run_command_ssh(host, ssh_user, ssh_key, ssh_port, argv, timeout=60)
        else:
            code, out, err = _run_command_local(argv, timeout=60)

        # Post-process JSON-per-line output
        displayed_out = out
        if cmd_key in ("docker_ps", "docker_stats", "docker_images", "docker_networks", "docker_volumes"):
            items = []
            for line in out.splitlines():
                line = line.strip()
                if line:
                    try:
                        items.append(json.loads(line))
                    except:
                        items.append({"raw": line})
            try:
                displayed_out = json.dumps(items, indent=2, ensure_ascii=False)
            except:
                displayed_out = "\n".join(str(x) for x in items)

        cmdline_str = " ".join(_shlex_quote(a) for a in (argv if not use_remote else ["ssh", host] + argv))
        return _format_result_md(cmdline_str, code, displayed_out, err)

tool = DockerTool()
