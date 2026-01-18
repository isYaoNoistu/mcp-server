# -*- coding: utf-8 -*-
# 调用记录管理模块
import json
import os
from datetime import datetime, timezone

# 调用记录文件路径
CALL_RECORDS_FILE = "logs/call_records.json"

# 调用记录列表（内存存储）
call_records = []
MAX_RECORDS = 1000  # 最多保存1000条记录

# 保存调用记录到文件
def save_call_records():
    """保存调用记录到文件"""
    try:
        with open(CALL_RECORDS_FILE, "w", encoding="utf-8") as f:
            json.dump(call_records, f, ensure_ascii=False, indent=2)
    except Exception as e:
        from logging import getLogger
        logger = getLogger("mcp-server")
        logger.error(f"Failed to save call records: {e}")

# 添加调用记录
def add_call_record(client_ip, tool_name, status, process_time, details=""):
    """添加工具调用记录"""
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "client_ip": client_ip,
        "tool_name": tool_name,
        "status": status,
        "process_time": process_time,
        "details": details
    }
    call_records.append(record)
    
    # 限制记录数量
    if len(call_records) > MAX_RECORDS:
        call_records.pop(0)
    
    # 保存到文件
    save_call_records()

# 加载调用记录
def load_call_records():
    """从文件加载调用记录"""
    global call_records
    if os.path.exists(CALL_RECORDS_FILE):
        try:
            with open(CALL_RECORDS_FILE, "r", encoding="utf-8") as f:
                call_records = json.load(f)
        except Exception as e:
            from logging import getLogger
            logger = getLogger("mcp-server")
            logger.error(f"Failed to load call records: {e}")
            call_records = []

# 获取调用记录
def get_call_records(limit=100, offset=0):
    """获取调用记录（分页）"""
    # 按时间倒序排序（最新的记录在前）
    sorted_records = sorted(call_records, key=lambda x: x['timestamp'], reverse=True)
    
    # 获取分页数据
    paginated_records = sorted_records[offset:offset + limit]
    
    return {
        "records": paginated_records,
        "total": len(sorted_records),
        "limit": limit,
        "offset": offset
    }

# 获取调用统计数据
def get_call_stats():
    """获取调用统计数据"""
    total_calls = len(call_records)
    success_calls = sum(1 for r in call_records if r['status'] == 'success')
    success_rate = success_calls / total_calls if total_calls > 0 else 0
    
    # 按工具名称分组统计成功率
    tool_success_rates = {}
    tool_call_counts = {}
    
    for record in call_records:
        tool = record['tool_name']
        tool_call_counts[tool] = tool_call_counts.get(tool, 0) + 1
        if record['status'] == 'success':
            if tool not in tool_success_rates:
                tool_success_rates[tool] = {'success': 0, 'total': 0}
            tool_success_rates[tool]['success'] += 1
            tool_success_rates[tool]['total'] += 1
        else:
            if tool not in tool_success_rates:
                tool_success_rates[tool] = {'success': 0, 'total': 0}
            tool_success_rates[tool]['total'] += 1
    
    # 计算每个工具的成功率
    success_rates = {}
    for tool, counts in tool_success_rates.items():
        success_rates[tool] = counts['success'] / counts['total'] if counts['total'] > 0 else 0
    
    return {
        "total_calls": total_calls,
        "success_calls": success_calls,
        "success_rate": success_rate,
        "tool_call_counts": tool_call_counts,
        "success_rates": success_rates
    }

# 初始化调用记录
load_call_records()
