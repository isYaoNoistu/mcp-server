# -*- coding: utf-8 -*-
from fastapi import FastAPI, Request, Response
import uvicorn
import logging
from datetime import datetime, timezone

from core.protocol import jsonrpc_response, jsonrpc_error
from core.state import MCPServerState
from core.registry import load_tools, list_tools, call_tool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-server")

app = FastAPI(title="MCP Server (Dify & Cherry Compatible)")

# 启动时加载所有 tools
load_tools()


@app.post("/mcp")
async def mcp_handler(request: Request):
    # 尽量在入口处捕获解析错误并返回 JSON-RPC parse error
    try:
        body = await request.json()
    except Exception:
        logger.warning("Failed to parse request JSON")
        # id unknown -> null in JSON-RPC error
        return jsonrpc_error(None, -32700, "Parse error: invalid JSON")

    method = body.get("method")
    request_id = body.get("id")

    # Treat requests without id as notifications -> 204 No Content
    if request_id is None:
        logger.info(f"Notification received (method={method}) -> 204")
        # optional handling of initialized notification
        if method == "notifications/initialized":
            MCPServerState.initialized = True
            logger.info("Set MCPServerState.initialized = True from notification")
        return Response(status_code=204)

    # Allow missing jsonrpc field: only error if present and not "2.0"
    if "jsonrpc" in body and body.get("jsonrpc") != "2.0":
        return jsonrpc_error(request_id, -32600, "Invalid JSON-RPC version")

    logger.info(f"MCP method: {method}, id: {request_id}")

    # -------- initialize --------
    if method == "initialize":
        MCPServerState.initialized = True
        return jsonrpc_response(request_id, {
            "protocolVersion": "2025-06-18",
            "capabilities": {
                "tools": {},
                "roots": {},
                "logging": {}
            },
            "serverInfo": {
                "name": "mcp-server",
                "version": "2.0.0"
            }
        })

    # -------- lifecycle guard --------
    if not MCPServerState.initialized:
        return jsonrpc_error(request_id, -32002, "Server not initialized")

    # -------- tools/list --------
    if method == "tools/list":
        return jsonrpc_response(request_id, {
            "tools": [
                {
                    "name": t.name,
                    "description": getattr(t, "description", ""),
                    "inputSchema": getattr(t, "input_schema", {})
                }
                for t in list_tools()
            ]
        })

    # -------- tools/call --------
    if method == "tools/call":
        params = body.get("params", {})
        tool_name = params.get("name") if isinstance(params, dict) else None

        try:
            result = call_tool(tool_name, params)
        except KeyError:
            return jsonrpc_error(request_id, -32601, "Tool not found")

        # normalize result into content list expected by Dify
        return jsonrpc_response(request_id, {
            "content": [
                {"type": "text", "text": result}
            ],
            "isError": False
        })

    # -------- ping --------
    if method == "ping":
        return jsonrpc_response(request_id, {
            "status": "ok",
            "time": datetime.now(timezone.utc).isoformat()
        })

    return jsonrpc_error(request_id, -32601, f"Method not found: {method}")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "initialized": MCPServerState.initialized
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)