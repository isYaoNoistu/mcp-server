# MCP Server 工具说明

## 工具概述

MCP Server 提供了多种工具，用于实现不同的功能。所有工具默认关闭，需要在 .env 文件中配置启用。

## 工具列表及说明

### 1. read_file
- **作用**：读取指定的系统文件（初期测试使用）
- **使用语法**：
  ```json
  {
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params": {"name":"read_file","arguments":{"file_path":"/path/to/file"}}
  }
  ```

### 2. prometheus_tools
- **作用**：基于 dify-plugin-prometheus 二次开发，实现 AI 调用 Prometheus 功能
- **使用语法**：
  ```json
  {
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params": {"name":"prometheus","arguments":{"query":"up","time_range":"5m","step":"30s"}}
  }
  ```

### 3. files_query
- **作用**：定义可以访问的目录，该目录下所有文件可查看
- **使用语法**：
  ```json
  {
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params": {"name":"files_query","arguments":{"query":"file_content","path":"/path/to/directory"}}
  }
  ```

### 4. system_check_tools
- **作用**：定义一部分常用系统运维命令，AI 可调用命令查询系统状态等
- **使用语法**：
  ```json
  {
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params": {"name":"system_check_tools","arguments":{"command":"top","lines":20}}
  }
  ```

### 5. docker_tools
- **作用**：定义 docker 相关查询信息，AI 可调用命令查询 docker 容器状态、镜像等
- **使用语法**：
  ```json
  {
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params": {"name":"docker_tools","arguments":{"action":"list","command":"ps"}}
  }
  ```

### 6. jenkins_tools
- **作用**：定义 Jenkins 相关查询信息，AI 可调用命令查询 jenkins 流水线内容及状态等
- **使用语法**：
  ```json
  {
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params": {"name":"jenkins_tools","arguments":{"action":"get_job_status","job_name":"example-job"}}
  }
  ```

### 7. mysql_query_tools
- **作用**：MySQL 数据库内容调用，并进行 AI 分析
- **使用语法**：
  ```json
  {
    "jsonrpc":"2.0","id":1,"method":"tools/call",
    "params": {"name":"mysql_query_tools","arguments":{"query":"SELECT * FROM users LIMIT 10"}}
  }
  ```

## 工具详细命令清单

### docker_tools 命令清单

|          命令标识          |              对应的原生 Docker 命令              |                         功能说明                         |                   所需参数                    |
| :------------------------: | :----------------------------------------------: | :------------------------------------------------------: | :-------------------------------------------: |
|      **原有兼容命令**      |                                                  |                                                          |                                               |
|        `docker_ps`         |       `docker ps -a --format "{{json .}}"`       |  列出所有容器（包含已停止的），输出每行 JSON 格式的数据  |                      无                       |
|       `docker_stats`       | `docker stats --no-stream --format "{{json .}}"` |   获取容器资源使用统计快照（CPU、内存等），非流式输出    |                      无                       |
|      `docker_images`       |     `docker images -a --format "{{json .}}"`     | 列出所有镜像（包含中间层镜像），输出每行 JSON 格式的数据 |                      无                       |
|      **新增扩展命令**      |                                                  |                                                          |                                               |
| `docker_container_inspect` |           `docker inspect <container>`           |      根据容器名称 / ID 查看容器的详细配置和状态信息      |       `container`（必填，容器名 / ID）        |
|   `docker_image_inspect`   |             `docker inspect <image>`             |       根据镜像名称 / ID 查看镜像的详细配置和元数据       |         `image`（必填，镜像名 / ID）          |
|  `docker_container_logs`   |      `docker logs --tail <num> <container>`      |            获取容器日志，默认返回最后 100 行             | `container`（必填）、`tail`（可选，默认 100） |
|     `docker_networks`      |    `docker network ls --format "{{json .}}"`     |      列出所有 Docker 网络，输出每行 JSON 格式的数据      |                      无                       |
|  `docker_network_inspect`  |        `docker network inspect <network>`        |       根据网络名称 / ID 查看 Docker 网络的详细配置       |        `network`（必填，网络名 / ID）         |
|      `docker_volumes`      |     `docker volume ls --format "{{json .}}"`     |       列出所有 Docker 卷，输出每行 JSON 格式的数据       |                      无                       |
|  `docker_volume_inspect`   |         `docker volume inspect <volume>`         |         根据卷名称 / ID 查看 Docker 卷的详细配置         |          `volume`（必填，卷名 / ID）          |

