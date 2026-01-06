# -*- coding: utf-8 -*-
import importlib
import pkgutil
from typing import Dict, Any

# 工具注册表：键为工具名称/别名，值为对应的工具对象
_TOOL_REGISTRY: Dict[str, object] = {}


def register_tool(tool: Any):
    """
    注册工具对象，同时注册其主名称和所有别名。

    工具对象需满足以下属性/方法要求：
      - name: str（必填，工具主名称）
      - description: str（可选，工具描述）
      - input_schema: dict（可选，工具入参Schema）
      - run(params: dict) -> str（必填，工具执行方法）
      - aliases: list[str]（可选，工具别名列表）
    """
    # 注册工具主名称
    _TOOL_REGISTRY[tool.name] = tool
    # 获取工具别名（无则为空列表）
    aliases = getattr(tool, "aliases", []) or []
    for a in aliases:
        # 避免同名别名覆盖已注册的不同工具
        if a in _TOOL_REGISTRY and _TOOL_REGISTRY[a] is not tool:
            continue
        # 注册工具别名
        _TOOL_REGISTRY[a] = tool


def load_tools():
    """
    自动加载tools包下所有模块，并注册模块中暴露的`tool`对象。
    """
    # 导入tools包（需确保项目根目录有tools包）
    import tools
    # 遍历tools包下所有模块
    for _, module_name, _ in pkgutil.iter_modules(tools.__path__):
        # 动态导入模块
        module = importlib.import_module(f"tools.{module_name}")
        # 若模块中有tool对象，则注册该工具
        if hasattr(module, "tool"):
            register_tool(module.tool)


def list_tools():
    """
    返回所有已注册的唯一工具对象（按对象内存地址去重）。
    """
    # 记录已遍历过的工具对象内存地址，用于去重
    seen = set()
    unique_tools = []
    # 遍历注册表中的所有工具对象
    for t in _TOOL_REGISTRY.values():
        # 通过对象id判断是否已存在，避免重复
        if id(t) in seen:
            continue
        seen.add(id(t))
        unique_tools.append(t)
    return unique_tools


def _normalize_arguments_from_params(params: dict):
    """
    标准化工具调用的入参（兼容不同Agent的参数传递格式）。
    支持的参数字段：'arguments'、'input'、'args'、'parameters'。
    若params本身是原始参数字典，直接返回；
    若params包含除'name'外的其他键，将这些键值对作为入参返回。
    """
    # 非字典/空字典直接返回空参数
    if not params or not isinstance(params, dict):
        return {}
    # 优先读取常用的参数字段
    for key in ("arguments", "input", "args", "parameters"):
        if key in params and isinstance(params[key], dict):
            return params[key]
    # 若存在非name的键，过滤掉name后返回剩余键值对
    if any(k != "name" for k in params.keys()):
        return {k: v for k, v in params.items() if k != "name"}
    # 无有效参数时返回空字典
    return {}


def call_tool(name: str, params: dict):
    """
    根据工具名称/别名查找工具，并使用标准化后的参数调用其run()方法。
    若工具未找到，抛出KeyError异常。
    """
    # 工具名称为空/未注册时抛出异常
    if not name or name not in _TOOL_REGISTRY:
        raise KeyError(f"Tool not found: {name}")
    # 获取工具对象
    tool = _TOOL_REGISTRY[name]
    # 标准化调用参数
    args = _normalize_arguments_from_params(params or {})
    # 执行工具并返回结果
    return tool.run(args)