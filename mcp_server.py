# -*- coding: utf-8 -*-
# 基于FastAPI实现的MCP服务端（兼容Dify & Cherry），遵循JSON-RPC 2.0协议
from fastapi import FastAPI, Request, Response
import uvicorn
import logging
from datetime import datetime, timezone

# 从核心模块导入JSON-RPC响应/错误构造函数、服务状态管理、工具注册相关函数
from core.protocol import jsonrpc_response, jsonrpc_error
from core.state import MCPServerState
from core.registry import load_tools, list_tools, call_tool

# 配置日志基础级别为INFO
logging.basicConfig(level=logging.INFO)
# 创建日志器实例，指定日志名称为"mcp-server"
logger = logging.getLogger("mcp-server")

# 初始化FastAPI应用，指定服务标题（兼容Dify和Cherry的MCP服务端）
app = FastAPI(title="MCP Server (Dify & Cherry Compatible)")

# 服务启动时加载所有注册的工具
load_tools()


@app.post("/mcp")
async def mcp_handler(request: Request):
    """MCP核心请求处理接口，接收并处理所有JSON-RPC协议请求"""
    # 尽量在入口处捕获JSON解析错误，并返回JSON-RPC标准的解析错误
    try:
        # 读取并解析请求体的JSON数据
        body = await request.json()
    except Exception:
        # 记录JSON解析失败的警告日志
        logger.warning("Failed to parse request JSON")
        # JSON-RPC规范：解析错误时id为null
        return jsonrpc_error(None, -32700, "Parse error: invalid JSON")

    # 提取请求中的方法名和请求ID
    method = body.get("method")
    request_id = body.get("id")

    # 将没有request_id的请求视为通知类请求 -> 返回204无内容响应
    if request_id is None:
        logger.info(f"Notification received (method={method}) -> 204")
        # 可选处理initialized通知（初始化完成通知）
        if method == "notifications/initialized":
            # 标记服务状态为已初始化
            MCPServerState.initialized = True
            logger.info("Set MCPServerState.initialized = True from notification")
        # 返回204状态码（无内容）
        return Response(status_code=204)

    # 兼容JSON-RPC字段缺失场景：仅当字段存在且不等于"2.0"时才返回版本错误
    if "jsonrpc" in body and body.get("jsonrpc") != "2.0":
        return jsonrpc_error(request_id, -32600, "Invalid JSON-RPC version")

    # 记录请求的方法名和请求ID
    logger.info(f"MCP method: {method}, id: {request_id}")

    # -------- 处理初始化方法 --------
    if method == "initialize":
        # 标记服务状态为已初始化
        MCPServerState.initialized = True
        # 返回初始化成功的JSON-RPC响应
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
        return jsonrpc_error(request_id, -32002, "Server not initialized")

    # -------- 处理工具列表查询方法 --------
    if method == "tools/list":
        # 构造所有已加载工具的列表并返回
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

        try:
            # 调用指定名称的工具并获取结果
            result = call_tool(tool_name, params)
        except KeyError:
            # 工具不存在时返回JSON-RPC方法未找到错误
            return jsonrpc_error(request_id, -32601, "Tool not found")

        # 将工具调用结果标准化为Dify期望的内容列表格式
        return jsonrpc_response(request_id, {
            "content": [
                {"type": "text", "text": result}  # 结果以文本类型返回
            ],
            "isError": False  # 标记调用无错误
        })

    # -------- 处理心跳检测方法 --------
    if method == "ping":
        return jsonrpc_response(request_id, {
            "status": "ok",  # 心跳状态正常
            "time": datetime.now(timezone.utc).isoformat()  # 当前UTC时间（ISO格式）
        })

    # 匹配不到任何方法时，返回方法未找到错误
    return jsonrpc_error(request_id, -32601, f"Method not found: {method}")


@app.get("/health")
def health():
    """服务健康检查接口"""
    return {
        "status": "ok",  # 服务运行状态
        "initialized": MCPServerState.initialized  # 服务初始化状态
    }


if __name__ == "__main__":
    # 服务主入口：启动uvicorn服务，监听所有网卡的8000端口
    uvicorn.run(app, host="0.0.0.0", port=8000)