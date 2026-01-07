# 适用于mcp-server的Prometheus查询工具（使用模块级常量配置Prometheus地址和认证信息）
# 导出模块级别的`tool`对象（兼容mcp-server的工具注册机制）
# 此版本的run()方法始终返回字符串，确保与Dify/Cherry Studio兼容。

import re
import requests
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

# 填写Prometheus连接信息 无需认证则留空
# <-- 在此配置Prometheus连接信息 -->
PROMETHEUS_API_URL = "http://127.0.0.1:9090"   # 改为你的Prometheus地址
PROMETHEUS_USERNAME = ""                       # 在此设置用户名（无需基础认证则留空）
PROMETHEUS_PASSWORD = ""                       # 在此设置密码（无需基础认证则留空）
PROMETHEUS_TOKEN = ""                          # 可选：在此设置Bearer Token（未使用则留空）
# ------------------------------------------------------------------------------

class PrometheusTool:
    name = "prometheus"
    aliases = ["prometheus.query"]
    description = "使用PromQL查询Prometheus指标（范围查询）。使用模块级别的PROMETHEUS_*常量配置连接信息。"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "start_time": {"type": "string"},
            "end_time": {"type": "string"},
            "step": {"type": "string"},
            "username": {"type": "string"},
            "password": {"type": "string"},
            "token": {"type": "string"}
        },
        "required": ["query"]
    }

    def run(self, params: Dict[str, Any]) -> str:
        """
        使用PROMETHEUS_API_URL和可选的认证常量执行Prometheus范围查询。
        返回字符串（成功时返回Markdown表格，失败时返回'Error: ...'格式的错误字符串）。
        认证信息解析优先级：
          1) 调用时传入的params['username']/params['password'] 或 params['token']（如果提供）
          2) 模块级常量PROMETHEUS_USERNAME / PROMETHEUS_PASSWORD
          3) 模块级常量PROMETHEUS_TOKEN
          若所有认证信息均为空，则发起无认证的请求。
        """
        try:
            if not isinstance(params, dict):
                return "Error: params must be a dict"

            query = params.get("query")
            if not query:
                return "Error: missing required parameter: query"

            start_time = params.get("start_time", "1h")
            end_time = params.get("end_time", "now")
            step = params.get("step", "15s")

            # 认证信息解析：优先使用调用时传入的参数，其次使用模块常量
            username = params.get("username") if params.get("username") is not None else PROMETHEUS_USERNAME or None
            password = params.get("password") if params.get("password") is not None else PROMETHEUS_PASSWORD or None
            token = params.get("token") if params.get("token") is not None else PROMETHEUS_TOKEN or None

            api_url = PROMETHEUS_API_URL.rstrip("/") if PROMETHEUS_API_URL else ""
            if not api_url:
                return "Error: PROMETHEUS_API_URL is not set in module"

            headers = {}
            auth = None
            # 如果提供了用户名/密码，使用基础认证（requests的auth元组）
            # 否则如果有token，使用Bearer Token请求头
            if username and password:
                auth = (username, password)
            elif token:
                headers["Authorization"] = f"Bearer {token}"

            start_iso = self._parse_time_to_iso(start_time)
            end_iso = self._parse_time_to_iso(end_time)

            url = f"{api_url}/api/v1/query_range"
            params_req = {
                "query": query,
                "start": start_iso,
                "end": end_iso,
                "step": step
            }

            resp = requests.get(url, params=params_req, headers=headers, auth=auth, timeout=30)
            if resp.status_code != 200:
                return f"Error: query failed: HTTP {resp.status_code}, {resp.text}"

            data = resp.json()
            markdown = self._format_markdown_table_from_range(data)

            return markdown

        except Exception as e:
            return f"Error: exception: {str(e)}"

    def _parse_time_to_iso(self, t: Optional[str]) -> str:
        """
        将时间表示形式转换为Prometheus可接受的RFC3339 / ISO8601格式字符串。
        支持的格式：
          - "now" -> 当前UTC时间
          - 相对时间，如'1h'（1小时前）、'30m'（30分钟前）、'15s'（15秒前）、'2d'（2天前）、'1w'（1周前）、'1M'（1个月前）、'1y'（1年前）
          - RFC3339/ISO格式字符串
          - Unix时间戳（整数/浮点数格式的字符串）
        """
        if t is None:
            t = "now"
        t = str(t).strip()
        if t.lower() == "now":
            return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        if re.fullmatch(r"^\d+(\.\d+)?$", t):
            ts = float(t)
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt.isoformat().replace("+00:00", "Z")
        m = re.fullmatch(r"^(\d+)([smhdwMy])$", t)
        if m:
            n = int(m.group(1))
            unit = m.group(2)
            now = datetime.utcnow().replace(tzinfo=timezone.utc)
            if unit == "s":
                dt = now - timedelta(seconds=n)
            elif unit == "m":
                dt = now - timedelta(minutes=n)
            elif unit == "h":
                dt = now - timedelta(hours=n)
            elif unit == "d":
                dt = now - timedelta(days=n)
            elif unit == "w":
                dt = now - timedelta(weeks=n)
            elif unit == "M":
                dt = now - timedelta(days=30 * n)
            elif unit == "y":
                dt = now - timedelta(days=365 * n)
            else:
                dt = now
            return dt.isoformat().replace("+00:00", "Z")
        try:
            txt = t.replace("Z", "+00:00") if t.endswith("Z") else t
            dt = datetime.fromisoformat(txt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt = dt.astimezone(timezone.utc)
            return dt.isoformat().replace("+00:00", "Z")
        except Exception:
            return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")

    def _format_markdown_table_from_range(self, resp_json: Dict[str, Any]) -> str:
        """
        构建Markdown表格，展示每个时间序列（指标标签）的最新时间戳和数值。
        返回字符串（Markdown格式）。
        """
        if not resp_json or resp_json.get("status") != "success":
            return "No data or query failed."

        data = resp_json.get("data", {})
        results = data.get("result", [])

        label_keys = set()
        for series in results:
            metric = series.get("metric", {}) or {}
            for k in metric.keys():
                label_keys.add(k)
        label_keys = sorted(list(label_keys))
        header_cols = label_keys + ["value", "time"]

        rows: List[Dict[str, str]] = []
        for series in results:
            metric = series.get("metric", {}) or {}
            values = series.get("values") or series.get("value")
            latest_time = ""
            latest_value = ""
            if isinstance(values, list) and values:
                ts, val = values[-1]
                latest_time = datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat().replace("+00:00", "Z")
                latest_value = str(val)
            row = {k: metric.get(k, "") for k in label_keys}
            row["value"] = latest_value
            row["time"] = latest_time
            rows.append(row)

        if not rows:
            return "No series returned."

        header_line = "| " + " | ".join(header_cols) + " |"
        sep_line = "| " + " | ".join(["---"] * len(header_cols)) + " |"
        row_lines = []
        for r in rows:
            row_lines.append("| " + " | ".join(r.get(c, "") for c in header_cols) + " |")

        md = "\n".join([header_line, sep_line] + row_lines)
        return md


# 模块级别的tool对象，供mcp-server的工具注册器使用
tool = PrometheusTool()