### system_check_tools 命令清单

|               工具类别               |     命令标识     |                   对应原生系统命令                   |                   功能说明                   |                        所需参数                         |
| :----------------------------------: | :--------------: | :--------------------------------------------------: | :------------------------------------------: | :-----------------------------------------------------: |
|  **system_status**（基础系统信息）   |      uname       |                      `uname -a`                      |   查询内核版本、系统架构、主机名等基础信息   |                           无                            |
|                                      |     hostname     |                    `hostname -f`                     |             查询服务器完整主机名             |                           无                            |
|                                      |   lsb_release    |                   `lsb_release -a`                   | 查询 Linux 发行版版本信息（如 Ubuntu 版本）  |                           无                            |
|                                      |      uptime      |                     `uptime -p`                      | 以易读格式显示系统运行时长（如 "up 5 days"） |                           无                            |
| **process_check**（进程 / 资源检查） |       top        |                    `top -bn1 -c`                     |      单次快照显示所有进程的资源使用情况      |        lines（可选 int，默认 30，限制输出行数）         |
|                                      |      ps_cpu      |       `ps -eo pid,ppid,pcpu,cmd --sort=-pcpu`        |      按 CPU 使用率降序显示进程（TOP N）      |        limit（可选 int，默认 20，限制输出行数）         |
|                                      |      ps_mem      |        `ps -eo pid,ppid,rss,cmd --sort=-rss`         |   按内存（RSS）使用率降序显示进程（TOP N）   |        limit（可选 int，默认 20，限制输出行数）         |
|                                      |      mpstat      |                 `mpstat -P ALL 1 1`                  |    查看每个 CPU 核心的使用率（采样 1 次）    |                           无                            |
|                                      |       free       |                      `free -h`                       |   人类可读格式显示内存 / 交换分区使用情况    |                           无                            |
|                                      |      vmstat      |                     `vmstat 1 2`                     |   虚拟内存统计快照（采样 2 次，间隔 1 秒）   |                           无                            |
| **service_check**（服务 / 日志检查） | systemctl_failed | `systemctl list-units --type=service --state=failed` |         列出所有失败的 systemd 服务          |                           无                            |
|                                      | systemctl_status |             `systemctl status <service>`             |       查看指定 systemd 服务的详细状态        |      service（必填 str，服务名，如 nginx.service）      |
|                                      |    ps_defunct    |              `ps -eo pid,ppid,stat,cmd`              |        筛选显示僵尸（Z/defunct）进程         |                           无                            |
|                                      |      pstree      |                     `pstree -p`                      |         树形结构显示进程（包含 PID）         |                           无                            |
|                                      |    journalctl    |        `journalctl -n 50 --no-pager -o json`         |     查看最后 50 条系统日志（JSON 格式）      |                           无                            |
|                                      |       tail       |               `tail -n <lines> <path>`               |          查看文件末尾指定行数的内容          | path（必填 str，文件路径）、lines（可选 int，默认 100） |

## 测试使用语法

### 1. 检查服务与健康
目标：确认服务已启动并能访问

```bash
curl -sS http://127.0.0.1:8000/health | jq .
```

### 2. 初始化（必须步骤）
目标：调用 JSON-RPC initialize 方法，标记服务为已初始化

```bash
curl -sS -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | jq .
```

### 3. 查看已启用工具
目标：获取当前“已启用”工具列表

```bash
curl -sS -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' | jq .
```

### 4. 列出所有已注册工具及启用状态
目标：管理员查看全部工具及 enabled 状态（包含禁用的）

