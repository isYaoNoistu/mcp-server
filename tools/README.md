# MCP 可执行命令清单





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







# MCP可调用清单
