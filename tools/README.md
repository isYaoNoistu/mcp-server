# MCP Server 测试指引

说明（重要）
- 在使用任何 tools/list 或 tools/call 之前，必须先对 MCP Server 调用 `initialize` 方法（一次就行，服务重启后需要再次调用）。
- 如果收到错误 "Server not initialized"，表示尚未执行 initialize。

前置条件
1. 确保 mcp-server 已启动并监听（例如：`http://127.0.0.1:8000/mcp`）。
3. 若遇到 “Failed to parse request JSON” 错误，通常是 JSON 格式或引号问题，见下面“调试提示”。

## 一、检查服务与健康
目标：确认服务已启动并能访问
验证点：HTTP 200 /health 返回 { "status":"ok", "initialized": <bool> }

Linux (curl):
```bash
curl -sS http://127.0.0.1:8000/health | jq .
```

## 二、初始化（必须步骤）
目标：调用 JSON-RPC initialize 方法，标记服务为已初始化
说明：只需调用一次（每次服务重启后需重新调用）

Linux (curl):
```bash
curl -sS -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | jq .
```

验证点（中文）：
- 返回应是 JSON-RPC 的响应，表示初始化成功（protocolVersion、capabilities 等信息）。
- 初始化后，`/health` 中的 `initialized` 会为 true（取决实现）。

## 三、查看已启用工具（tools/list）
目标：获取当前“已启用”工具列表（前端展示用）
说明：此调用要要求服务已初始化

Linux (curl):
```bash
curl -sS -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' | jq .
```

验证点（中文）：
- 输出包含 "tools" 字段，里面是被启用工具的数组（每项含 name/description/inputSchema）。
- 被 .env 或 control_center 禁用的工具不应出现在此列表。

## 四、列出所有已注册工具及启用状态（control_center action=list）
目标：管理员查看全部工具及 enabled 状态（包含禁用的）
说明：control_center 本身必须是启用状态，否则无法调用

Linux (curl):
```bash
curl -sS -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":3,"method":"tools/call",
    "params": {"name":"control_center","arguments":{"action":"list"}}
  }' | jq .
```

验证点（中文）：
- 返回 Markdown 文本（content[0].text）或 JSON，内含每个工具的 enabled 状态（true/false）。
- 可用作管理员查看/同步 .env 与 .tool_state.json 状态。

## 五、通过 control_center 启用/禁用工具（示例）
目标：演示 enable/disable 并即时生效（写入 .tool_state.json）

禁用示例（disable container_check）Linux:
```bash
curl -sS -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":4,"method":"tools/call",
    "params": {"name":"control_center","arguments":{"action":"disable","name":"container_check"}}
  }' | jq .
```

验证点（中文）：
- 返回表示禁用成功（例如 "Disabled tool 'container_check': True"）。
- 立即再执行 tools/list，确认对应工具已从列表移除。

## 六、调用具体工具示例（prometheus）
说明：确保 prometheus 在 .env 已配置并启用

Linux (curl):
```bash
curl -sS -X POST http://127.0.0.1:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":5,"method":"tools/call",
    "params": {"name":"prometheus","arguments":{"query":"up","time_range":"5m","step":"30s"}}
  }' | jq .
```

验证点（中文）：
- 若 Prometheus 可达并启用：返回的 content[0].text 应包含指标结果（Markdown 表格或文本）。
- 若工具被禁用：返回 JSON-RPC 错误，message 中通常写 "Tool not enabled" 或 "Tool not found"。
- 若配置错误或网络问题：工具返回以 `Error:` 开头的字符串说明。

## 七、查看 .tool_state.json（持久化文件）
目标：确认 enable/disable 操作写入或 .env 覆盖后的最终状态

Linux:
```bash
cat .tool_state.json | jq .
```

验证点（中文）：
- JSON 中 "enabled" 数组应该反映当前已启用工具的 canonical names。

## 附：建议的测试顺序（最少步骤）

