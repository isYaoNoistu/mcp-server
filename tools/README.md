# MCP-Server Prometheus 查询工具
一款轻量、易集成的工具，用于在 MCP-Server 生态中通过 PromQL 范围查询获取 Prometheus 监控指标。该工具将查询结果转换为易读的 Markdown 表格，支持灵活的时间格式和多种认证方式。

## 1. 工具概述
本工具专为 MCP-Server 设计，作为模块注册后可提供标准化接口，执行 PromQL 范围查询并返回格式化结果。核心能力包括：
- 采用**模块级常量**集中配置 Prometheus 服务地址，所有查询复用该配置
- 支持多种时间格式（相对时间、ISO8601 标准格式、Unix 时间戳、"now" 关键字）
- 兼容 Prometheus 认证机制（基本认证 / Bearer 令牌认证）
- 将查询结果格式化为清晰的 Markdown 表格（展示每个时间序列的最新值和时间戳）
- 完善的异常处理机制，返回人性化的错误提示文本

## 2. 安装与依赖
### 必备依赖
使用前需安装以下 Python 包：
```bash
pip install requests python-dotenv  # python-dotenv 为可选（用于环境变量配置）
```

### 与 MCP-Server 集成
1. 将本工具模块放置到 MCP-Server 的工具注册目录（遵循 MCP-Server 工具注册规范）
2. 配置 `PROMETHEUS_API_URL` 常量（见第 3 节）
3. 重启/重载 MCP-Server 完成工具注册

## 3. 工具配置
工具通过**模块级常量**定义 Prometheus 服务地址，使用前需先配置：

```python
# 工具代码第 9 行 - 替换为你的 Prometheus 服务地址
PROMETHEUS_API_URL = "http://127.0.0.1:9090"  # 默认值：本地 Prometheus 实例
```

配置说明：
- 确保地址末尾无斜杠（工具会自动去除末尾斜杠）
- 验证 MCP-Server 与 Prometheus 服务的网络连通性
- 若访问远程 Prometheus 实例，需确保防火墙/安全组放行 Prometheus API 端口（默认 9090）

## 4. 工具入参
工具遵循 MCP-Server 入参规范，支持以下参数：

| 参数名      | 类型   | 是否必填 | 默认值 | 说明                                                                 |
|-------------|--------|----------|--------|----------------------------------------------------------------------|
| `query`     | 字符串 | ✅        | -      | PromQL 查询语句（示例：`node_cpu_usage{instance="server-01"}`）      |
| `start_time`| 字符串 | ❌        | `1h`   | 范围查询的开始时间（支持格式见第 5 节）                             |
| `end_time`  | 字符串 | ❌        | `now`  | 范围查询的结束时间（支持格式见第 5 节）                             |
| `step`      | 字符串 | ❌        | `15s`  | 查询步长/分辨率（示例：`10s`、`1m`、`5m`）                          |
| `username`  | 字符串 | ❌        | -      | Prometheus 基本认证用户名（需与 `password` 配合使用）                |
| `password`  | 字符串 | ❌        | -      | Prometheus 基本认证密码（需与 `username` 配合使用）                  |
| `token`     | 字符串 | ❌        | -      | Prometheus API 认证的 Bearer 令牌（优先级高于基本认证）              |

### 参数优先级
- 若同时提供 `token` 和 `username`/`password`，优先使用 `token`（Bearer 认证）
- 步长需符合 Prometheus 规范（如 `15s`、`1m`、`1h`，无空格）

## 5. 支持的时间格式
`start_time` 和 `end_time` 参数支持多种灵活格式（所有时间最终转换为 UTC 时区）：

