# command_tools.py
# 四个相关的工具合并在同一模块中并导出：system_status / process_check / container_check / service_check
#
# 模块总体说明（中文）：
# - 提供一组受控、可被 AI 调用的系统检测命令，分为四类：
#   1) system_status: 系统基础信息（uname, hostname, lsb_release, uptime）
#   2) process_check: 进程与 CPU/内存 排查（top, ps, mpstat, free, vmstat）
#   3) container_check: 容器与磁盘/IO 排查（docker ps/images/stats, df, du, iostat, lsof）
#   4) service_check: 系统服务与日志检查（systemctl, journalctl, tail, pstree）
# - 默认这些命令在本机执行；如果 .env 开启远程执行(ALLOW_REMOTE_EXEC=true)并配置允许主机，
#   可传入 host 参数使命令通过 ssh 在远端执行（见 README 中的说明）。
# - 安全性：只允许执行登记在各类别字典中的命令，所有��部参数会做严格的 token 校验，禁止任意 shell 注入。
#
# 注意（中文）：
# - 远端执行是可选且默认关闭的功能。若未配置 .env 或 ALLOW_REMOTE_EXEC=false，所有命令在本机执行。
# - 请务必谨慎设置 REMOTE_ALLOWED_HOSTS、REMOTE_SSH_KEY、REMOTE_SSH_USER 等，参见 README 的安全建议。

import shutil
import subprocess
import json
import re
import os
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
from pathlib import Path

from tools.config import get as cfg_get

# 尝试导入 core.registry，以便在模块导入时能把多个工具注册到 registry 中
try:
    from core import registry as core_registry  # type: ignore
    _CORE_REGISTRY_AVAILABLE = True
except Exception:
    _CORE_REGISTRY_AVAILABLE = False

# 允许的 token 模式（保守）：字母数字、下划线、连字符、点、斜线、冒号、等号、@
_SAFE_TOKEN_RE = re.compile(r"^[\w\-\./:=@]+$")

def _is_safe_token(tok: str) -> bool:
    """校验单个 token 是否安全（用于路径、主机、服务名等输入）。"""
    return bool(_SAFE_TOKEN_RE.fullmatch(tok))

def _safe_join_args(args: List[str]) -> Tuple[bool, List[str], Optional[str]]:
    """
    验证参数数组中的每个 token，若全部合法返回 (True, sanitized_args, None)，否则返回错误信息。
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
    在本机执行命令（不使用 shell），捕获 stdout/stderr 并以 utf-8 返回。
    返回 (exit_code, stdout, stderr)。
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
    通过 SSH 在远端主机执行命令：
      ssh [-i <ssh_key>] [-p <port>] [user@]host -- <remote_argv...>
    返回 (exit_code, stdout, stderr)。
    """
    ssh_bin = shutil.which("ssh")
    if not ssh_bin:
        return 127, "", "ssh binary not available on local host"

    # 从 .env 读取 StrictHostKeyChecking 配置（可选）
    strict_check_env = str(cfg_get("REMOTE_STRICT_HOST_KEY_CHECKING") or "false").lower()
    strict_opt = "-o StrictHostKeyChecking=yes" if strict_check_env in ("1", "true", "yes", "y") else "-o StrictHostKeyChecking=no"

    ssh_cmd = [ssh_bin, "-o", "BatchMode=yes", strict_opt]
    if ssh_key:
        ssh_cmd += ["-i", ssh_key]
    if ssh_port:
        ssh_cmd += ["-p", str(ssh_port)]
    target = f"{ssh_user or ''}@{host}" if ssh_user else host
    ssh_cmd.append(target)
    ssh_cmd.append("--")
    ssh_cmd += remote_argv

    return _run_command_local(ssh_cmd, timeout=timeout)

