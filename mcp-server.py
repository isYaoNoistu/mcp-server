# -*- coding: utf-8 -*-
# 基于FastAPI实现的MCP服务端，遵循JSON-RPC 2.0协议
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import uvicorn
import logging
import os

# 从核心模块导入工具注册相关函数和API路由注册函数
from core.registry import load_tools
from core.api import register_routes

# 配置日志
# 创建日志器实例，指定日志名称为"mcp-server"
logger = logging.getLogger("mcp-server")
logger.setLevel(logging.INFO)

# 确保logs目录存在
os.makedirs("logs", exist_ok=True)

# 创建文件处理器，将日志写入logs/mcp-server.log
file_handler = logging.FileHandler("logs/mcp-server.log", encoding="utf-8")
file_handler.setLevel(logging.INFO)

# 定义日志格式 - 优化为更易于解析的格式，包含处理时间
log_format = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(client_ip)s - %(tool_name)s - %(process_time)s - %(message)s"
)
file_handler.setFormatter(log_format)

# 创建自定义过滤器，用于记录客户端IP、工具名称和处理时间
class ToolLogFilter(logging.Filter):
    def __init__(self):
        super().__init__()
    
    def filter(self, record):
        # 添加合理的默认值，确保日志符合企业规范
        record.client_ip = getattr(record, 'client_ip', '127.0.0.1')
        record.tool_name = getattr(record, 'tool_name', 'system')
        record.process_time = getattr(record, 'process_time', '0.000')
        return True

# 添加过滤器到文件处理器
file_handler.addFilter(ToolLogFilter())

# 移除所有现有的处理器，然后添加文件处理器
for handler in logger.handlers[:]:
    logger.removeHandler(handler)
logger.addHandler(file_handler)

# 添加控制台处理器，保持原有控制台输出
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(log_format)
console_handler.addFilter(ToolLogFilter())
logger.addHandler(console_handler)

# 初始化FastAPI应用，指定服务标题（兼容Dify和Cherry的MCP服务端）
app = FastAPI(title="MCP Server (Dify & Cherry Compatible)")

# 配置静态文件服务
app.mount("/static", StaticFiles(directory="web/static"), name="static")

# 服务启动时加载所有注册的工具
load_tools()

# 注册所有API路由
register_routes(app)

if __name__ == "__main__":
    # 服务主入口：启动uvicorn服务，监听所有网卡的8000端口
    uvicorn.run(app, host="0.0.0.0", port=8000)
