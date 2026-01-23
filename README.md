# 探索AIOps：MCP Server（兼容 Cherry Studio & Dify）

## 项目简介

本项目是一个 **MCP（Model Context Protocol）Server**，基于 **FastAPI + JSON-RPC 2.0** 实现，优先支持 **Cherry Studio** 的 JSON 导入方式，同时兼容 **Dify 平台** 的 MCP 工具对接。

- **优先支持 Cherry Studio 的 JSON 导入方式**
- **完整兼容 Dify MCP 接入规范**
- **工具（Tools）模块化、可扩展**
- **单一 Server，双平台复用（二合一）**

当前MCP Server可调用mcp工具如下：

- `read_file`：读取指定的系统文件文件（初期测试使用）。

- `prometheus_tools`：基于dify-plugin-prometheus二次开发，实现AI调用Prometheus功能。

- `files_query`：定义可以访问的目录，该目录下所有文件可查看。

- `system_check_tools`：定义一部分常用系统运维命令，AI可调用命令查询系统状态等等。

- `docker_tools`：定义docker相关查询信息，AI可调用命令查询docker容器状态、镜像等。

- `jenkins_tools`：定义Jenkins相关查询信息，AI可调用命令查询jenkins流水线内容及状态等。

- `mysql_query_tools`：MySQL数据库内容调用，并进行AI分析。
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
├── mcp-server.py              # MCP 服务器主入口
├── requirements.txt           # Python 依赖
├── README.md                  # 项目说明（本文档）
├── start_project.sh           # 处理服务启动Python依赖与环境
│
├── systemd_service/
│   └── mcp-server.service     # MCP Server 使用systemd管理启动文件示例
│
├── core/                      # MCP 核心抽象
│   ├── __init__.py
│   ├── api.py                 # API路由定义
│   ├── call_records.py        # 调用记录管理
│   ├── protocol.py            # JSON-RPC / MCP 响应封装
│   ├── registry.py            # Tool 注册与发现
│   ├── state.py               # Server 状态管理
│   └── utils.py               # 通用工具函数
│
├── scripts/
│   └── add_tools.py           # MCP 工具注入.tools_state.json
│
├── tools/                     # MCP 工具目录（重点）
│   ├── __init__.py
│   ├── config.py              # .env 配置文件加载器
│   ├── control_center.py      # MCP 服务控制中心
│   ├── docker_tools.py        # Docker信息查询工具
│   ├── files_query_tools.py   # 文件查询工具
│   ├── jenkins_tools.py       # Jenkins信息查询工具
│   ├── mysql_query_tools.py   # MySQL查询工具
│   ├── prometheus_tools.py    # Prometheus查询工具
│   ├── read_file.py           # 文件读取工具
│   └── system_check_tools.py  # 系统检查工具
│
├── cherry/                    # Cherry Studio 专用
│   └── cherry_mcp.json        # Cherry Studio 导入配置 
│
├── web/                       # Web管理界面
│   ├── static/                # 静态资源
│   └── index.html             # 管理界面入口
│
└── .env.example               # 环境配置示例文件
```

------

## 核心模块说明

本节专注说明项目中所有核心模块，这些模块构成了 MCP 服务器的基础架构，负责处理 API 路由、协议封装、工具注册与调用、状态管理等核心功能。

### 1. core/api.py

**职责**：API路由模块，包含所有Web API端点的定义

- **主要功能**：
  - 注册所有API路由
  - 实现Web管理界面首页
  - 提供服务状态查询接口
  - 实现MCP协议的核心接口（initialize、tools/list、tools/call）
  - 提供工具调用记录查询接口
  - 实现远程连接测试接口
  - 配置文件保存接口

- **设计特点**：
  - 基于FastAPI实现，提供高性能的API服务
  - 支持跨域请求
  - 集成静态文件服务，提供Web管理界面

### 2. core/call_records.py

**职责**：调用记录管理模块，用于记录和查询工具调用记录

- **主要功能**：
  - 记录工具调用的详细信息（时间、客户端IP、工具名称、状态、处理时间等）
  - 提供调用记录的分页查询功能
  - 实现调用统计功能（总调用次数、成功率、按工具统计等）
  - 自动保存调用记录到文件
  - 限制最大记录数量，避免占用过多磁盘空间

- **设计特点**：
  - 内存与文件双重存储，兼顾性能和持久性
  - 自动清理旧记录，保持系统资源占用稳定
  - 支持高效的分页查询

### 3. core/protocol.py

**职责**：JSON-RPC协议封装模块，提供响应和错误处理

- **主要功能**：
  - 封装JSON-RPC 2.0协议的成功响应格式
  - 封装JSON-RPC 2.0协议的错误响应格式
  - 提供统一的响应构造函数

- **设计特点**：
  - 严格遵循JSON-RPC 2.0协议规范
  - 与业务逻辑完全分离，便于维护和扩展
  - 支持自定义错误码

### 4. core/registry.py

**职责**：工具注册与管理模块，负责工具的加载、注册和调用

- **主要功能**：
  - 自动发现和加载tools目录下的所有工具
  - 注册工具及其别名
  - 管理工具的启用/禁用状态
  - 提供工具列表查询功能
  - 实现工具调用逻辑
  - 支持从.env文件加载工具配置
  - 持久化工具状态到文件

- **设计特点**：
  - 工具与核心完全解耦，便于扩展
  - 支持多种工具启用方式（环境变量、配置文件、运行时API）
  - 自动处理参数归一化，兼容不同平台的调用格式
  - 支持工具别名，提高兼容性

- **工具对象约定**：
  - 必需：
    - `name`（str）：主名，用于注册与发现
    - `run(self, params: dict) -> str`：执行入口
  - 可选：
    - `description`（str）：用于tools/list展示
    - `input_schema`（dict）：JSON Schema，用于描述参数结构
    - `aliases`（list[str]）：允许工具被多个名称调用

### 5. core/state.py

**职责**：服务器状态管理模块，保存全局运行时状态

- **主要功能**：
  - 保存服务器初始化状态
  - 提供全局状态访问接口

- **设计特点**：
  - 轻量级设计，只保存必要的全局状态
  - 线程安全，支持多线程访问

### 6. core/utils.py

**职责**：通用工具函数模块，包含工具调用计数器和客户端IP获取等功能

- **主要功能**：
  - 实现工具调用计数器，记录每个工具的调用次数
  - 提供客户端IP地址获取功能
  - 支持工具调用计数的持久化存储

- **设计特点**：
  - 提供通用功能，避免代码重复
  - 自动处理文件读写异常，提高系统健壮性

## 工具开发规范

### 工具对象骨架

```python
class ExampleTool:
    name = "example"  # 工具主名，唯一标识符
    aliases = ["example_alt"]  # 可选别名列表
    description = "示例工具"  # 工具描述
    input_schema = {"type":"object", "properties": {}}  # 参数JSON Schema

    def run(self, params):
        # 工具执行逻辑
        # params：归一化后的参数字典
        # 返回：字符串结果（Markdown或普通文本）
        return "执行结果"

