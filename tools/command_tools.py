# command_tools.py
# Four related tools in one module for mcp-server:
#  - system_status (basic system info / uptime / uname / lsb_release)
#  - process_check (CPU / memory / process listings)
#  - container_check (docker ps / images / stats)
#  - service_check (systemctl status / list failed)
#
# Design notes:
#  - By default commands run on the local host (mcp-server host).
#  - Remote execution via SSH is supported only if enabled in .env (ALLOW_REMOTE_EXEC=true)
#    and the requested host is allowed by REMOTE_ALLOWED_HOSTS (comma-separated) or matches
#    REMOTE_ALLOWED_HOST. SSH connection settings may be provided via .env:
#      REMOTE_SSH_USER, REMOTE_SSH_KEY, REMOTE_SSH_PORT
#  - Each tool exposes `action=list` to show available commands in that category,
#    and `action=run` to run one of the allowed commands with validated params.
#  - For compatibility with mcp-server loader, this module provides a module-level `tool`
#    object (system_status_tool). During import we also attempt to register the other
#    three tools into the registry so they appear as separate tools (if core.registry is available).
#
# Security:
#  - Only commands enumerated in the category registries are executable.
#  - User-supplied tokens/paths/hosts are validated with a conservative regexp.
#  - Remote execution is opt-in and controlled by .env settings.
#
# Each public function/method is commented with what command it runs (if any) and why.
#
# Required supporting module: tools.config (provides cfg_get(key) and repo_root()).

import shutil
import subprocess
import json
import re
import os
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
from pathlib import Path

from tools.config import get as cfg_get

# Attempt to import registry to register multiple tools at import time.
# core.registry.register_tool(tool) is used so tools can appear individually.
try:
    from core import registry as core_registry  # type: ignore
    _CORE_REGISTRY_AVAILABLE = True
except Exception:
    _CORE_REGISTRY_AVAILABLE = False

# Safety: allowed characters for tokens passed from AI (filenames, hosts, simple args)
_SAFE_TOKEN_RE = re.compile(r"^[\w\-\./:=@]+$")  # letters, digits, underscore, dash, dot, slash, colon, =, @

def _is_safe_token(tok: str) -> bool:
    """Validate a token (path, host, service name, etc.)."""
    return bool(_SAFE_TOKEN_RE.fullmatch(tok))

def _safe_join_args(args: List[str]) -> Tuple[bool, List[str], Optional[str]]:
    """
    Validate a list of argument tokens.
    Returns (ok, sanitized_args, error_message_if_any).
    """
    out = []
    for a in args:
        if not isinstance(a, str):
            return False, [], f"invalid argument type: {a!r}"
        if not _is_safe_token(a):
            return False, [], f"unsafe token in arguments: {a!r}"
        out.append(a)
    return True, out, None