def _format_result_md(command_line: str, exit_code: int, stdout: str, stderr: str) -> str:
    """
    将命令执行结果格式化为 Markdown 字符串，包含命令、退出码、stdout、stderr，供 AI 阅读。
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

def _take_top_lines(text: str, n: int) -> str:
    """取文本的前 n 行（用于限制输出长度）。"""
    lines = text.splitlines()
    return "\n".join(lines[:n])

def _filter_lines_containing(text: str, needle: str) -> str:
    """筛选包含指定关键字的行（用于 lsof deleted 等场景）。"""
    lines = [l for l in text.splitlines() if needle in l]
    return "\n".join(lines)

# -------------------------
# 各类命令注册表（中文说明）
# 每个命令条目包括：
#  - description: 中文用途说明
#  - cmd: 基本 argv 列表（本地/远端执行该 argv）
#  - params: 允许的命名参数（及是否必需）
# -------------------------

# 1. 系统基础信息（system_status）
_SYSTEM_STATUS_CMDS: Dict[str, Dict] = {
    "uname": {"description": "内核版本、主机架构与主机名（uname -a）", "cmd": ["uname", "-a"], "params": {}},
    "hostname": {"description": "完整主机名（FQDN）（hostname -f）", "cmd": ["hostname", "-f"], "params": {}},
    "lsb_release": {"description": "发行版信���（lsb_release -a，某些系统可能无此命令）", "cmd": ["lsb_release", "-a"], "params": {}},
    "uptime": {"description": "系统运行时长（pretty）（uptime -p）", "cmd": ["uptime", "-p"], "params": {}},
}

# 2. 进程与 CPU/MEM 排查（process_check）
_PROCESS_CHECK_CMDS: Dict[str, Dict] = {
    "top": {"description": "一次性 top 快照（top -bn1 -c），用于查看 CPU 与进程快照", "cmd": ["top", "-bn1", "-c"], "params": {"lines": {"type": "int", "default": 30}}},
    "ps_cpu": {"description": "按 CPU 使用率排序的进程列表（ps ... --sort=-pcpu）", "cmd": ["ps", "-eo", "pid,ppid,pcpu,cmd", "--sort=-pcpu"], "params": {"limit": {"type": "int", "default": 20}}},
    "ps_mem": {"description": "按内存（RSS）排序的进程列表（ps ... --sort=-rss）", "cmd": ["ps", "-eo", "pid,ppid,rss,cmd", "--sort=-rss"], "params": {"limit": {"type": "int", "default": 20}}},
    "mpstat": {"description": "各核 CPU 利用率（mpstat -P ALL 1 1）", "cmd": ["mpstat", "-P", "ALL", "1", "1"], "params": {}},
    "free": {"description": "内存与交换区使用（free -h，-h 为人类友好格式）", "cmd": ["free", "-h"], "params": {}},
    "vmstat": {"description": "内存换入/换出���页错误（vmstat 1 2）", "cmd": ["vmstat", "1", "2"], "params": {}},
}

# 3. 容器与磁盘/IO 检查（container_check）
_CONTAINER_CHECK_CMDS: Dict[str, Dict] = {
    "docker_ps": {"description": "列出 Docker 容器（docker ps -a，使用 JSON 格式每行输出）", "cmd": ["docker", "ps", "-a", "--format", "{{json .}}"], "params": {}},
    "docker_stats": {"description": "容器资源快照（docker stats --no-stream --format json）", "cmd": ["docker", "stats", "--no-stream", "--format", "{{json .}}"], "params": {}},
    "docker_images": {"description": "镜像列表（docker images -a --format json）", "cmd": ["docker", "images", "-a", "--format", "{{json .}}"], "params": {}},
    "df": {"description": "磁盘挂载点与使用率（df -hTP）", "cmd": ["df", "-hTP"], "params": {}},
    "du": {"description": "目录大小（du -sh <path>，需提供 path 参数）", "cmd": ["du", "-sh"], "params": {"path": {"type": "str", "required": True}}},
    "iostat": {"description": "磁盘 IO 统计（iostat -x 1 2）", "cmd": ["iostat", "-x", "1", "2"], "params": {}},
    "lsof": {"description": "列出打开的文件（可在输出中过滤 'deleted'，用于排查已删除但占用空间的文件）", "cmd": ["lsof"], "params": {}},
}

# 4. 系统服务与日志（service_check）
_SERVICE_CHECK_CMDS: Dict[str, Dict] = {
    "systemctl_failed": {"description": "列出失败的 systemd 服务（systemctl list-units --type=service --state=failed）", "cmd": ["systemctl", "list-units", "--type=service", "--state=failed"], "params": {}},
    "systemctl_status": {"description": "查看指定服务状态（systemctl status <service>）", "cmd": ["systemctl", "status"], "params": {"service": {"type": "str", "required": True}}},
    "ps_defunct": {"description": "查找僵尸进程（stat 包含 Z 或命令中含 defunct）", "cmd": ["ps", "-eo", "pid,ppid,stat,cmd"], "params": {}},
    "pstree": {"description": "进程树（pstree -p），显示父子关系与 PID", "cmd": ["pstree", "-p"], "params": {}},
    "journalctl": {"description": "最近系统日志（JSON 格式）（journalctl -n 50 -o json）", "cmd": ["journalctl", "-n", "50", "--no-pager", "-o", "json"], "params": {}},
    "tail": {"description": "查看文件末尾若干行（tail -n <lines> <path>）", "cmd": ["tail"], "params": {"path": {"type": "str", "required": True}, "lines": {"type": "int", "default": 100}}},
}

# 类别到注册表映射
_CATEGORY_MAP = {
    "system_status": _SYSTEM_STATUS_CMDS,
    "process_check": _PROCESS_CHECK_CMDS,
    "container_check": _CONTAINER_CHECK_CMDS,
    "service_check": _SERVICE_CHECK_CMDS,
}

def _should_run_remote(requested_host: Optional[str]) -> Tuple[bool, Optional[str], Optional[str], Optional[int], Optional[str]]:
    """
    判断是否应在远端执行（基于 .env 配置）。
    返回 (use_remote, host, ssh_user, ssh_port, ssh_key)。
    - 仅当 ALLOW_REMOTE_EXEC=true 且 host 可被允许时才返回 True。
    - 若 REMOTE_ALLOWED_HOSTS 非空，则 host 必须在白名单内。
    """
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

def _execute_category_command(category: str, cmd_key: str, named_params: Dict[str, Any], extra_args: List[str], requested_host: Optional[str]) -> str:
    """
    核心执行逻辑：
      - 校验命令是否允许执行
      - 根据命令与参数构建 argv（不使用 shell）
      - 决定本地执行或远端执行
      - 执行并对输出做后处理（例如 JSON 格式化或截断）以便 AI 分析
    """
    registry = _CATEGORY_MAP.get(category)
    if registry is None:
        return f"Error: unknown category: {category}"

    entry = registry.get(cmd_key)
    if not entry:
        return f"Error: command '{cmd_key}' not available in category '{category}'"

    base_cmd = list(entry["cmd"])

    bin0 = base_cmd[0]
    use_remote, host, ssh_user, ssh_port, ssh_key = _should_run_remote(requested_host)
    if not use_remote and not shutil.which(bin0):
        return f"Error: required binary not found on system: {bin0}"

    argv = list(base_cmd)
    params_spec = entry.get("params", {})

    for pname, spec in params_spec.items():
        if spec.get("required") and pname not in named_params:
            return f"Error: missing required parameter '{pname}' for command '{cmd_key}'"

    # 各命令的参数映射与校验
    if cmd_key == "du":
        path = named_params.get("path")
        if not isinstance(path, str) or not _is_safe_token(path):
            return "Error: invalid or unsafe 'path' parameter for du"
        argv.append(path)
    elif cmd_key == "ping":
        hostp = named_params.get("host")
        if not hostp or not _is_safe_token(hostp):
            return "Error: invalid or missing 'host' param for ping"
        count = int(named_params.get("count", 4))
        argv = ["ping", "-c", str(count), hostp]
    elif cmd_key == "curl":
        url = named_params.get("url")
        if not url or "\n" in url:
            return "Error: invalid or missing 'url' param for curl"
        timeout = int(named_params.get("timeout", 5))
        argv = ["curl", "-I", "-m", str(timeout), url]
    elif cmd_key == "tail":
        path = named_params.get("path")
        lines = int(named_params.get("lines", 100))
        if not path or not _is_safe_token(path):
            return "Error: invalid or missing 'path' param for tail"
        argv = ["tail", "-n", str(lines), path]
    elif cmd_key == "systemctl_status":
        svc = named_params.get("service")
        if not svc or not _is_safe_token(svc):
            return "Error: invalid or missing 'service' param for systemctl_status"
        argv = ["systemctl", "status", svc]

    if extra_args:
        ok, safe_args, why = _safe_join_args(list(extra_args))
        if not ok:
            return f"Error: invalid extra_args: {why}"
        argv += safe_args

    if use_remote:
        if not _is_safe_token(host):
            return "Error: unsafe host token for remote execution"
        exit_code, stdout, stderr = _run_command_ssh(host=host, ssh_user=ssh_user, ssh_key=ssh_key, ssh_port=ssh_port, remote_argv=argv, timeout=60)
    else:
        exit_code, stdout, stderr = _run_command_local(argv, timeout=60)

    displayed_stdout = stdout
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

    if cmd_key == "lsof":
        displayed_stdout = "\n".join([l for l in stdout.splitlines() if "deleted" in l])

    if cmd_key in ("ps_cpu", "ps_mem", "top"):
        lim = int(named_params.get("limit", params_spec.get("limit", {}).get("default", 20)))
        lines = displayed_stdout.splitlines()
        displayed_stdout = "\n".join(lines[:lim + 2])

    if cmd_key == "ps_defunct":
        displayed_stdout = "\n".join([l for l in stdout.splitlines() if " Z " in l or "defunct" in l])

    cmdline_str = " ".join([_shlex_quote(a) for a in (argv if not use_remote else (["ssh", host] + argv))])
    md = _format_result_md(cmdline_str, exit_code, displayed_stdout, stderr)
    return md

def _shlex_quote(s: str) -> str:
    """用于在 Markdown 中可读地对命令参数做简单引用。"""
    if re.search(r"[ \t\n'\"`]", s):
        return "'" + s.replace("'", "'\"'\"'") + "'"
    return s

# 工具基类工厂（中文注释）
class _BaseCommandTool:
    """
    工具基类，所有具体类别工具继承自此类。
    run(params) 方法返回字符串（markdown 或错误信息）。
    支持参数：
      - action: 'list' 或 'run'
      - command: 要执行的命令 key（action=run 时必需）
      - params: 命名参数字典
      - extra_args: 可选额外参数列表
      - host: 可选远端主机（需要在 .env 中允许远端执行）
    """

    name: str = "base"
    aliases: List[str] = []
    description: str = "Base command tool"
    category_key: str = ""

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

    def run(self, params: Dict[str, Any]) -> str:
        """
        运行入口（中文注释）。
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
        """返回该类别可用命令的 Markdown 列表（包含中文描述与参数说明）。"""
        registry = _CATEGORY_MAP.get(self.category_key, {})
        lines = [f"# {self.name} - 可用命令", ""]
        for k, v in sorted(registry.items()):
            desc = v.get("description", "")
            params = v.get("params", {})
            if params:
                pdesc = ", ".join([f"{p}" + (" (必需)" if params[p].get("required") else "") for p in params])
            else:
                pdesc = "无"
            lines.append(f"- **{k}**: {desc}  \n  参数: {pdesc}")
        lines.append("")
        lines.append("运行示例：action=run, command=<key>, params={...}。可选 host 用于远程执行（需启用远端执行）")
        allow_remote_env = str(cfg_get("ALLOW_REMOTE_EXEC") or "false").lower() in ("1", "true", "yes", "y")
        if allow_remote_env:
            lines.append("")
            lines.append("> 远端执行已启用。允许的主机: " + (cfg_get("REMOTE_ALLOWED_HOSTS") or cfg_get("REMOTE_DEFAULT_HOST") or "未指定"))
        else:
            lines.append("")
            lines.append("> 远端执行未启用（ALLOW_REMOTE_EXEC=false）。所有命令将在本机执行。")
        return "\n".join(lines)

