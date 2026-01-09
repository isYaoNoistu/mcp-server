# 探索AIOps：MCP Server（接入 Cherry Studio & Dify）

## 项目简介

本项目是一个 **MCP（Model Context Protocol）Server**，基于 **FastAPI + JSON-RPC 2.0** 实现，最初用于 **Dify 平台** 的 MCP 工具对接，在**不破坏原有核心逻辑的前提下**，通过结构化改造，实现兼容Cherry Studio。

- ✅ **完整兼容 Dify MCP 接入规范**
- ✅ **同时支持 Cherry Studio 的 JSON 导入方式**
- ✅ **工具（Tools）模块化、可扩展**
- ✅ **单一 Server，双平台复用（二合一）**

当前已内置工具：

- `read_file`：读取指定的系统文件文件（初期测试使用）。

- `prometheus_tools`：基于dify-plugin-prometheus二次开发，仅保留AI调用Prometheus功能，移除kubernetes逻辑。

- `files_query`：定义可以访问的目录，该目录下所有文件可查看。

- `system_check_tools`：定义一部分常用系统运维命令，AI可调用命令查询系统状态等等。

- `docker_tools`：定义docker相关查询信息，AI可调用命令查询docker容器状态、镜像等等。
------

## 设计原则

### 1. Dify 优先，Cherry Studio 兼容

- **原始 `/mcp` JSON-RPC 接口语义不变**
- `initialize / tools/list / tools/call` 行为完全保留
- Cherry Studio 仅通过 **额外 JSON 描述文件** + **工具元数据适配** 接入

### 2. 核心 Server 稳定，不做“推倒重写”

- `mcp_handler` 仍是唯一入口
- 生命周期状态（`SERVER_INITIALIZED`）保持一致
- 现有调用链完全可回滚

### 3. 工具即插件（Tool as Plugin）

- 每个 MCP Tool 独立成文件
- 自动注册
- 后续新增工具无需修改主逻辑

------

## 项目目录结构

```text
mcp-server/
├── mcp_server.py              # MCP 主入口（Dify / Cherry 共用）
├── requirements.txt           # Python 依赖
├── README.md                  # 项目说明（本文档）
│
├── core/                      # MCP 核心抽象
│   ├── __init__.py
│   ├── registry.py            # Tool 注册与发现
│   ├── protocol.py            # JSON-RPC / MCP 响应封装
│   └── state.py               # Server 状态管理
│
├── tools/                     # MCP 工具目录（重点）
│   ├── __init__.py
│   └── read_files.py          # 查询Linux文件的mcp工具
│   └── prometheus_tools.py    # 查询Prometheus的mcp工具
│   └── files_query.py         # 文件查询的mcp工具
│   └── system_check_tools.py  # 常用系统检查命令的mcp工具
│   └── docker_tools.py        # docker常用命令的mcp工具
│
└── cherry/                    # Cherry Studio 专用
    └── cherry_mcp.json        # Cherry Studio 导入配置 
```

------

## 核心模块说明

本节专注说明项目中负责协议、状态与工具发现/调用的核心模块：`core/protocol.py`、`core/registry.py`、`core/state.py`。这些模块构成了 MCP 服务器的最小内核：协议编解码、工具注册与分发、以及运行时状态。把注意力放在「稳定不变的核心逻辑」上，使得新增/修改工具只需在 `tools/` 中动手即可，避免频繁改动服务器协议代码。

### 1、core/protocol.py

职责：封装 JSON-RPC 的基础响应格式（成功/错误）。
- 提供 `jsonrpc_response(request_id, result)`：返回标准的 JSON-RPC 成功响应结构。
- 提供 `jsonrpc_error(request_id, code, message)`：返回标准的 JSON-RPC 错误结构。
用途：
- 将协议层与业务逻辑分离，统一返回格式，便于在 `mcp_server.py` 中直接调用。

接口要求（使用约定）：
- `request_id` 可为任意 JSON-RPC 可接受的 id（数值、字符串或 null）。
- 错误码遵循 JSON-RPC 常见约定（-32700 parse error 等），但可扩展自定义服务器错误码（如 -32002）。

### 2、core/state.py

职责：保存全局/轻量级的运行时状态。
- 当前实现例子：`MCPServerState.initialized`（bool）
用途：
- 由 `mcp_server.py` 在处理 initialize/notification 时设置或检查，以作为生命周期守卫（拒绝在未初始化时调用工具）。
扩展建议：
- 若需要更多生命周期或配置信息，可在此模块加入字段或封装成类方法（例如 `initialize()`, `reset()`）。

### 3、core/registry.py

职责：自动发现、注册并调用 `tools/` 中导出的工具对象；为工具化扩展提供统一入口。
设计原则：

- 工具实现与核心完全解耦。工具以模块形式放在 `tools/` 下，模块内必须导出一个 `tool` 对象（module-level）。
- 注册行为在服务启动时执行（`load_tools()`），只需重启或热重载即可让新工具生效。

关键函数与行为：
- `register_tool(tool)`  
  将工具对象按 `tool.name` 注册入内部字典；若工具声明 `aliases`（可选），也会将别名注册到同一对象上，支持多个调用名指向同一实现。
- `load_tools()`  
  遍历 `tools` 包中的模块，导入并注册其中的 `tool` 对象（若存在）。
- `list_tools()`  
  返回去重后的工具对象列表（用于实现 `tools/list`）。
- `call_tool(name, params)`  
  查找工具（支持主名或 alias），并在找到后调用 `tool.run(normalized_params)`，返回执行结果；找不到则抛出 `KeyError`。

参数兼容性（实用约定）：
- 不同平台/agent 可能把工具参数放在不同字段（如 `params.arguments`、`params.input`、`params.args`、或直接放在 `params` 中）。`registry` 应提供参数归一化逻辑，将这些常见变体统一转换为工具 `run()` 的 `params` 字典，减少核心修改频率。
- 工具 `run(params)` 应总是接受并期望一个字典（即使为空），并返回字符串（或可序列化的结果）；`mcp_server` 会根据平台要求把该结果封装成 `content`。

工具对象约定（示例）
- 必需：
  - `name`（str）：主名，用于注册与 discovery。
  - `run(self, params: dict) -> str`：执行入口。
- 可选：
  - `description`（str）：用于 tools/list 展示。
  - `input_schema`（dict）：JSON Schema，用于描述参数结构。
  - `aliases`（list[str]）：允许工具被多个名称调用（提高兼容性）。

示例工具骨架：
```python
class ExampleTool:
    name = "example"
    aliases = ["example_alt"]
    description = "示例工具"
    input_schema = {"type":"object", "properties": {}}

    def run(self, params):
        return "ok"

tool = ExampleTool()
```

------

## 工作流程对比

### Dify 调用链

```text
Dify
  → /mcp
    → initialize
    → tools/list
    → tools/call
```

### Cherry Studio 调用链

```text
Cherry Studio
  → 导入 cherry_mcp.json
  → 直接调用 /mcp tools/call
```

✔ **同一个 Server**
✔ **同一套工具**
✔ **零重复实现**

------

## 启动方式

```bash
pip install -r requirements.txt
python mcp_server.py
```

默认监听：

```text
http://0.0.0.0:8000/mcp
```

------

## 总结一句话

> **这是一个以 Dify 为核心、Cherry Studio 为兼容目标的工程化 MCP Server，实现了“一次开发，多平台复用”。**