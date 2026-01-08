# Prometheus query tool for mcp-server
# Prometheus 查询工具，适用于 mcp-server 服务
# - 从 .env 配置文件（通过 tools.config）读取 PROMETHEUS_API_URL 和认证信息（也可通过参数覆盖）
# - 优先使用 Prometheus 的 /api/v1/query_range 接口（范围查询）
# - 若配置允许，当范围查询不可用时，会降级为在时间范围内多次执行瞬时查询（instant query）采样
# - 始终返回字符串（markdown 格式）以保证兼容性

import re
import time
import requests
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

# 导入配置读取工具：从 .env 读取配置项
from tools.config import get as cfg_get


def _parse_time_to_iso(t: Optional[str]) -> str:
    """
    私有辅助函数：将多种格式的时间字符串解析为 UTC 时区的 ISO 格式字符串（以 Z 结尾）
    支持的时间格式：
    - "now"：当前 UTC 时间
    - 时间戳（如 1735689600 或 1735689600.123）
    - 相对时间（如 10m、1h、2d、1w、1M、1y）
    - ISO 格式字符串（如 2025-01-01T00:00:00Z 或 2025-01-01T00:00:00+08:00）
    :param t: 待解析的时间字符串（None 则视为 "now"）
    :return: UTC 时区的 ISO 8601 格式字符串（如 2025-01-01T00:00:00Z）
    """
    if t is None:
        t = "now"
    t = str(t).strip()

    # 处理 "now"：返回当前 UTC 时间的 ISO 格式
    if t.lower() == "now":
        return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")

    # 处理时间戳（整数/浮点数格式）
    if re.fullmatch(r"^\d+(\.\d+)?$", t):
        ts = float(t)
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")

    # 处理相对时间（如 10m、1h、2d 等）
    m = re.fullmatch(r"^(\d+)([smhdwMy])$", t)
    if m:
        n = int(m.group(1))  # 数值部分（如 10）
        unit = m.group(2)  # 单位部分（s/m/h/d/w/M/y）
        now = datetime.utcnow().replace(tzinfo=timezone.utc)
        # 根据单位计算偏移后的时间
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
        elif unit == "M":  # 月：简化为 30 天
            dt = now - timedelta(days=30 * n)
        elif unit == "y":  # 年：简化为 365 天
            dt = now - timedelta(days=365 * n)
        else:
            dt = now
        return dt.isoformat().replace("+00:00", "Z")

    # 处理 ISO 格式字符串（兼容带 Z 或时区偏移的格式）
    try:
        # 替换 Z 为 +00:00 以适配 fromisoformat 解析
        txt = t.replace("Z", "+00:00") if t.endswith("Z") else t
        dt = datetime.fromisoformat(txt)
        # 若时间无时区信息，默认视为 UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        # 转换为 UTC 时区
        dt = dt.astimezone(timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    except Exception:
        # 解析失败：返回当前 UTC 时间
        return datetime.utcnow().replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


class PrometheusTool:
    # 工具名称
    name = "prometheus"
    # 工具别名，用于兼容不同的调用方式
    aliases = ["prometheus.query"]
    # 工具描述：说明核心功能
    description = "Query Prometheus metrics using PromQL (range query). Configured via .env. Supports instant sampling fallback."
    # 输入参数 schema：定义调用工具时允许的参数格式和类型
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},  # 必选：PromQL 查询语句（如 node_cpu_usage{job="node"}）
            "start_time": {"type": "string"},  # 可选：查询开始时间（支持 _parse_time_to_iso 兼容的格式）
            "end_time": {"type": "string"},  # 可选：查询结束时间（默认 now）
            "step": {"type": "string"},  # 可选：范围查询的步长（默认 15s）
            "time_range": {"type": "string"},  # 可选：快捷方式，如 10m 表示查询最近 10 分钟（会覆盖 start_time）
            "sample_points": {"type": "integer"},  # 可选：降级采样时的采样点数量（默认 6）
            "allow_instant_fallback": {"type": "boolean"},  # 可选：是否允许降级为瞬时查询（默认 true）
            "username": {"type": "string"},  # 可选：Prometheus 认证用户名（覆盖 .env 配置）
            "password": {"type": "string"},  # 可选：Prometheus 认证密码（覆盖 .env 配置）
            "token": {"type": "string"},  # 可选：Prometheus Bearer Token（覆盖 .env 配置）
            "api_url": {"type": "string"}  # 可选：Prometheus API 地址（覆盖 .env 配置）
        },
        "required": ["query"]  # 强制必填参数：query（PromQL 查询语句）
    }

    def run(self, params: Dict[str, Any]) -> str:
        """
        工具核心执行方法：处理查询参数，优先执行范围查询，失败则降级为瞬时采样查询，返回 markdown 格式结果
        :param params: 调用工具时传入的参数字典
        :return: markdown 格式的查询结果字符串或错误信息
        """
        try:
            # 校验参数类型：必须是字典
            if not isinstance(params, dict):
                return "Error: params must be a dict"

            # 校验必选参数：query
            query = params.get("query")
            if not query:
                return "Error: missing required parameter: query"

            # ========== 时间参数处理 ==========
            time_range = params.get("time_range")  # 时间范围快捷参数（如 10m）
            start_time = params.get("start_time")  # 开始时间
            end_time = params.get("end_time", "now")  # 结束时间（默认 now）
            step = params.get("step", "15s")  # 范围查询步长（默认 15 秒）

            # 若指定了 time_range 且未指定 start_time：设置 start_time = now - time_range
            if time_range and not start_time:
                start_time = time_range

            # 将时间参数解析为 ISO 格式
            start_iso = _parse_time_to_iso(start_time or "1h")  # 默认查询最近 1 小时
            end_iso = _parse_time_to_iso(end_time or "now")

            # ========== API 地址和认证信息处理 ==========
            # 优先使用参数中的 api_url，其次从 .env 读取
            api_url = (params.get("api_url") or cfg_get("PROMETHEUS_API_URL") or "").strip()
            if not api_url:
                return "Error: PROMETHEUS_API_URL not configured in .env or params"
            api_url = api_url.rstrip("/")  # 移除末尾斜杠，避免 URL 拼接错误

            # 认证信息：参数优先，其次从 .env 读取（支持用户名密码 / Token 两种方式）
            username = params.get("username") if params.get("username") is not None else cfg_get(
                "PROMETHEUS_USERNAME") or None
            password = params.get("password") if params.get("password") is not None else cfg_get(
                "PROMETHEUS_PASSWORD") or None
            token = params.get("token") if params.get("token") is not None else cfg_get("PROMETHEUS_TOKEN") or None

            # 构建请求头和认证对象
            headers = {}
            auth = None
            if username and password:
                auth = (username, password)  # 基本认证
            elif token:
                headers["Authorization"] = f"Bearer {token}"  # Bearer Token 认证

            # ========== 第一步：执行范围查询（优先） ==========
            query_url = f"{api_url}/api/v1/query_range"  # 范围查询接口
            params_req = {"query": query, "start": start_iso, "end": end_iso, "step": step}
            try:
                # 发送范围查询请求（超时 30 秒）
                resp = requests.get(query_url, params=params_req, headers=headers, auth=auth, timeout=30)
            except Exception as e:
                resp = None
                resp_exc = e  # 记录异常，不立即抛出

            # 范围查询成功且有数据：格式化并返回结果
            if resp is not None and resp.status_code == 200:
                data = resp.json()
                # 检查响应状态为 success 且有结果数据
                if data.get("status") == "success" and data.get("data", {}).get("result"):
                    return self._format_markdown_table_from_range(data)
                # 范围查询返回空结果：继续尝试降级逻辑（若启用）
            else:
                # 范围查询失败（非 200 状态码 / 网络异常）：继续降级逻辑
                pass

            # ========== 第二步：降级为瞬时查询采样（若启用） ==========
            # 读取降级开关配置：参数优先，其次从 .env 读取（默认开启）
            allow_fallback_env = cfg_get("PROMETHEUS_ALLOW_INSTANT_FALLBACK") or "true"
            allow_fallback_param = params.get("allow_instant_fallback")
            if allow_fallback_param is not None:
                allow_fallback = bool(allow_fallback_param)
            else:
                allow_fallback = str(allow_fallback_env).lower() in ("1", "true", "yes", "y")

            # 若禁用降级：返回提示信息
            if not allow_fallback:
                return "No range data available and instant sampling fallback disabled."

            # 确定采样点数量：参数优先，其次从 .env 读取（默认 6 个）
            sample_points = params.get("sample_points")
            if sample_points is None:
                sp_env = cfg_get("PROMETHEUS_SAMPLE_POINTS")
                try:
                    sample_points = int(sp_env) if sp_env else 6
                except Exception:
                    sample_points = 6
            sample_points = max(1, int(sample_points))  # 至少 1 个采样点

            # 计算采样时间点：在 [start, end] 范围内均匀分布
            try:
                # 将 ISO 时间转换为 datetime 对象
                start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
            except Exception:
                # 解析失败：降级为查询最近 10 分钟
                end_dt = datetime.utcnow().replace(tzinfo=timezone.utc)
                start_dt = end_dt - timedelta(minutes=10)

            # 计算时间范围总秒数
            duration = (end_dt - start_dt).total_seconds()
            if duration <= 0:
                # 时间范围无效：仅采样结束时间
                ts_list = [end_dt]
            else:
                # 生成均匀分布的采样时间点
                ts_list = []
                for i in range(sample_points):
                    frac = i / (sample_points - 1) if sample_points > 1 else 1.0
                    ts = start_dt + timedelta(seconds=frac * duration)
                    ts_list.append(ts)

            # 执行瞬时查询：遍历所有采样时间点
            # 数据结构：{标签元组: [(时间ISO, 值), ...]}，标签元组保证唯一性
            results_by_series = {}
            instant_url = f"{api_url}/api/v1/query"  # 瞬时查询接口
            for ts in ts_list:
                ts_unix = int(ts.timestamp())  # 转换为 Unix 时间戳（秒）
                try:
                    # 发送瞬时查询请求（超时 15 秒）
                    r = requests.get(instant_url, params={"query": query, "time": ts_unix}, headers=headers, auth=auth,
                                     timeout=15)
                    if r.status_code != 200:
                        continue
                    jr = r.json()
                    if jr.get("status") != "success":
                        continue
                    # 遍历每个指标系列
                    for series in jr.get("data", {}).get("result", []):
                        metric = series.get("metric", {}) or {}
                        # 将标签转换为有序元组作为唯一键（避免字典无序问题）
                        key = tuple(sorted(metric.items()))
                        value = None
                        # 瞬时查询结果的 value 格式为 [时间戳, 数值]
                        val = series.get("value")
                        if isinstance(val, list) and len(val) >= 2:
                            value = val[1]
                        # 收集该系列的采样数据
                        results_by_series.setdefault(key, []).append(
                            (ts.isoformat().replace("+00:00", "Z"), str(value)))
                except Exception:
                    # 单个采样点失败：忽略，继续下一个
                    continue

            # 无采样数据：返回提示
            if not results_by_series:
                return "No data obtained via instant sampling fallback."

            # ========== 格式化瞬时采样结果为 Markdown 表格 ==========
            # 收集所有标签键（用于表格列）
            label_keys = set()
            for key in results_by_series.keys():
                for k, v in key:
                    label_keys.add(k)
            label_keys = sorted(list(label_keys))  # 排序保证列顺序稳定

            # 采样时间列（按采样顺序）
            ts_cols = [t.isoformat().replace("+00:00", "Z") for t in ts_list]
            # 表格头部：标签列 + 时间列
            header_cols = label_keys + ts_cols
            header_line = "| " + " | ".join(header_cols) + " |"
            sep_line = "| " + " | ".join(["---"] * len(header_cols)) + " |"

            # 构建表格行
            rows = []
            for key, samples in results_by_series.items():
                metric_dict = dict(key)
                # 填充标签列
                row = [metric_dict.get(k, "") for k in label_keys]
                # 构建采样值映射：时间 -> 数值
                sample_map = {t: v for t, v in samples}
                # 填充每个时间点的数值
                for ts in ts_cols:
                    row.append(sample_map.get(ts, ""))
                rows.append(row)

            # 拼接 Markdown 表格
            lines = [header_line, sep_line]
            for r in rows:
                lines.append("| " + " | ".join(r) + " |")
            md = "\n".join(lines)
            return md

        # 捕获所有异常并返回错误信息
        except Exception as e:
            return f"Error: exception: {str(e)}"

    def _format_markdown_table_from_range(self, resp_json: Dict[str, Any]) -> str:
        """
        私有辅助方法：将 Prometheus 范围查询的响应数据格式化为 Markdown 表格
        注：仅展示每个指标系列的**最新一个数据点**（value + time）
        :param resp_json: Prometheus 范围查询的 JSON 响应数据
        :return: Markdown 格式的表格字符串
        """
        # 校验响应有效性
        if not resp_json or resp_json.get("status") != "success":
            return "No data or query failed."

        data = resp_json.get("data", {})
        results = data.get("result", [])

        # 收集所有指标标签键（用于表格列）
        label_keys = set()
        for series in results:
            metric = series.get("metric", {}) or {}
            for k in metric.keys():
                label_keys.add(k)
        label_keys = sorted(list(label_keys))  # 排序保证列顺序稳定
        # 表格头部：标签列 + value（数值） + time（时间）
        header_cols = label_keys + ["value", "time"]

        # 构建表格行
        rows: List[List[str]] = []
        for series in results:
            metric = series.get("metric", {}) or {}
            # 范围查询结果的 values 是数组（[时间戳, 数值], ...），value 是单个数据点（兼容）
            values = series.get("values") or series.get("value")
            latest_time = ""
            latest_value = ""
            # 提取最新的一个数据点
            if isinstance(values, list) and values:
                ts, val = values[-1]
                # 转换时间戳为 ISO 格式
                latest_time = datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat().replace("+00:00", "Z")
                latest_value = str(val)
            # 填充行数据：标签列 + 最新数值 + 最新时间
            row = [metric.get(k, "") for k in label_keys] + [latest_value, latest_time]
            rows.append(row)

        # 无数据：返回提示
        if not rows:
            return "No series returned."

        # 拼接 Markdown 表格
        header_line = "| " + " | ".join(header_cols) + " |"
        sep_line = "| " + " | ".join(["---"] * len(header_cols)) + " |"
        row_lines = []
        for r in rows:
            row_lines.append("| " + " | ".join(r) + " |")

        md = "\n".join([header_line, sep_line] + row_lines)
        return md


# 创建工具实例，供外部调用
tool = PrometheusTool()