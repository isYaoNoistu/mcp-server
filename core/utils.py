# -*- coding: utf-8 -*-
"""工具模块，包含工具调用计数器、客户端IP获取等通用功能"""

import os
import json
from fastapi import Request

# 工具调用计数器文件路径
COUNTER_FILE = "logs/tool_call_counter.json"

# 加载工具调用计数器
tool_call_counter = {}
if os.path.exists(COUNTER_FILE):
    try:
        with open(COUNTER_FILE, "r", encoding="utf-8") as f:
            tool_call_counter = json.load(f)
    except Exception as e:
        import logging
        logger = logging.getLogger("mcp-server")
        logger.error(f"Failed to load tool call counter: {e}")
        tool_call_counter = {}


def save_tool_call_counter():
    """保存工具调用计数器到文件"""
    try:
        with open(COUNTER_FILE, "w", encoding="utf-8") as f:
            json.dump(tool_call_counter, f, ensure_ascii=False, indent=2)
    except Exception as e:
        import logging
        logger = logging.getLogger("mcp-server")
        logger.error(f"Failed to save tool call counter: {e}")


def get_client_ip(request: Request) -> str:
    """获取客户端IP地址"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"
