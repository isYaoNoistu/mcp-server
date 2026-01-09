# Jenkins 工具 for mcp-server
# 功能（中文）：
# - 与 Jenkins 交互，提供常用操作：ping, list_jobs, job_info, console_log, recent_builds
# - 优先使用安装的 jenkins_mcp_enterprise（若存在），否则使用 requests 直接调用 Jenkins REST API
# - 从 .env 读取配置：JENKINS_URL, JENKINS_USER, JENKINS_TOKEN, JENKINS_TIMEOUT, JENKINS_CONSOLE_MAX_BYTES
# - 对 Jenkins 返回的 timestamp（毫秒）做正确转换，输出本地 ISO 时间与相对时间（如 "3 天前"）
# - 返回值始终为字符串（Markdown 或以 "Error:" 开头的文本），以兼容 mcp-server
#
# 使用示例（JSON-RPC tools/call）:
# {
#   "name": "jenkins_tools",
#   "arguments": {"action":"recent_builds", "job":"myjob", "limit": 5}
# }
#
# 注意：请将 Jenkins 凭据放在仓库根 .env（或环境变量）中，避免将 .env 提交到公开仓库。

import json
from typing import Any, Dict, Optional
from urllib.parse import urljoin
from datetime import datetime, timezone
import requests

from tools.config import get as cfg_get

# 尝试检测高级库（可选）
_JMCP_AVAILABLE = False
try:
    import jenkins_mcp_enterprise  # type: ignore
    _JMCP_AVAILABLE = True
except Exception:
    _JMCP_AVAILABLE = False

def _get_jenkins_config():
    """从 .env 读取 Jenkins 配置（返回 base_url, user, token, timeout(int)）"""
    url = (cfg_get("JENKINS_URL") or "").rstrip("/")
    user = cfg_get("JENKINS_USER") or None
    token = cfg_get("JENKINS_TOKEN") or None
    try:
        timeout = int(cfg_get("JENKINS_TIMEOUT") or 30)
    except Exception:
        timeout = 30
    try:
        max_bytes = int(cfg_get("JENKINS_CONSOLE_MAX_BYTES") or 204800)
    except Exception:
        max_bytes = 204800
    return url, user, token, timeout, max_bytes

def _auth_tuple(user: Optional[str], token: Optional[str]):
    """返回 requests 可用的 auth tuple 或 None"""
    if user and token:
        return (user, token)
    return None

def _build_job_path(job_name: str) -> str:
    """
    将 folder/child/jobname 转换为 Jenkins API 路径片段：
    "parent/child/jobname" -> "job/parent/job/child/job/jobname"
    如果传入的是完整 URL，则返回去掉末尾斜杠的 URL。
    """
    if job_name.startswith("http://") or job_name.startswith("https://"):
        return job_name.rstrip("/")
    parts = [p for p in job_name.strip("/").split("/") if p]
    segs = []
    for p in parts:
        segs.append("job")
        segs.append(p)
    return "/".join(segs)

def _format_timestamp_ms(ts_ms: Optional[int]):
    """
    将 Jenkins 的毫秒 timestamp 转为 (iso_local, relative_str)。
    若 ts_ms 为空或无效，返回 ("", "")。
    """
    if ts_ms is None:
        return ("", "")
    try:
        ts_ms = int(ts_ms)
    except Exception:
        return ("invalid", "")
    ts_s = ts_ms / 1000.0
    # Jenkins timestamp 通常以 UTC 表示
    dt_utc = datetime.fromtimestamp(ts_s, tz=timezone.utc)
    # 转为本地时区
    dt_local = dt_utc.astimezone()
    iso = dt_local.isoformat()
    now = datetime.now(timezone.utc).astimezone()
    delta = now - dt_local
    secs = delta.total_seconds()
    if secs < 60:
        rel = f"{int(secs)} 秒前"
    elif secs < 3600:
        rel = f"{int(secs//60)} 分钟前"
    elif secs < 86400:
        rel = f"{int(secs//3600)} 小时前"
    else:
        rel = f"{int(delta.days)} 天前"
    return iso, rel