1. 启动 mcp-server 或确认已运行。
2. health 检查（/health）。
3. initialize 调用（必须）。
4. tools/list（确认可用工具）。
5. control_center list（确认 enabled 状态）。
6. 通过 control_center 禁用/启用某工具并再次验证 tools/list。
7. 调用某具体工具（如 prometheus）验证返回结果。
8. 检查 .tool_state.json 持久化。



# MCP 可执行命令清单

docker_tools、system_ckeck



## docker_tools:

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



## system_check:



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





# 新增工具流程

回答是的，你的理解基本正确。下面把整个流程、注意事项、测试步骤和最佳实践整理成一份清晰的指南（中文），方便你下次新增工具时参考并避免常见坑。

一、总体流程（新增工具 -> 启用/禁用）
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
     - 调用 tools/call name=control_center, arguments={"action":"enable","name":"<tool_name>"}
     - control_center 会把变更写入 .tool_state.json（持久化），立即生效。
6. 验证：用 tools/list 查看当前“已启用”的工具；或用 control_center action=list 查看所有工具及 enabled 状态。

二、.env 与 .tool_state.json 的优先级与行为
- .tool_state.json：runtime 的持久化存储（control_center enable/disable 会写入它）。
- .env：启动时的“声明式”配置。load_tools() 在导入所有工具并从 .tool_state.json 恢复后，会应用 .env 的覆盖规则（.env 优先于 .tool_state.json），并把结果持久化回 .tool_state.json。
- 启动顺序与效果：
  - 修改 .env 后需要重启 mcp-server 才会被读取并覆盖当前状态（除非你使用 control_center 的 apply_env 功能来在运行时重新读取并应用 .env）。
  - 使用 control_center 修改会立即生效并写入 .tool_state.json，但下次重启若 .env 对同一工具有设置，会以 .env 为准覆盖该值。
- 建议：
  - 想要“长期默认状态”就同步修改 .env（部署时由运维设置）；临时调整用 control_center（例如排障时）。

三、新增工具时的注意事项（避免常见问题）
1. name 唯一：确保 tool.name 与其它已存在工具不冲突（包含大小写一致性）。
2. 返回类型：run 必须返回字符串（Markdown 或错误字符串）。否则 mcp-server 会把它放进 content.text 导致类型校验错误。
3. input_schema：推荐提供，便于在 tools/list 与前端展示参数说明。
4. aliases：如需兼容多种调用名可设置 aliases 列表。
5. 模块导出：必须有 module-level `tool` 变量（示例：tool = ExampleTool()）。
6. 如果工具依赖外部二进制（如 docker/iostat），建议在 run 中检查二进制是否存在，返回友好错误信息。
7. 若工具需要读取仓库配置，使用 tools.config.get() 读取 .env 配置。

四、测试步骤（新增工具后的验证）
假设新工具 canonical name 为 example_tool：
1. 把文件放到 tools/example_tool.py 并提交。
2. （声明式启动）编辑 .env，加入：
   TOOL_EXAMPLE_TOOL=1
   或 TOOL_EXAMPLE=1（取决于 canonical name）
3. 重启 mcp-server。
4. 验证：
   - 查看所有已启用工具（tools/list）：
     curl -X POST http://127.0.0.1:8000/mcp -H 'Content-Type: application/json' -d '{
       "jsonrpc":"2.0","id":1,"method":"tools/list","params": {}
     }'
     -> 结果应包含 example_tool。
   - 使用 control_center 查看全部工具状态（包含被禁用的）：
     调用 tools/call name=control_center arguments={"action":"list"}，观察 example_tool 的 enabled 字段。
   - 直接调用新工具：
     curl ... tools/call name=example_tool arguments={"query":...}（根据 input_schema 调用）
   - 查看 .tool_state.json 内容确认已包含 example_tool（或其启用/禁用状态）。

五、如果你不想重启也要用 .env 生效
- 如果不想重启服务，可用 control_center 的 apply_env（若你已加上此功能）在运行时重新读取 .env 并应用，这会写回 .tool_state.json 并立即生效：
  调用 tools/call name=control_center arguments={"action":"apply_env"}。

六、示例模板（新增工具文件示例）
把下面模板按需修改并保存为 tools/example_tool.py：

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

