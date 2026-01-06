# MCP Server（Dify & Cherry Studio 双兼容）

## 项目简介

本项目是一个 **MCP（Model Context Protocol）Server**，基于 **FastAPI + JSON-RPC 2.0** 实现，最初用于 **Dify 平台** 的 MCP 工具对接，在**不破坏原有核心逻辑的前提下**，通过结构化改造，实现：

- ✅ **完整兼容 Dify MCP 接入规范**
- ✅ **同时支持 Cherry Studio 的 JSON 导入方式**
- ✅ **工具（Tools）模块化、可扩展**
- ✅ **单一 Server，双平台复用（二合一）**

当前已内置示例工具：

- `read_linux_yaml`：读取 Prometheus Linux 规则 YAML 文件

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
│   └── read_linux_yaml.py     # 查询Linux文件的mcp工具
│
├── cherry/                    # Cherry Studio 专用
│   ├── cherry_mcp.json        # Cherry Studio 导入配置
│   └── export.py              # 工具 → Cherry JSON 转换（可选）
│
└── scripts/
    └── run.sh                 # 启动脚本
```

------

## 核心模块说明

### 1. `mcp_server.py`（核心入口）

- 提供 `/mcp` JSON-RPC 接口
- 兼容：
  - `initialize`
  - `tools/list`
  - `tools/call`
  - `ping`
- **不会因 Cherry Studio 接入而改变行为**

👉 **Dify 仍然按原方式接入**

------

### 2. `core/registry.py`（工具注册中心）

职责：

- 自动发现 `tools/` 目录下的 MCP 工具
- 统一维护：
  - Tool name
  - description
  - inputSchema
  - handler 函数

示意逻辑：

```python
TOOL_REGISTRY = {}

def register_tool(tool):
    TOOL_REGISTRY[tool.name] = tool

def list_tools():
    return TOOL_REGISTRY.values()

def call_tool(name, params):
    return TOOL_REGISTRY[name].run(params)
```

------

### 3. `tools/`（MCP 工具目录）

#### 每个工具一个文件

以 `read_linux_yaml.py` 为例：

```python
class ReadLinuxYAMLTool:
    name = "read_linux_yaml"
    description = "Read Prometheus Linux rule YAML"
    input_schema = {
        "type": "object",
        "properties": {},
        "required": []
    }

    def run(self, params):
        ...
```

**新增工具流程：**

1. 新建文件 `tools/xxx.py`
2. 实现 Tool 类
3. 自动加载，无需改主逻辑

------

### 4. `cherry/cherry_mcp.json`（Cherry Studio 导入文件）

Cherry Studio 使用 **JSON 描述 MCP 工具**，示例：

```json
{
  "name": "linux-yaml-reader",
  "type": "mcp",
  "transport": "http",
  "endpoint": "http://YOUR_SERVER_IP:8000/mcp",
  "tools": [
    {
      "name": "read_linux_yaml",
      "description": "Read Prometheus Linux rule YAML",
      "input_schema": {}
    }
  ]
}
```

📌 **这个文件是 Cherry Studio 唯一需要的东西**

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


~~~
git add .
git commit -m ""
git push origin main
~~~