# 四个具体工具类（中文说明）
class SystemStatusTool(_BaseCommandTool):
    name = "system_status"
    aliases = ["sys.status"]
    description = "系统基础信息：uname、hostname、uptime、lsb_release（中文说明）"
    category_key = "system_status"

class ProcessCheckTool(_BaseCommandTool):
    name = "process_check"
    aliases = ["proc.check"]
    description = "进程与 CPU/内存 排查：top、ps、mpstat、free、vmstat（中文说明）"
    category_key = "process_check"

class ContainerCheckTool(_BaseCommandTool):
    name = "container_check"
    aliases = ["container.check"]
    description = "容器与磁盘/IO 检查：docker ps/images/stats、df、du、iostat、lsof（中文说明）"
    category_key = "container_check"

class ServiceCheckTool(_BaseCommandTool):
    name = "service_check"
    aliases = ["service.check"]
    description = "系统服务与日志检查：systemctl、journalctl、tail、pstree（中文说明）"
    category_key = "service_check"

# 实例化工具并导出（mcp-server 的 load_tools 会注册 module.tool）
system_status_tool = SystemStatusTool()
process_check_tool = ProcessCheckTool()
container_check_tool = ContainerCheckTool()
service_check_tool = ServiceCheckTool()

# 默认导出 module-level 的 tool 对象供注册使用（兼容现有 loader）
tool = system_status_tool

# 尝试在导入时注册其余工具到 core registry（若可用）
if _CORE_REGISTRY_AVAILABLE:
    try:
        core_registry.register_tool(process_check_tool)
        core_registry.register_tool(container_check_tool)
        core_registry.register_tool(service_check_tool)
    except Exception:
        pass