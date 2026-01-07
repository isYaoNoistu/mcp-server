# Prometheus query tool for mcp-server (uses module-level constants for Prometheus URL and credentials)
# Exports a module-level `tool` object (compatible with mcp-server registry)
# This version ALWAYS returns a string from run() to ensure compatibility with Dify/Cherry Studio.

import re
import requests
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

# 填写Prometheus连接信息 无需验证则留空
# <-- Configure Prometheus connection here -->
PROMETHEUS_API_URL = "http://127.0.0.1:9090"   # change to your Prometheus URL
PROMETHEUS_USERNAME = ""                       # set username here (leave empty for no basic-auth)
PROMETHEUS_PASSWORD = ""                       # set password here (leave empty for no basic-auth)
PROMETHEUS_TOKEN = ""                          # optional: set bearer token here (leave empty if unused)
# ------------------------------------------------------------------------------

class PrometheusTool:
    name = "prometheus"
    aliases = ["prometheus.query"]
    description = "Query Prometheus metrics using PromQL (range query). Uses module-level PROMETHEUS_* constants."
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
        Run the Prometheus range query using PROMETHEUS_API_URL and optional credential constants.
        Returns a STRING (Markdown table on success, or 'Error: ...' string on failure).
        Credential resolution order:
          1) params['username']/params['password'] or params['token'] if provided in call
          2) PROMETHEUS_USERNAME / PROMETHEUS_PASSWORD
          3) PROMETHEUS_TOKEN
          If credentials are empty, the request is made without auth.
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

            # Credential resolution: prefer per-call params, fall back to module constants
            username = params.get("username") if params.get("username") is not None else PROMETHEUS_USERNAME or None
            password = params.get("password") if params.get("password") is not None else PROMETHEUS_PASSWORD or None
            token = params.get("token") if params.get("token") is not None else PROMETHEUS_TOKEN or None

            api_url = PROMETHEUS_API_URL.rstrip("/") if PROMETHEUS_API_URL else ""
            if not api_url:
                return "Error: PROMETHEUS_API_URL is not set in module"

            headers = {}
            auth = None
            # If username/password present, use basic auth (requests auth tuple).
            # Else if token present, use Bearer token header.
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
        Convert time representations to RFC3339 / ISO8601 string acceptable by Prometheus.
        Supported formats:
          - "now" -> current UTC time
          - relative like '1h', '30m', '15s', '2d', '1w', '1M', '1y'
          - RFC3339/ISO string
          - unix timestamp (int/float string)
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
        Build a markdown table that shows for each timeseries (metric labels) the latest timestamp and value.
        Returns a string (markdown).
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


# module-level tool object required by mcp-server registry
tool = PrometheusTool()