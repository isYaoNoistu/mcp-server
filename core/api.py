# -*- coding: utf-8 -*-
"""API路由模块，包含所有Web API端点的定义"""

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from datetime import datetime, timezone
import logging

from core.call_records import add_call_record, get_call_records as cr_get_call_records, get_call_stats
from core.registry import list_all_tools, enable_tool, disable_tool
from core.protocol import jsonrpc_response, jsonrpc_error
from core.state import MCPServerState
from core.registry import list_tools, call_tool

# 创建日志器实例
logger = logging.getLogger("mcp-server")


def register_routes(app: FastAPI):
    """注册所有API路由"""
    
    # 获取客户端IP的辅助函数
    def get_client_ip(request: Request) -> str:
        """获取客户端IP地址"""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "127.0.0.1"
    
    # Web管理界面路由
    @app.get("/", response_class=HTMLResponse)
    def root():
        """Web管理界面首页"""
        with open("web/index.html", "r", encoding="utf-8") as f:
            return f.read()
    
    # API: 获取服务状态
    @app.get("/api/status")
    def get_status(request: Request):
        """获取服务状态"""
        client_ip = get_client_ip(request)
        start_time = datetime.now()
        
        status = {
            "status": "running" if MCPServerState.initialized else "stopped",
            "initialized": MCPServerState.initialized,
            "version": "2.0.0"
        }
        
        process_time = datetime.now() - start_time
        logger.info(
            "API: Get status", 
            extra={"client_ip": client_ip, "tool_name": "system", "process_time": f"{process_time.total_seconds():.3f}"}
        )
        return status
    
    # API: 获取工具列表
    @app.get("/api/tools")
    def get_tools(request: Request):
        """获取所有工具列表"""
        client_ip = get_client_ip(request)
        start_time = datetime.now()
        
        try:
            # 从工具注册表中获取所有工具，包括启用和禁用的
            all_tools = list_all_tools(include_status=True)
            tool_list = []
            for tool in all_tools:
                # 生成工具ID，将工具名称转换为小写并替换空格为下划线
                tool_id = tool["name"].lower().replace(" ", "_")
                
                tool_list.append({
                    "id": tool_id,
                    "name": tool["name"],
                    "description": tool["description"],
                    "status": tool["enabled"]
                })
            
            process_time = datetime.now() - start_time
            logger.info(
                f"API: Get tools list, count: {len(tool_list)}", 
                extra={"client_ip": client_ip, "tool_name": "system", "process_time": f"{process_time.total_seconds():.3f}"}
            )
            return {"tools": tool_list}
        except Exception as e:
            process_time = datetime.now() - start_time
            logger.error(
                f"API: Get tools list failed: {e}", 
                extra={"client_ip": client_ip, "tool_name": "system", "process_time": f"{process_time.total_seconds():.3f}"}
            )
            return {"tools": []}
    
    # API: 切换工具状态
    @app.post("/api/tools/toggle")
    async def toggle_tool(request: Request):
        """切换工具启用/禁用状态"""
        client_ip = get_client_ip(request)
        start_time = datetime.now()
        
        try:
            body = await request.json()
            tool_id = body.get("toolId")
            enabled = body.get("enabled", True)
            
            # 查找对应的工具名称
            found_tool_name = None
            # 使用list_all_tools获取所有工具，包括启用和禁用的
            all_tools = list_all_tools()
            for tool in all_tools:
                # 比较小写的工具名称和前端传递的toolId
                if tool["name"].lower().replace(" ", "_") == tool_id:
                    found_tool_name = tool["name"]
                    break
            
            if not found_tool_name:
                process_time = datetime.now() - start_time
                logger.error(
                    f"API: Toggle tool - Tool not found: {tool_id}", 
                    extra={"client_ip": client_ip, "tool_name": "system", "process_time": f"{process_time.total_seconds():.3f}"}
                )
                return {
                    "success": False,
                    "message": f"Tool {tool_id} not found",
                    "toolId": tool_id,
                    "enabled": not enabled
                }
            
            # 实际调用工具注册表的方法来切换工具状态
            if enabled:
                # 启用工具
                success = enable_tool(found_tool_name)
            else:
                # 禁用工具
                success = disable_tool(found_tool_name)
            
            process_time = datetime.now() - start_time
            if success:
                # 操作成功，返回新的工具状态
                logger.info(
                    f"API: Toggle tool - {tool_id} {'enabled' if enabled else 'disabled'} successfully", 
                    extra={"client_ip": client_ip, "tool_name": found_tool_name, "process_time": f"{process_time.total_seconds():.3f}"}
                )
                return {
                    "success": True,
                    "message": f"Tool {tool_id} {'enabled' if enabled else 'disabled'} successfully",
                    "toolId": tool_id,
                    "enabled": enabled
                }
            else:
                # 操作失败，工具不存在
                logger.error(
                    f"API: Toggle tool - Failed to toggle {tool_id}", 
                    extra={"client_ip": client_ip, "tool_name": found_tool_name, "process_time": f"{process_time.total_seconds():.3f}"}
                )
                return {
                    "success": False,
                    "message": f"Failed to toggle tool {tool_id}",
                    "toolId": tool_id,
                    "enabled": not enabled
                }
        except Exception as e:
            process_time = datetime.now() - start_time
            logger.error(
                f"API: Toggle tool - Error: {e}", 
                extra={"client_ip": client_ip, "tool_name": "system", "process_time": f"{process_time.total_seconds():.3f}"}
            )
            return {
                "success": False,
                "message": f"Error toggling tool: {str(e)}",
                "toolId": body.get("toolId") if 'body' in locals() else None,
                "enabled": False
            }
    
    # API: 保存配置
    @app.post("/api/config/save")
    async def save_config(request: Request):
        """保存工具配置"""
        client_ip = get_client_ip(request)
        start_time = datetime.now()
        
        try:
            import os
            import re
            
            body = await request.json()
            
            # 读取现有的.env文件内容
            env_path = ".env"
            env_content = ""
            
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as f:
                    env_content = f.read()
            
            # 远程主机配置字段映射：中文显示名 -> 实际配置项名称
            remote_host_field_map = {
                '允许远程执行(ALLOW_REMOTE_EXEC)': 'ALLOW_REMOTE_EXEC',
                '远程主机IP(REMOTE_HOST_IP)': 'REMOTE_HOST_IP',
                'SSH端口(REMOTE_SSH_PORT)': 'REMOTE_SSH_PORT',
                'SSH用户名(REMOTE_SSH_USER)': 'REMOTE_SSH_USER',
                'SSH密码(REMOTE_SSH_PASSWORD)': 'REMOTE_SSH_PASSWORD',
                'SSH密钥(REMOTE_SSH_KEY)': 'REMOTE_SSH_KEY',
                '认证方式(REMOTE_AUTH_METHOD)': 'REMOTE_AUTH_METHOD'
            }
            
            # 根据配置数据更新.env文件内容
            for section, fields in body.items():
                for field, value in fields.items():
                    # 生成配置项名称，根据不同工具进行特殊处理
                    config_key = ""
                    
                    # 特殊处理：为不同工具映射正确的配置项名称
                    if section == "prometheus":
                        if field == "url":
                            config_key = "PROMETHEUS_API_URL"
                        else:
                            config_key = f"PROMETHEUS_{field.upper()}"
                    elif section == "files_query":
                        if field == "root":
                            config_key = "FILES_ROOT"
                        elif field == "max_bytes":
                            config_key = "FILE_READ_MAX_BYTES"
                    elif section == "mysql":
                        config_key = f"MYSQL_DEFAULT_{field.upper()}"
                    elif section == "jenkins":
                        config_key = f"JENKINS_{field.upper()}"
                    elif section == "remote_host":
                        # 远程主机配置：使用映射将中文显示名转换为实际配置项名称
                        config_key = remote_host_field_map.get(field, field.upper())
                    else:
                        # 默认生成规则
                        config_key = f"{section.upper()}_{field.upper()}"
                    
                    # 替换或添加配置项
                    pattern = f"^{config_key}=.*$"  # 正则表达式匹配配置项
                    if re.search(pattern, env_content, re.MULTILINE):
                        # 替换现有配置项
                        env_content = re.sub(pattern, f"{config_key}={value}", env_content, flags=re.MULTILINE)
                    else:
                        # 添加新的配置项
                        env_content += f"\n{config_key}={value}"
            
            # 保存更新后的.env文件
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(env_content)
            
            # 清除配置缓存，确保下次读取时重新加载
            from tools.config import clear_cache
            clear_cache()
            
            process_time = datetime.now() - start_time
            logger.info(
                "API: Save config successful", 
                extra={"client_ip": client_ip, "tool_name": "system", "process_time": f"{process_time.total_seconds():.3f}"}
            )
            return {
                "success": True,
                "message": "配置保存成功",
                "config": body
            }
        except Exception as e:
            process_time = datetime.now() - start_time
            logger.error(
                f"API: Save config failed: {e}", 
                extra={"client_ip": client_ip, "tool_name": "system", "process_time": f"{process_time.total_seconds():.3f}"}
            )
            return {
                "success": False,
                "message": f"配置保存失败: {str(e)}",
                "config": body if 'body' in locals() else {}
            }
    
    # API: 获取系统信息
    @app.get("/api/system")
    def get_system_info(request: Request):
        """获取系统信息"""
        client_ip = get_client_ip(request)
        start_time = datetime.now()
        
        import platform
        import os
        
        system_info = {
            "service_version": "2.0.0",
            "python_version": platform.python_version(),
            "os": platform.system(),
            "os_version": platform.version(),
            "hostname": platform.node(),
            "cpu_usage": 0,  # 暂时返回0，实际使用中可以添加psutil依赖
            "memory_usage": 0,  # 暂时返回0，实际使用中可以添加psutil依赖
            "disk_usage": 0,  # 暂时返回0，实际使用中可以添加psutil依赖
            "uptime": 0  # 暂时返回0，实际使用中可以添加psutil依赖
        }
        
        process_time = datetime.now() - start_time
        logger.info(
            "API: Get system info", 
            extra={"client_ip": client_ip, "tool_name": "system", "process_time": f"{process_time.total_seconds():.3f}"}
        )
        return system_info
    
    # API: 测试远程主机连接
    @app.post("/api/config/test-remote-connection")
    async def test_remote_connection(request: Request):
        """测试远程主机连接"""
        client_ip = get_client_ip(request)
        start_time = datetime.now()
        
        try:
            body = await request.json()
            
            # 提取配置信息
            remote_host_field_map = {
                '允许远程执行(ALLOW_REMOTE_EXEC)': 'ALLOW_REMOTE_EXEC',
                '远程主机IP(REMOTE_HOST_IP)': 'REMOTE_HOST_IP',
                'SSH端口(REMOTE_SSH_PORT)': 'REMOTE_SSH_PORT',
                'SSH用户名(REMOTE_SSH_USER)': 'REMOTE_SSH_USER',
                'SSH密码(REMOTE_SSH_PASSWORD)': 'REMOTE_SSH_PASSWORD',
                'SSH密钥(REMOTE_SSH_KEY)': 'REMOTE_SSH_KEY',
                '认证方式(REMOTE_AUTH_METHOD)': 'REMOTE_AUTH_METHOD'
            }
            
            # 转换配置字段
            config = {}
            for field, value in body.items():
                config_key = remote_host_field_map.get(field, field)
                config[config_key] = value
            
            # 检查必要的配置项
            if not config.get('REMOTE_HOST_IP'):
                return {
                    "success": False,
                    "message": "远程主机IP不能为空"
                }
            
            if not config.get('REMOTE_SSH_USER'):
                return {
                    "success": False,
                    "message": "SSH用户名不能为空"
                }
            
            # 获取连接参数
            host = config.get('REMOTE_HOST_IP')
            port = int(config.get('REMOTE_SSH_PORT', 22))
            username = config.get('REMOTE_SSH_USER')
            auth_method = config.get('REMOTE_AUTH_METHOD', 'password')
            password = config.get('REMOTE_SSH_PASSWORD', '')
            ssh_key = config.get('REMOTE_SSH_KEY', '')
            
            # 尝试建立SSH连接
            import paramiko
            import io
            
            ssh = paramiko.SSHClient()
            # 自动添加未知主机密钥
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            try:
                if auth_method == 'password':
                    # 使用密码认证
                    ssh.connect(hostname=host, port=port, username=username, password=password, timeout=5)
                else:
                    # 使用密钥认证
                    if not ssh_key:
                        return {
                            "success": False,
                            "message": "SSH密钥不能为空"
                        }
                    
                    # 将密钥字符串转换为RSAKey对象
                    key = paramiko.RSAKey.from_private_key(io.StringIO(ssh_key))
                    ssh.connect(hostname=host, port=port, username=username, pkey=key, timeout=5)
                
                # 执行简单命令测试连接
                stdin, stdout, stderr = ssh.exec_command('echo "test"', timeout=5)
                output = stdout.read().decode('utf-8').strip()
                
                ssh.close()
                
                if output == 'test':
                    process_time = datetime.now() - start_time
                    logger.info(
                        f"API: Test remote connection successful", 
                        extra={"client_ip": client_ip, "tool_name": "system", "process_time": f"{process_time.total_seconds():.3f}"}
                    )
                    return {
                        "success": True,
                        "message": "连接成功"
                    }
                else:
                    return {
                        "success": False,
                        "message": "连接测试失败: 命令执行结果不符合预期"
                    }
            except paramiko.AuthenticationException:
                ssh.close()
                return {
                    "success": False,
                    "message": "连接失败: 认证失败，请检查用户名和密码/密钥"
                }
            except paramiko.SSHException as e:
                ssh.close()
                return {
                    "success": False,
                    "message": f"连接失败: SSH错误 - {str(e)}"
                }
            except TimeoutError:
                ssh.close()
                return {
                    "success": False,
                    "message": "连接失败: 连接超时，请检查主机IP和端口"
                }
            except Exception as e:
                ssh.close()
                return {
                    "success": False,
                    "message": f"连接失败: {str(e)}"
                }
        except Exception as e:
            process_time = datetime.now() - start_time
            logger.error(
                f"API: Test remote connection failed: {e}", 
                extra={"client_ip": client_ip, "tool_name": "system", "process_time": f"{process_time.total_seconds():.3f}"}
            )
            return {
                "success": False,
                "message": f"测试失败: {str(e)}"
            }
    
    # API: 获取工具配置
    @app.get("/api/config/load")
    def load_config(request: Request):
        """获取当前工具配置"""
        client_ip = get_client_ip(request)
        start_time = datetime.now()
        
        try:
            from tools.config import get as cfg_get
            
            # 获取当前配置
            config = {}
            
            # 从.env中读取各个工具的配置
            for tool in ['prometheus', 'mysql', 'jenkins', 'files_query', 'remote_host']:
                config[tool] = {}
                
                if tool == 'prometheus':
                    config[tool]['url'] = cfg_get('PROMETHEUS_API_URL') or 'http://127.0.0.1:9090'
                    config[tool]['username'] = cfg_get('PROMETHEUS_USERNAME') or ''
                    config[tool]['password'] = cfg_get('PROMETHEUS_PASSWORD') or ''
                elif tool == 'mysql':
                    config[tool]['host'] = cfg_get('MYSQL_DEFAULT_HOST') or '127.0.0.1'
                    config[tool]['port'] = cfg_get('MYSQL_DEFAULT_PORT') or '3306'
                    config[tool]['user'] = cfg_get('MYSQL_DEFAULT_USER') or 'root'
                    config[tool]['password'] = cfg_get('MYSQL_DEFAULT_PASSWORD') or 'password'
                elif tool == 'jenkins':
                    config[tool]['url'] = cfg_get('JENKINS_URL') or 'http://127.0.0.1:8080'
                    config[tool]['username'] = cfg_get('JENKINS_USERNAME') or ''
                    config[tool]['token'] = cfg_get('JENKINS_TOKEN') or ''
                    config[tool]['timeout'] = cfg_get('JENKINS_TIMEOUT') or '30'
                    config[tool]['console_max_bytes'] = cfg_get('JENKINS_CONSOLE_MAX_BYTES') or '204800'
                elif tool == 'files_query':
                    config[tool]['root'] = cfg_get('FILES_ROOT') or 'files'
                    config[tool]['max_bytes'] = cfg_get('FILE_READ_MAX_BYTES') or '204800'
                elif tool == 'remote_host':
                    # 远程主机配置：简化为单个主机配置
                    config[tool]['允许远程执行(ALLOW_REMOTE_EXEC)'] = cfg_get('ALLOW_REMOTE_EXEC') or 'false'
                    config[tool]['远程主机IP(REMOTE_HOST_IP)'] = cfg_get('REMOTE_HOST_IP') or ''
                    config[tool]['SSH端口(REMOTE_SSH_PORT)'] = cfg_get('REMOTE_SSH_PORT') or '22'
                    config[tool]['SSH用户名(REMOTE_SSH_USER)'] = cfg_get('REMOTE_SSH_USER') or ''
                    config[tool]['SSH密码(REMOTE_SSH_PASSWORD)'] = cfg_get('REMOTE_SSH_PASSWORD') or ''
                    config[tool]['SSH密钥(REMOTE_SSH_KEY)'] = cfg_get('REMOTE_SSH_KEY') or ''
                    config[tool]['认证方式(REMOTE_AUTH_METHOD)'] = cfg_get('REMOTE_AUTH_METHOD') or 'password'
            
            process_time = datetime.now() - start_time
            logger.info(
                "API: Load config successful", 
                extra={"client_ip": client_ip, "tool_name": "system", "process_time": f"{process_time.total_seconds():.3f}"}
            )
            return {
                "success": True,
                "config": config
            }
        except Exception as e:
            process_time = datetime.now() - start_time
            logger.error(
                f"API: Load config failed: {e}", 
                extra={"client_ip": client_ip, "tool_name": "system", "process_time": f"{process_time.total_seconds():.3f}"}
            )
            return {
                "success": False,
                "message": f"加载配置失败: {str(e)}",
                "config": {}
            }
    
    # API: 获取统计数据
    @app.get("/api/stats")
    def get_stats(request: Request):
        """获取服务统计数据"""
        client_ip = get_client_ip(request)
        start_time = datetime.now()
        
        # 使用核心模块中的get_call_stats函数获取统计数据
        stats = get_call_stats()
        
        process_time = datetime.now() - start_time
        logger.info(
            "API: Get stats", 
            extra={"client_ip": client_ip, "tool_name": "system", "process_time": f"{process_time.total_seconds():.3f}"}
        )
        return stats
    
    # API: 获取调用记录
    @app.get("/api/call-records")
    def get_call_records(request: Request, limit: int = 100, offset: int = 0):
        """获取工具调用记录"""
        client_ip = get_client_ip(request)
        start_time = datetime.now()
        
        # 使用核心模块中的get_call_records函数获取记录
        result = cr_get_call_records(limit=limit, offset=offset)
        
        process_time = datetime.now() - start_time
        logger.info(
            f"API: Get call records, limit: {limit}, offset: {offset}, total: {result['total']}", 
            extra={"client_ip": client_ip, "tool_name": "system", "process_time": f"{process_time.total_seconds():.3f}"}
        )
        return result
    
    # API: 服务健康检查接口
    @app.get("/health")
    def health(request: Request):
        """服务健康检查接口"""
        client_ip = get_client_ip(request)
        start_time = datetime.now()
        
        health_status = {
            "status": "ok",  # 服务运行状态
            "initialized": MCPServerState.initialized  # 服务初始化状态
        }
        
        process_time = datetime.now() - start_time
        logger.info(
            "Health check", 
            extra={"client_ip": client_ip, "tool_name": "system", "process_time": f"{process_time.total_seconds():.3f}"}
        )
        return health_status
    
    # API: MCP核心请求处理接口
    @app.post("/mcp")
    async def mcp_handler(request: Request):
        """MCP核心请求处理接口，接收并处理所有JSON-RPC协议请求"""
        # 获取客户端IP
        client_ip = get_client_ip(request)
        
        # 记录请求开始时间
        start_time = datetime.now()
        
        # 尽量在入口处捕获JSON解析错误，并返回JSON-RPC标准的解析错误
        try:
            # 读取并解析请求体的JSON数据
            body = await request.json()
        except Exception:
            # 计算处理时间
            process_time = datetime.now() - start_time
            # 记录JSON解析失败的警告日志
            logger.warning(
                "Failed to parse request JSON", 
                extra={"client_ip": client_ip, "tool_name": "system", "process_time": f"{process_time.total_seconds():.3f}"}
            )
            # JSON-RPC规范：解析错误时id为null
            return jsonrpc_error(None, -32700, "Parse error: invalid JSON")

        # 提取请求中的方法名和请求ID
        method = body.get("method")
        request_id = body.get("id")

        # 将没有request_id的请求视为通知类请求 -> 返回204无内容响应
        if request_id is None:
            # 计算处理时间
            process_time = datetime.now() - start_time
            logger.info(
                f"Notification received (method={method}) -> 204", 
                extra={"client_ip": client_ip, "tool_name": "system", "process_time": f"{process_time.total_seconds():.3f}"}
            )
            # 可选处理initialized通知（初始化完成通知）
            if method == "notifications/initialized":
                # 标记服务状态为已初始化
                MCPServerState.initialized = True
                logger.info(
                    "Set MCPServerState.initialized = True from notification", 
                    extra={"client_ip": client_ip, "tool_name": "system", "process_time": f"{process_time.total_seconds():.3f}"}
                )
            # 返回204状态码（无内容）
            return Response(status_code=204)

        # 兼容JSON-RPC字段缺失场景：仅当字段存在且不等于"2.0"时才返回版本错误
        if "jsonrpc" in body and body.get("jsonrpc") != "2.0":
            # 计算处理时间
            process_time = datetime.now() - start_time
            logger.warning(
                f"Invalid JSON-RPC version: {body.get('jsonrpc')}", 
                extra={"client_ip": client_ip, "tool_name": "system", "process_time": f"{process_time.total_seconds():.3f}"}
            )
            return jsonrpc_error(request_id, -32600, "Invalid JSON-RPC version")

        # 记录请求的方法名和请求ID
        logger.info(
            f"MCP method: {method}, id: {request_id}", 
            extra={"client_ip": client_ip, "tool_name": "system", "process_time": "0.000"}
        )

        # -------- 处理初始化方法 --------
        if method == "initialize":
            # 标记服务状态为已初始化
            MCPServerState.initialized = True
            # 计算处理时间
            process_time = datetime.now() - start_time
            # 返回初始化成功的JSON-RPC响应
            logger.info(
                "Service initialized", 
                extra={"client_ip": client_ip, "tool_name": "system", "process_time": f"{process_time.total_seconds():.3f}"}
            )
            return jsonrpc_response(request_id, {
                "protocolVersion": "2025-06-18",  # MCP协议版本
                "capabilities": {
                    "tools": {},
                    "roots": {},
                    "logging": {}
                },
                "serverInfo": {  # 服务基本信息
                    "name": "mcp-server",
                    "version": "2.0.0"
                }
            })

        # -------- 生命周期守卫：未初始化则拒绝后续业务请求 --------
        if not MCPServerState.initialized:
            # 计算处理时间
            process_time = datetime.now() - start_time
            logger.warning(
                "Server not initialized", 
                extra={"client_ip": client_ip, "tool_name": "system", "process_time": f"{process_time.total_seconds():.3f}"}
            )
            return jsonrpc_error(request_id, -32002, "Server not initialized")

        # -------- 处理工具列表查询方法 --------
        if method == "tools/list":
            # 构造所有已加载工具的列表并返回
            # 计算处理时间
            process_time = datetime.now() - start_time
            logger.info(
                "Listing tools", 
                extra={"client_ip": client_ip, "tool_name": "system", "process_time": f"{process_time.total_seconds():.3f}"}
            )
            return jsonrpc_response(request_id, {
                "tools": [
                    {
                        "name": t.name,               # 工具名称
                        "description": getattr(t, "description", ""),  # 工具描述（无则为空）
                        "inputSchema": getattr(t, "input_schema", {})  # 工具入参Schema（无则为空）
                    }
                    for t in list_tools()  # 遍历所有已加载的工具
                ]
            })

        # -------- 处理工具调用方法 --------
        if method == "tools/call":
            # 提取请求参数（默认空字典）
            params = body.get("params", {})
            # 提取要调用的工具名称（仅当params为字典时有效）
            tool_name = params.get("name") if isinstance(params, dict) else None
            
            if not tool_name:
                # 计算处理时间
                process_time = datetime.now() - start_time
                logger.error(
                    "Tool name not provided in params", 
                    extra={"client_ip": client_ip, "tool_name": "system", "process_time": f"{process_time.total_seconds():.3f}"}
                )
                return jsonrpc_error(request_id, -32602, "Invalid params: tool name missing")
            
            # 记录详细的工具调用信息
            logger.info(
                f"Tool call: {tool_name}, params: {params}",
                extra={"client_ip": client_ip, "tool_name": tool_name, "process_time": "0.000"}
            )

            try:
                # 调用指定名称的工具并获取结果
                result = call_tool(tool_name, params)
                # 计算处理时间
                process_time = datetime.now() - start_time
                process_time_seconds = process_time.total_seconds()
                # 记录工具调用成功
                logger.info(
                    f"Tool call successful: {tool_name}, result_len: {len(str(result))}",
                    extra={"client_ip": client_ip, "tool_name": tool_name, "process_time": f"{process_time_seconds:.3f}"}
                )
                
                # 判断结果是否为错误：如果结果以"Error: "或"No data"开头，则视为错误
                is_error = False
                if isinstance(result, str):
                    result_lower = result.lower()
                    is_error = result_lower.startswith("error:") or result_lower.startswith("no data")
                
                # 添加调用记录
                add_call_record(
                    client_ip=client_ip,
                    tool_name=tool_name,
                    status="error" if is_error else "success",
                    process_time=process_time_seconds,
                    details=str(result)[:200]  # 只保存前200个字符
                )
                
            except KeyError:
                # 计算处理时间
                process_time = datetime.now() - start_time
                process_time_seconds = process_time.total_seconds()
                # 工具不存在时返回JSON-RPC方法未找到错误
                logger.error(
                    f"Tool not found: {tool_name}",
                    extra={"client_ip": client_ip, "tool_name": tool_name, "process_time": f"{process_time_seconds:.3f}"}
                )
                
                # 添加调用记录
                add_call_record(
                    client_ip=client_ip,
                    tool_name=tool_name,
                    status="error",
                    process_time=process_time_seconds,
                    details="Tool not found"
                )
                
                return jsonrpc_error(request_id, -32601, "Tool not found")
            except Exception as e:
                # 计算处理时间
                process_time = datetime.now() - start_time
                process_time_seconds = process_time.total_seconds()
                # 记录工具调用异常
                logger.error(
                    f"Tool call failed: {tool_name}, error: {str(e)}",
                    extra={"client_ip": client_ip, "tool_name": tool_name, "process_time": f"{process_time_seconds:.3f}"}
                )
                
                # 添加调用记录
                add_call_record(
                    client_ip=client_ip,
                    tool_name=tool_name,
                    status="error",
                    process_time=process_time_seconds,
                    details=str(e)
                )
                
                return jsonrpc_error(request_id, -32603, f"Tool execution failed: {str(e)}")

            # 将工具调用结果标准化为Dify期望的内容列表格式
            return jsonrpc_response(request_id, {
                "content": [
                    {"type": "text", "text": result}  # 结果以文本类型返回
                ],
                "isError": is_error  # 根据结果内容判断是否为错误
            })

        # -------- 处理心跳检测方法 --------
        if method == "ping":
            # 计算处理时间
            process_time = datetime.now() - start_time
            logger.info(
                "Heartbeat received", 
                extra={"client_ip": client_ip, "tool_name": "system", "process_time": f"{process_time.total_seconds():.3f}"}
            )
            return jsonrpc_response(request_id, {
                "status": "ok",  # 心跳状态正常
                "time": datetime.now(timezone.utc).isoformat()  # 当前UTC时间（ISO格式）
            })

        # 匹配不到任何方法时，返回方法未找到错误
        # 计算处理时间
        process_time = datetime.now() - start_time
        logger.error(
            f"Method not found: {method}", 
            extra={"client_ip": client_ip, "tool_name": "system", "process_time": f"{process_time.total_seconds():.3f}"}
        )
        return jsonrpc_error(request_id, -32601, f"Method not found: {method}")