# 模块级导出，load_tools()会自动注册这个tool对象
tool = ExampleTool()
```

### 开发注意事项

1. **命名规范**：工具名称应简洁明了，避免使用特殊字符
2. **返回类型**：run方法必须返回字符串，支持Markdown格式
3. **参数处理**：params已由registry归一化，直接使用即可
4. **错误处理**：内部异常应捕获并返回友好的错误信息
5. **性能考虑**：避免长时间阻塞操作，考虑异步处理
6. **安全性**：严格验证输入参数，防止安全漏洞
7. **日志记录**：重要操作应记录日志，便于调试和监控

## 配置文件说明

### .env文件

项目支持通过.env文件配置各项参数，主要包括：

- **工具启用配置**：以`TOOL_<TOOL_NAME>=1`格式启用工具
- **远程执行配置**：控制是否允许远程命令执行
- **Prometheus配置**：Prometheus服务器地址和认证信息
- **文件查询配置**：可访问的文件根目录
- **SSH配置**：远程连接的SSH参数
- **Jenkins配置**：Jenkins服务器地址和认证信息
- **MySQL配置**：MySQL数据库连接信息

### .tool_state.json文件

自动生成的工具状态文件，用于持久化工具的启用状态。格式为：

```json
{
  "enabled": ["tool1", "tool2", ...]
}
```

### cherry_mcp.json文件

Cherry Studio专用的配置文件，用于快速导入MCP Server配置。

------

## 工作流程对比

### Cherry Studio 调用链（优先支持）

```text
Cherry Studio
  → 导入 cherry/cherry_mcp.json 配置文件
  → 直接调用 /mcp tools/call
```

### Dify 调用链（兼容支持）

```text
Dify
  → /mcp
    → initialize
    → tools/list
    → tools/call
```

✔ **同一个 Server**
✔ **同一套工具**
✔ **零重复实现**

------

## 启动方式

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动服务

```bash
python mcp-server.py
```

默认监听：

```text
http://0.0.0.0:8000/mcp
```

## 使用说明

### Cherry Studio 配置（优先支持）

1. 在 Cherry Studio 中导入 `cherry/cherry_mcp.json` 配置文件
2. 配置文件自动指向 MCP Server 地址
3. 直接调用工具即可，无需额外初始化步骤

### Dify 配置（兼容支持）

1. 在 Dify 平台中配置 MCP Server 地址
2. 按照 Dify MCP 协议调用接口
3. 需要先调用 `initialize` 方法，再调用 `tools/list` 和 `tools/call`

## 注意事项

- **SSH远程连接功能**：当前SSH远程连接功能暂时无法使用，正在修复中。
- 所有工具默认关闭，需要在 `.env` 文件中配置启用。
- 建议只在安全的内网环境中使用，特别是命令执行相关工具。
- 配置文件修改后需要重启服务才能生效。
- 详细的工具使用说明请查看 `tools/README.md` 文件。

------