class JenkinsTools:
    name = "jenkins_tools"
    aliases = ["jenkins", "jenkins_mcp"]
    description = "Jenkins 工具：ping / 列表 jobs / job 信息 / console log / recent builds（配置来自 .env）"
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["ping", "list_jobs", "job_info", "console_log", "recent_builds"], "default": "ping"},
            "job": {"type": "string"},
            "build_number": {"type": "integer"},
            "limit": {"type": "integer", "default": 5},
            "depth": {"type": "integer", "default": 1}
        },
        "required": []
    }

    def run(self, params: Dict[str, Any]) -> str:
        if not isinstance(params, dict):
            return "Error: params must be a dict"
        action = (params.get("action") or "ping").strip()
        base_url, user, token, timeout, max_bytes = _get_jenkins_config()
        if not base_url:
            return "Error: JENKINS_URL 未配置（请在 .env 中设置 JENKINS_URL）"

        auth = _auth_tuple(user, token)
        headers = {"Accept": "application/json"}

        # 如果存在高级库，可以在这里扩展调用；当前以 REST API 为主
        try:
            if action == "ping":
                return self._ping(base_url, auth, headers, timeout)
            elif action == "list_jobs":
                depth = int(params.get("depth", 1))
                return self._list_jobs(base_url, auth, headers, timeout, depth)
            elif action == "job_info":
                job = params.get("job")
                if not job:
                    return "Error: 'job' 参数必需"
                return self._job_info(base_url, auth, headers, timeout, job)
            elif action == "console_log":
                job = params.get("job")
                build_number = params.get("build_number")
                if not job or build_number is None:
                    return "Error: 'job' 与 'build_number' 参数必需"
                return self._console_log(base_url, auth, headers, timeout, job, int(build_number), max_bytes)
            elif action == "recent_builds":
                job = params.get("job")
                limit = int(params.get("limit", 5))
                if not job:
                    return "Error: 'job' 参数必需"
                return self._recent_builds(base_url, auth, headers, timeout, job, limit)
            else:
                return f"Error: unknown action: {action}"
        except Exception as e:
            return f"Error: exception: {str(e)}"

    def _ping(self, base: str, auth, headers: Dict[str, str], timeout: int) -> str:
        url = base + "/api/json"
        try:
            r = requests.get(url, auth=auth, headers=headers, timeout=timeout)
            if r.status_code != 200:
                return f"Error: ping failed: HTTP {r.status_code} - {r.text[:400]}"
            j = r.json()
            version = r.headers.get("X-Jenkins", "")
            md = f"# Jenkins Ping\n\n- URL: {base}\n- API OK\n- X-Jenkins: {version}\n- description: {j.get('description','')}\n"
            return md
        except Exception as e:
            return f"Error: ping exception: {e}"

    def _list_jobs(self, base: str, auth, headers: Dict[str, str], timeout: int, depth: int = 1) -> str:
        """
        列出 jobs（顶层），若 depth>1 则尝试探查文件夹内的子 job（简单实现）
        """
        try:
            api = base + "/api/json?tree=jobs[name,color,url]"
            r = requests.get(api, auth=auth, headers=headers, timeout=timeout)
            if r.status_code != 200:
                return f"Error: list_jobs failed: HTTP {r.status_code} - {r.text[:400]}"
            data = r.json()
            jobs = data.get("jobs", [])
            lines = ["# Jenkins Jobs (top-level)", ""]
            for j in jobs:
                lines.append(f"- **{j.get('name')}**  - color: {j.get('color')}  - url: {j.get('url')}")
            if depth > 1:
                lines.append("")
                lines.append("## Subfolders (depth>1) (partial):")
                for j in jobs:
                    try:
                        subapi = j.get("url").rstrip("/") + "/api/json"
                        sr = requests.get(subapi, auth=auth, headers=headers, timeout=timeout)
                        if sr.status_code != 200:
                            continue
                        sd = sr.json()
                        subjobs = sd.get("jobs", [])
                        if subjobs:
                            lines.append(f"### Folder: {j.get('name')}")
                            for sj in subjobs[:200]:
                                lines.append(f"- {sj.get('name')}  - {sj.get('url')}")
                    except Exception:
                        continue
            return "\n".join(lines)
        except Exception as e:
            return f"Error: list_jobs exception: {e}"

    def _job_info(self, base: str, auth, headers: Dict[str, str], timeout: int, job: str) -> str:
        try:
            path = _build_job_path(job)
            api = base + "/" + path + "/api/json"
            r = requests.get(api, auth=auth, headers=headers, timeout=timeout)
            if r.status_code != 200:
                return f"Error: job_info failed: HTTP {r.status_code} - {r.text[:400]}"
            j = r.json()
            # 抽取关键信息并格式化时间
            last_build = j.get("lastBuild") or {}
            last_completed = j.get("lastCompletedBuild") or {}
            md_lines = [
                f"# Job: {job}",
                "",
                f"- displayName: {j.get('displayName')}",
                f"- fullName: {j.get('fullName')}",
                f"- url: {j.get('url')}",
                f"- color: {j.get('color')}",
                f"- lastBuild: {last_build}",
                f"- lastCompletedBuild: {last_completed}",
                f"- total builds (reported): {len(j.get('builds', []))}"
            ]
            return "\n".join(md_lines)
        except Exception as e:
            return f"Error: job_info exception: {e}"

    def _console_log(self, base: str, auth, headers: Dict[str, str], timeout: int, job: str, build_number: int, max_bytes: int) -> str:
        try:
            path = _build_job_path(job)
            url = base + "/" + path + f"/{build_number}/consoleText"
            r = requests.get(url, auth=auth, headers=headers, timeout=timeout)
            if r.status_code != 200:
                return f"Error: console_log failed: HTTP {r.status_code} - {r.text[:400]}"
            text = r.text
            truncated = len(text.encode("utf-8")) > max_bytes
            if truncated:
                text = text.encode("utf-8")[:max_bytes].decode("utf-8", errors="replace")
            md = f"# Console Log: {job}#{build_number}\n\n"
            if truncated:
                md += f"> Note: console truncated to {max_bytes} bytes\n\n"
            md += "```\n" + text + "\n```\n"
            return md
        except Exception as e:
            return f"Error: console_log exception: {e}"

    def _recent_builds(self, base: str, auth, headers: Dict[str, str], timeout: int, job: str, limit: int) -> str:
        """
        返回最近 limit 个构建的简要信息，包含 timestamp 的 ISO 与相对时间
        """
        try:
            path = _build_job_path(job)
            # 使用 tree 参数获取必要的字段（兼容性更好）
            api = base + "/" + path + f"/api/json?tree=builds[number,result,timestamp,id]{{0,{limit}}}"
            r = requests.get(api, auth=auth, headers=headers, timeout=timeout)
            if r.status_code != 200:
                return f"Error: recent_builds failed: HTTP {r.status_code} - {r.text[:400]}"
            j = r.json()
            builds = j.get("builds", [])[:limit]
            lines = [f"# Recent builds for {job}", ""]
            for b in builds:
                ts = b.get("timestamp")
                iso, rel = _format_timestamp_ms(ts)
                lines.append(f"- #{b.get('number')}  result: {b.get('result')}  id: {b.get('id')}  ts(ms): {ts}  time: {iso}  ({rel})")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: recent_builds exception: {e}"

# module-level tool object required by registry
tool = JenkinsTools()