def _run_command_local(argv: List[str], timeout: int = 30) -> Tuple[int, str, str]:
    """
    Execute a local command argv (no shell), capture stdout/stderr as utf-8.
    Returns (exit_code, stdout, stderr).
    """
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
    """
    Execute command remotely via SSH:
      ssh -i <ssh_key> -p <port> user@host -- <remote_argv...>
    Returns (exit_code, stdout, stderr).
    """
    ssh_bin = shutil.which("ssh")
    if not ssh_bin:
        return 127, "", "ssh binary not available on local host"

    # Build ssh command list
    ssh_cmd = [ssh_bin, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no"]
    if ssh_key:
        ssh_cmd += ["-i", ssh_key]
    if ssh_port:
        ssh_cmd += ["-p", str(ssh_port)]
    target = f"{ssh_user or ''}@{host}" if ssh_user else host
    ssh_cmd.append(target)
    ssh_cmd.append("--")
    ssh_cmd += remote_argv

    # Run locally the ssh command which in turn runs remote command
    return _run_command_local(ssh_cmd, timeout=timeout)

def _format_result_md(command_line: str, exit_code: int, stdout: str, stderr: str) -> str:
    """
    Format result as markdown for AI consumption.
    Includes executed command, exit code, stdout and stderr (each fenced).
    """
    header = f"**Command:** `{command_line}`\n\n**Exit code:** {exit_code}\n\n"
    parts = [header]
    if stdout:
        parts.append("**Stdout:**\n")
        parts.append("```\n" + stdout.strip() + "\n```\n")
    else:
        parts.append("**Stdout:** (empty)\n\n")
    if stderr:
        parts.append("**Stderr:**\n")
        parts.append("```\n" + stderr.strip() + "\n```\n")
    else:
        parts.append("**Stderr:** (empty)\n\n")
    return "".join(parts)

# -------------------------
# Command definitions by category
# Each mapping entry defines:
#  - description: human text
#  - cmd: base argv (list) to execute locally/remote
#  - params: allowed named params and whether required
#  - post: optional post-processing instructions (limit lines, grep filter, jsonize)
# -------------------------

_SYSTEM_STATUS_CMDS: Dict[str, Dict] = {
    # uname -a
    "uname": {"description": "Kernel/arch/hostname (uname -a)", "cmd": ["uname", "-a"], "params": {}},
    # hostname -f (FQDN)
    "hostname": {"description": "Full hostname (hostname -f)", "cmd": ["hostname", "-f"], "params": {}},
    # lsb_release -a (may not exist on all systems)
    "lsb_release": {"description": "Distro release info (lsb_release -a)", "cmd": ["lsb_release", "-a"], "params": {}},
    # uptime -p
    "uptime": {"description": "Pretty uptime (uptime -p)", "cmd": ["uptime", "-p"], "params": {}},
}

_PROCESS_CHECK_CMDS: Dict[str, Dict] = {
    # top -bn1 -c (non-interactive single snapshot)
    "top": {"description": "One-shot top snapshot (top -bn1 -c)", "cmd": ["top", "-bn1", "-c"], "params": {"lines": {"type": "int", "default": 30}}},
    # ps sorted by cpu
    "ps_cpu": {"description": "Top processes by CPU (ps ... --sort=-pcpu)", "cmd": ["ps", "-eo", "pid,ppid,pcpu,cmd", "--sort=-pcpu"], "params": {"limit": {"type": "int", "default": 20}}},
    # ps sorted by memory (RSS)
    "ps_mem": {"description": "Top processes by memory (RSS)", "cmd": ["ps", "-eo", "pid,ppid,rss,cmd", "--sort=-rss"], "params": {"limit": {"type": "int", "default": 20}}},
    # mpstat per-core snapshot
    "mpstat": {"description": "Per-CPU usage (mpstat -P ALL 1 1)", "cmd": ["mpstat", "-P", "ALL", "1", "1"], "params": {}},
    # free -h
    "free": {"description": "Memory and swap usage (free -h)", "cmd": ["free", "-h"], "params": {}},
    # vmstat 1 2
    "vmstat": {"description": "VM stat snapshot (vmstat 1 2)", "cmd": ["vmstat", "1", "2"], "params": {}},
}

_CONTAINER_CHECK_CMDS: Dict[str, Dict] = {
    # docker ps -a --format '{{json .}}'  (requires docker installed)
    "docker_ps": {"description": "Docker containers (docker ps -a --format json per line)", "cmd": ["docker", "ps", "-a", "--format", "{{json .}}"], "params": {}},
    # docker stats non-streaming
    "docker_stats": {"description": "Docker stats snapshot (docker stats --no-stream --format json)", "cmd": ["docker", "stats", "--no-stream", "--format", "{{json .}}"], "params": {}},
    # docker images -a --format '{{json .}}'
    "docker_images": {"description": "Docker images (docker images -a --format json per line)", "cmd": ["docker", "images", "-a", "--format", "{{json .}}"], "params": {}},
    # df -hTP
    "df": {"description": "Disk usage by mount (df -hTP)", "cmd": ["df", "-hTP"], "params": {}},
    # du -sh <path>
    "du": {"description": "Directory sizes (du -sh <path>)", "cmd": ["du", "-sh"], "params": {"path": {"type": "str", "required": True}}},
    # iostat -x 1 2
    "iostat": {"description": "I/O stats (iostat -x 1 2)", "cmd": ["iostat", "-x", "1", "2"], "params": {}},
    # lsof (we will filter 'deleted' lines in post)
    "lsof": {"description": "List open files (lsof)", "cmd": ["lsof"], "params": {}},
}

_SERVICE_CHECK_CMDS: Dict[str, Dict] = {
    # list failed
    "systemctl_failed": {"description": "Failed systemd services (systemctl list-units --type=service --state=failed)", "cmd": ["systemctl", "list-units", "--type=service", "--state=failed"], "params": {}},
    # systemctl status <service>
    "systemctl_status": {"description": "Service status (systemctl status <service>)", "cmd": ["systemctl", "status"], "params": {"service": {"type": "str", "required": True}}},
    # ps defunct
    "ps_defunct": {"description": "List defunct (zombie) processes", "cmd": ["ps", "-eo", "pid,ppid,stat,cmd"], "params": {}},
    # pstree -p
    "pstree": {"description": "Process tree with PIDs (pstree -p)", "cmd": ["pstree", "-p"], "params": {}},
    # journalctl last n json
    "journalctl": {"description": "Last 50 journal entries in json", "cmd": ["journalctl", "-n", "50", "--no-pager", "-o", "json"], "params": {}},
    # tail <path>
    "tail": {"description": "Tail a file (tail -n <lines> <path>)", "cmd": ["tail"], "params": {"path": {"type": "str", "required": True}, "lines": {"type": "int", "default": 100}}},
}

# Utility: present a registry for each tool instance
_CATEGORY_MAP = {
    "system_status": _SYSTEM_STATUS_CMDS,
    "process_check": _PROCESS_CHECK_CMDS,
    "container_check": _CONTAINER_CHECK_CMDS,
    "service_check": _SERVICE_CHECK_CMDS,
}

# Helper to determine whether to run locally or remote.
def _should_run_remote(requested_host: Optional[str]) -> Tuple[bool, Optional[str], Optional[str], Optional[int], Optional[str]]:
    """
    Determine remote execution settings.
    Returns tuple:
      (use_remote, host, ssh_user, ssh_port, ssh_key)
    Decision order:
      1) If requested_host param provided -> try to use it (if allowed)
      2) Else, if .env provides REMOTE_DEFAULT_HOST -> use it
      3) Else -> local only
    Remote allowed only if ALLOW_REMOTE_EXEC in .env is true.
    Validate host against REMOTE_ALLOWED_HOSTS (comma-separated) if present.
    """
    allow_remote_env = str(cfg_get("ALLOW_REMOTE_EXEC") or "false").lower() in ("1", "true", "yes", "y")
    if not allow_remote_env:
        return False, None, None, None, None

    host = requested_host or cfg_get("REMOTE_DEFAULT_HOST") or None
    if not host:
        return False, None, None, None, None

    # Allowed hosts configuration (optional)
    allowed_csv = cfg_get("REMOTE_ALLOWED_HOSTS") or ""
    allowed = [h.strip() for h in allowed_csv.split(",") if h.strip()]
    if allowed and host not in allowed:
        # not allowed
        return False, None, None, None, None

    ssh_user = cfg_get("REMOTE_SSH_USER") or None
    ssh_key = cfg_get("REMOTE_SSH_KEY") or None
    ssh_port = cfg_get("REMOTE_SSH_PORT") or None
    try:
        ssh_port_i = int(ssh_port) if ssh_port else None
    except Exception:
        ssh_port_i = None

    return True, host, ssh_user, ssh_port_i, ssh_key

# Shared executor used by all categories
def _execute_category_command(category: str, cmd_key: str, named_params: Dict[str, Any], extra_args: List[str], requested_host: Optional[str]) -> str:
    """
    Core execution logic:
      - Validate cmd_key is allowed for category
      - Build argv with safe tokens and params
      - Decide local vs remote
      - Execute and post-process (truncate, filter, jsonize) for better AI consumption
    """
    registry = _CATEGORY_MAP.get(category)
    if registry is None:
        return f"Error: unknown category: {category}"

    entry = registry.get(cmd_key)
    if not entry:
        return f"Error: command '{cmd_key}' not available in category '{category}'"

    base_cmd = list(entry["cmd"])

    # Ensure binary exists locally (or if remote, we will assume remote has binaries)
    bin0 = base_cmd[0]
    # Only check locally if executing locally
    use_remote, host, ssh_user, ssh_port, ssh_key = _should_run_remote(requested_host)
    if not use_remote and not shutil.which(bin0):
        return f"Error: required binary not found on system: {bin0}"

    # Build argv depending on command specifics
    argv = list(base_cmd)  # shallow copy
    params_spec = entry.get("params", {})

    # Validate required named params
    for pname, spec in params_spec.items():
        if spec.get("required") and pname not in named_params:
            return f"Error: missing required parameter '{pname}' for command '{cmd_key}'"

    # Command-specific handling
    # du -> append path (single)
    if cmd_key == "du":
        path = named_params.get("path")
        if not isinstance(path, str) or not _is_safe_token(path):
            return "Error: invalid or unsafe 'path' parameter for du"
        argv.append(path)
    # ping -> -c count host
    elif cmd_key == "ping":
        hostp = named_params.get("host")
        if not hostp or not _is_safe_token(hostp):
            return "Error: invalid or missing 'host' param for ping"
        count = int(named_params.get("count", 4))
        argv = ["ping", "-c", str(count), hostp]
    # curl -> -I -m timeout url
    elif cmd_key == "curl":
        url = named_params.get("url")
        if not url or "\n" in url:
            return "Error: invalid or missing 'url' param for curl"
        timeout = int(named_params.get("timeout", 5))
        argv = ["curl", "-I", "-m", str(timeout), url]
    # tail -> -n lines path
    elif cmd_key == "tail":
        path = named_params.get("path")
        lines = int(named_params.get("lines", 100))
        if not path or not _is_safe_token(path):
            return "Error: invalid or missing 'path' param for tail"
        argv = ["tail", "-n", str(lines), path]
    # systemctl_status -> append service name
    elif cmd_key == "systemctl_status":
        svc = named_params.get("service")
        if not svc or not _is_safe_token(svc):
            return "Error: invalid or missing 'service' param for systemctl_status"
        argv = ["systemctl", "status", svc]
    # default: no special mapping

    # Validate extra_args
    if extra_args:
        ok, safe_args, why = _safe_join_args(list(extra_args))
        if not ok:
            return f"Error: invalid extra_args: {why}"
        argv += safe_args

    # Execute (local or remote)
    if use_remote:
        # For remote, we run ssh to host with argv as remote command
        # Validate requested host token
        if not _is_safe_token(host):
            return "Error: unsafe host token for remote execution"
        exit_code, stdout, stderr = _run_command_ssh(host=host, ssh_user=ssh_user, ssh_key=ssh_key, ssh_port=ssh_port, remote_argv=argv, timeout=60)
    else:
        exit_code, stdout, stderr = _run_command_local(argv, timeout=60)

    # Post-processing for readability / AI parsing
    displayed_stdout = stdout
    # For commands that generate JSON-per-line (docker), try to parse and pretty print
    if cmd_key in ("docker_ps", "docker_stats", "docker_images"):
        items = []
        for ln in stdout.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                obj = json.loads(ln)
                items.append(obj)
            except Exception:
                items.append({"raw": ln})
        try:
            displayed_stdout = json.dumps(items, ensure_ascii=False, indent=2)
        except Exception:
            displayed_stdout = "\n".join(str(i) for i in items)

    # For lsof, filter deleted lines if present
    if cmd_key == "lsof":
        displayed_stdout = "\n".join([l for l in stdout.splitlines() if "deleted" in l])

    # For ps_cpu/ps_mem/top: apply limit
    if cmd_key in ("ps_cpu", "ps_mem", "top"):
        lim = int(named_params.get("limit", params_spec.get("limit", {}).get("default", 20)))
        lines = displayed_stdout.splitlines()
        displayed_stdout = "\n".join(lines[:lim + 2])  # include possible header

    # For ps_defunct: filter lines containing ' Z ' or 'defunct'
    if cmd_key == "ps_defunct":
        displayed_stdout = "\n".join([l for l in stdout.splitlines() if " Z " in l or "defunct" in l])

    # Format command line for display (safe quoting)
    cmdline_str = " ".join([_shlex_quote(a) for a in (argv if not use_remote else (["ssh", host] + argv))])
    md = _format_result_md(cmdline_str, exit_code, displayed_stdout, stderr)
    return md

def _shlex_quote(s: str) -> str:
    """
    Minimal quoting for display in markdown.
    """
    if re.search(r"[ \t\n'\"`]", s):
        return "'" + s.replace("'", "'\"'\"'") + "'"
    return s

# Tool base class factories
class _BaseCommandTool:
    """
    Base class for the individual tools.
    Exposes run(params) -> str
    """

    name: str = "base"
    aliases: List[str] = []
    description: str = "Base command tool"
    category_key: str = ""  # category name used in _CATEGORY_MAP

    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "run"], "default": "list"},
            "command": {"type": "string"},
            "params": {"type": "object"},
            "extra_args": {"type": "array", "items": {"type": "string"}},
            "host": {"type": "string"}  # optional remote host override
        },
        "required": []
    }

    def run(self, params: Dict[str, Any]) -> str:
        """
        Run entry for the tool.
        params:
          - action: 'list' or 'run'
          - command: key name of command to run (required for run)
          - params: dict of named params for that command
          - extra_args: optional list of extra args
          - host: optional host to run remotely (requires ALLOW_REMOTE_EXEC in .env)
        """
        try:
            if not isinstance(params, dict):
                return "Error: params must be a dict"
            action = (params.get("action") or "list").lower()
            if action == "list":
                return self._list_commands_markdown()
            elif action == "run":
                cmd_key = params.get("command")
                if not cmd_key:
                    return "Error: 'command' required when action=run"
                named = params.get("params") or {}
                extra = params.get("extra_args") or []
                host = params.get("host")
                return _execute_category_command(self.category_key, cmd_key, named, extra, host)
            else:
                return "Error: unknown action"
        except Exception as e:
            return f"Error: exception: {str(e)}"

    def _list_commands_markdown(self) -> str:
        """
        Return markdown listing available commands for the category.
        """
        registry = _CATEGORY_MAP.get(self.category_key, {})
        lines = [f"# {self.name} - available commands", ""]
        for k, v in sorted(registry.items()):
            desc = v.get("description", "")
            params = v.get("params", {})
            if params:
                pdesc = ", ".join([f"{p}" + (" (required)" if params[p].get("required") else "") for p in params])
            else:
                pdesc = "none"
            lines.append(f"- **{k}**: {desc}  \n  params: {pdesc}")
        lines.append("")
        lines.append("To run: `action=run`, `command=<key>`, `params={...}`. Optionally `host` to run remotely (if enabled).")
        # Remote execution info:
        allow_remote_env = str(cfg_get("ALLOW_REMOTE_EXEC") or "false").lower() in ("1", "true", "yes", "y")
        if allow_remote_env:
            lines.append("")
            lines.append("> Remote execution enabled. Allowed hosts: " + (cfg_get("REMOTE_ALLOWED_HOSTS") or cfg_get("REMOTE_DEFAULT_HOST") or "none specified"))
        else:
            lines.append("")
            lines.append("> Remote execution is disabled by configuration (ALLOW_REMOTE_EXEC=false).")
        return "\n".join(lines)

