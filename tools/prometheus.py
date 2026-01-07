# Prometheus query tool for mcp-server (reads configuration from root .env via tools.config)
# Exports a module-level `tool` object compatible with mcp-server registry.
# Returns STRING (Markdown or Error: ...) for Dify/Cherry compatibility.

import re
import requests
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from tools.config import get as cfg_get

class PrometheusTool:
    name = "prometheus"
    aliases = ["prometheus.query"]
    description = "Query Prometheus metrics using PromQL (range query). Configured via root .env."
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
        Run the Prometheus range query.
        Credential / URL resolution order:
          1) Per-call params (params.username/password or params.token)
          2) Values from .env (PROMETHEUS_USERNAME / PROMETHEUS_PASSWORD / PROMETHEUS_TOKEN)
        .env should contain PROMETHEUS_API_URL (required) and optionally credentials.
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

            # Resolve URL: prefer params, fall back to .env
            api_url = (params.get("api_url") or cfg_get("PROMETHEUS_API_URL") or "").strip()
            if not api_url:
                return "Error: PROMETHEUS_API_URL not configured in .env (or passed in params)"
            api_url = api_url.rstrip("/")

            # Resolve credentials: per-call overrides .env
            username = params.get("username") if params.get("username") is not None else cfg_get("PROMETHEUS_USERNAME") or None
            password = params.get("password") if params.get("password") is not None else cfg_get("PROMETHEUS_PASSWORD") or None
            token = params.get("token") if params.get("token") is not None else cfg_get("PROMETHEUS_TOKEN") or None

            headers = {}
            auth = None
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

tool = PrometheusTool()