```bash
curl -sS -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":3,"method":"tools/call",
    "params": {"name":"control_center","arguments":{"action":"list"}}
  }' | jq .
```

### 5. 通过 control_center 启用/禁用工具
目标：演示 enable/disable 并即时生效

禁用示例：
```bash
curl -sS -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":4,"method":"tools/call",
    "params": {"name":"control_center","arguments":{"action":"disable","name":"container_check"}}
  }' | jq .
```

启用示例：
```bash
curl -sS -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":5,"method":"tools/call",
    "params": {"name":"control_center","arguments":{"action":"enable","name":"container_check"}}
  }' | jq .
```

### 6. 调用具体工具示例

Prometheus 工具示例：
```bash
curl -sS -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":6,"method":"tools/call",
    "params": {"name":"prometheus","arguments":{"query":"up","time_range":"5m","step":"30s"}}
  }' | jq .
```

Docker 工具示例：
```bash
curl -sS -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":7,"method":"tools/call",
    "params": {"name":"docker_tools","arguments":{"action":"run","command":"ps"}}
  }' | jq .
```

System Check 工具示例：
```bash
curl -sS -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":8,"method":"tools/call",
    "params": {"name":"system_check_tools","arguments":{"command":"top","lines":10}}
  }' | jq .
```

## 注意事项

- **SSH远程连接功能**：当前SSH远程连接功能暂时无法使用，正在修复中。
- 所有工具默认关闭，需要在 .env 文件中配置启用。
- 建议只在安全的内网环境中使用，特别是命令执行相关工具。
- 修改 .env 文件后需要重启 MCP Server 才能生效。
- 使用 control_center 修改工具状态会立即生效并写入 .tool_state.json，但下次重启若 .env 对同一工具有设置，会以 .env 为准覆盖该值。

## 新增工具流程

### 一、总体流程（新增工具 -> 启用/禁用）
1. 在 tools/ 目录新增工具模块文件（例如 tools/example_tool.py）。
2. 在模块内实现工具类并导出 module-level 的 tool 对象：
   - 必需属性/方法：
     - name: str（工具的 canonical name，唯一）
     - run(self, params: dict) -> str（返回字符串，兼容 mcp-server 的 content.text）
   - 可选：aliases（别名列表），description（字符串），input_schema（用于 tools/list 展示）
   - 最后：tool = ExampleTool()
3. 提交代码到仓库并部署（或在本地开发环境重启服务以让 load_tools 重新加载）。
4. 启动/重启 mcp-server（load_tools 会自动扫描 tools/ 并 register_tool(module.tool)）。
5. 启用方式（两选一或组合）：
   - 通过 .env（声明式，启动时生效）
     - 在仓库根 .env 加入 TOOL_<CANONICAL_NAME>=1（或 ENABLE_TOOL_<CANONICAL_NAME>=1 或 大写 CANONICAL_NAME=1）
     - 重启服务以让 .env 在 load_tools 阶段覆盖持久化状态。
   - 或 运行时通过 control_center（即时生效）
     - 调用 tools/call name=control_center arguments={"action":"enable","name":"<tool_name>"}
     - control_center 会把变更写入 .tool_state.json（持久化），立即生效。
6. 验证：用 tools/list 查看当前“已启用”的工具；或用 control_center action=list 查看所有工具及 enabled 状态。

### 二、示例模板（新增工具文件示例）

```python
class ExampleTool:
    name = "example_tool"
    aliases = ["example"]
    description = "示例工具：说明工具用途"
    input_schema = {
        "type":"object",
        "properties": {
            "param": {"type": "string"}
        },
        "required": []
    }

    def run(self, params):
        # params 已由 registry 归一化（可能在 arguments/input/args/parameters 中）
        try:
            p = params.get("param", "default")
            # 返回字符串（Markdown 或普通文本）
            return f"ExampleTool received param={p}"
        except Exception as e:
            return f"Error: {e}"

# 模块级导出，load_tools 会注册这个 tool
tool = ExampleTool()
```