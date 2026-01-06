# -*- coding: utf-8 -*-
from fastapi import FastAPI, Request, Response
import uvicorn
import logging
from datetime import datetime

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
    body = await request.json()
    method = body.get("method")
    request_id = body.get("id")

    # -------- Notification --------
    if method == "notifications/initialized":
        logger.info("MCP initialized notification received")
        return Response(status_code=204)

    # -------- Base validation --------
    if body.get("jsonrpc") != "2.0":
        return jsonrpc_error(request_id, -32600, "Invalid JSON-RPC version")

    if request_id is None:
        return jsonrpc_error(None, -32600, "id must not be null")

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
        return jsonrpc_error(
            request_id,
            -32002,
            "Server not initialized"
        )

    # -------- tools/list --------
    if method == "tools/list":
        return jsonrpc_response(request_id, {
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.input_schema
                }
                for t in list_tools()
            ]
        })

    # -------- tools/call --------
    if method == "tools/call":
        params = body.get("params", {})
        tool_name = params.get("name")

        try:
            result = call_tool(tool_name, params.get("arguments", {}))
        except KeyError:
            return jsonrpc_error(request_id, -32601, "Tool not found")

        return jsonrpc_response(request_id, {
            "content": [
                {"type": "text", "text": result}
            ],
            "isError": False
        })

    from datetime import datetime, timezone
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