# Concrete tool classes
class SystemStatusTool(_BaseCommandTool):
    name = "system_status"
    aliases = ["sys.status"]
    description = "Basic system information (uname, hostname, uptime, lsb_release)."
    category_key = "system_status"

class ProcessCheckTool(_BaseCommandTool):
    name = "process_check"
    aliases = ["proc.check"]
    description = "Process and CPU/memory inspection commands."
    category_key = "process_check"

class ContainerCheckTool(_BaseCommandTool):
    name = "container_check"
    aliases = ["container.check"]
    description = "Container and disk/io related inspection commands (docker, df, du, iostat)."
    category_key = "container_check"

class ServiceCheckTool(_BaseCommandTool):
    name = "service_check"
    aliases = ["service.check"]
    description = "System service and logs inspection (systemctl, journalctl, tail)."
    category_key = "service_check"

# Instantiate tools
system_status_tool = SystemStatusTool()
process_check_tool = ProcessCheckTool()
container_check_tool = ContainerCheckTool()
service_check_tool = ServiceCheckTool()

# For compatibility with mcp-server loader which expects module-level 'tool',
# export the primary tool as 'tool'. Also, attempt to register the other tools
# into the core registry if available so they appear individually.
tool = system_status_tool

if _CORE_REGISTRY_AVAILABLE:
    try:
        # register the other three tools (system_status already will be registered via module.tool)
        core_registry.register_tool(process_check_tool)
        core_registry.register_tool(container_check_tool)
        core_registry.register_tool(service_check_tool)
    except Exception:
        # if anything goes wrong, ignore; module.tool remains available and loader will still register it
        pass