| 格式类型       | 示例                  | 说明                                                              |
|----------------|-----------------------|-------------------------------------------------------------------|
| "now" 关键字   | `now`                 | 当前 UTC 时间（`end_time` 的默认值）                             |
| 相对时间       | `1h`、`30m`、`2d`、`1w` | 相对于当前时间的偏移（从当前 UTC 时间减去对应时长）：<br>- `s`：秒<br>- `m`：分钟<br>- `h`：小时<br>- `d`：天<br>- `w`：周<br>- `M`：月（按 30 天计算）<br>- `y`：年（按 365 天计算） |
| ISO8601/RFC3339 | `2026-01-07T12:00:00Z` | 标准 UTC 时间戳（支持 `Z` 或 `+00:00` 时区标识）                 |
| Unix 时间戳    | `1736246400`          | 数字型 Unix 时间戳（整数/浮点数，示例：`1736246400.5`）           |

## 6. 使用示例
### 基础示例（无认证）
查询过去 1 小时内的 CPU 空闲时间，步长 15 秒：
```python
# MCP-Server 调用工具的入参示例
params = {
    "query": "node_cpu_seconds_total{mode='idle'}",
    "start_time": "1h",
    "end_time": "now",
    "step": "15s"
}

# 工具返回的 Markdown 表格字符串示例：
"""
| __name__               | instance   | job    | value  | time                  |
|------------------------|------------|--------|--------|-----------------------|
| node_cpu_seconds_total | server-01  | node   | 12345  | 2026-01-07T12:00:00Z  |
| node_cpu_seconds_total | server-02  | node   | 67890  | 2026-01-07T12:00:00Z  |
"""
```

### Bearer 令牌认证示例
```python
params = {
    "query": "prometheus_http_requests_total",
    "start_time": "2026-01-07T10:00:00Z",
    "end_time": "2026-01-07T11:00:00Z",
    "step": "1m",
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

### 基本认证示例
```python
params = {
    "query": "up{job='mcp-server'}",
    "start_time": "2d",
    "end_time": "1d",
    "step": "5m",
    "username": "prometheus-user",
    "password": "secure-password-123"
}
```

## 7. 错误处理
工具将异常场景封装为以 `Error:` 开头的纯文本字符串返回，常见错误场景如下：

| 错误场景                | 示例错误信息                                                          |
|-------------------------|-----------------------------------------------------------------------|
| 缺少 `query` 参数       | `Error: missing required parameter: query`                            |
| Prometheus 地址未配置   | `Error: PROMETHEUS_API_URL is not set in module`                      |
| Prometheus HTTP 错误    | `Error: query failed: HTTP 401, {"status":"error","errorType":"unauthorized"}` |
| 通用运行时异常          | `Error: exception: ConnectionRefusedError: [Errno 111] Connection refused` |

## 8. 核心实现细节
### 核心工作流程
```mermaid
graph TD
    A[MCP-Server 调用 tool.run()] --> B[参数校验]
    B --> C[将开始/结束时间解析为 ISO8601 格式]
    C --> D[构建 Prometheus API 请求]
    D --> E[发送请求（附带配置的认证信息）]
    E --> F{HTTP 状态码是否为 200?}
    F -->|否| G[返回错误字符串]
    F -->|是| H[解析 JSON 响应数据]
    H --> I[将结果格式化为 Markdown 表格]
    I --> J[返回 Markdown 字符串]
```

### 关键方法说明
- `run()`：工具主入口，负责参数校验、API 调用、异常捕获与封装
- `_parse_time_to_iso()`：将灵活的时间输入转换为 Prometheus 兼容的 ISO8601 UTC 时间戳
- `_format_markdown_table_from_range()`：将 Prometheus API 返回的 JSON 数据转换为易读的 Markdown 表格（展示每个时间序列的最新值）

### 总结
1. 该工具是 MCP-Server 的 Prometheus 查询模块，核心通过调用 Prometheus 的 `/api/v1/query_range` API 实现 PromQL 范围查询，最终返回 Markdown 表格格式的结果
2. 核心配置为 `PROMETHEUS_API_URL` 常量，支持基本认证和 Bearer 令牌两种认证方式，时间参数兼容相对时间、ISO8601、Unix 时间戳等多种格式
3. 工具内置完善的参数校验和错误处理机制，返回的错误信息清晰易懂，便于集成到 MCP-Server 的业务流程中调试和使用