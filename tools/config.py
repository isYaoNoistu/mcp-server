# Lightweight .env loader for mcp-server tools (improved)
# 轻量级 .env 配置文件加载器（增强版），适用于 mcp-server 工具
# - 优先识别 DOTENV_PATH 环境变量（指定 .env 文件的绝对路径）
# - 自动向上搜索当前工作目录的 .env 文件，若未找到则查找代码仓库根目录（tools/ 父目录）
# - 对外暴露核心方法：get(key, default)（获取配置值）、as_dict()（获取全部配置）、repo_root()（获取仓库根目录）

from pathlib import Path
from typing import Dict, Optional
import os

# 全局缓存：存储加载后的环境配置（避免重复读取解析 .env 文件）
_ENV_CACHE: Optional[Dict[str, str]] = None

def _repo_root() -> Path:
    """
    私有辅助函数：获取代码仓库的根目录路径
    路径逻辑：当前文件（tools/config.py）的路径是 <repo>/tools/config.py，向上两级父目录即为仓库根目录
    :return: 仓库根目录的 Path 对象
    """
    return Path(__file__).resolve().parents[1]

def _find_dotenv_file() -> Optional[Path]:
    """
    私有辅助函数：按优先级查找 .env 文件，返回找到的文件路径或 None
    搜索优先级（从高到低）：
      1) 若设置了 DOTENV_PATH 环境变量：使用该路径（支持绝对/相对路径）
      2) 当前工作目录及其所有父目录（向上递归查找）
      3) 代码仓库根目录（tools/ 同级目录下的 .env）
    Returns: 找到的 .env 文件 Path 对象，未找到则返回 None
    """
    # 1) 优先级最高：使用 DOTENV_PATH 环境变量指定的路径
    override = os.environ.get("DOTENV_PATH")
    if override:
        # 解析路径：展开用户目录（~）并转换为绝对路径
        p = Path(override).expanduser().resolve()
        # 校验路径是否为存在的文件
        if p.exists() and p.is_file():
            return p

    # 2) 中等优先级：当前工作目录及其父目录向上查找
    cwd = Path.cwd().resolve()  # 获取当前工作目录的绝对路径
    # 遍历当前目录 + 所有父目录（如 /a/b/c -> /a/b/c → /a/b → /a → /）
    for p in [cwd] + list(cwd.parents):
        candidate = p / ".env"  # 拼接 .env 文件名
        if candidate.exists() and candidate.is_file():
            return candidate

    # 3) 最低优先级：代码仓库根目录
    repo_dotenv = _repo_root() / ".env"
    if repo_dotenv.exists() and repo_dotenv.is_file():
        return repo_dotenv

    # 所有路径均未找到 .env 文件
    return None

def _load_env() -> Dict[str, str]:
    """
    核心私有函数：加载并解析环境配置（系统环境变量 + .env 文件），结果存入全局缓存
    加载逻辑：
      1) 先继承系统已有的环境变量（os.environ）
      2) 解析 .env 文件，仅补充系统环境变量中不存在的配置（不覆盖已有变量）
      3) 解析后的配置存入全局缓存，后续调用直接返回缓存
    :return: 合并后的环境配置字典（key: 配置名，value: 配置值）
    """
    global _ENV_CACHE
    # 缓存命中：直接返回已加载的配置，避免重复IO
    if _ENV_CACHE is not None:
        return _ENV_CACHE

    # 初始化：以系统环境变量为基础（优先级最高）
    env: Dict[str, str] = dict(os.environ)

    # 查找 .env 文件
    dotenv = _find_dotenv_file()
    if not dotenv:
        # 未找到 .env 文件：缓存并返回系统环境变量
        _ENV_CACHE = env
        return env

    try:
        # 读取 .env 文件内容（UTF-8 编码），按行解析
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            line = line.strip()  # 去除行首尾空白字符
            # 跳过空行、注释行（以 # 开头）
            if not line or line.startswith("#"):
                continue
            # 跳过无等号的无效行（非 key=value 格式）
            if "=" not in line:
                continue
            # 分割键值对：仅按第一个 = 分割（支持值中包含 = 的场景）
            key, val = line.split("=", 1)
            key = key.strip()  # 去除键的首尾空白
            val = val.strip()  # 去除值的首尾空白
            # 移除值两端的引号（支持单引号/双引号包裹的场景，如 KEY="value" 或 KEY='value'）
            if (val.startswith("'") and val.endswith("'")) or (val.startswith('"') and val.endswith('"')):
                val = val[1:-1]
            # 仅当键不存在时才设置（系统环境变量优先级高于 .env 文件）
            env.setdefault(key, val)
    except Exception:
        # 捕获所有读取/解析异常（如文件权限、编码错误等），仅使用系统环境变量
        pass

    # 将合并后的配置存入全局缓存
    _ENV_CACHE = env
    return env

def get(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    对外暴露的核心方法：获取指定配置项的值
    :param key: 配置项名称（如 "FILES_ROOT"、"PROMETHEUS_API_URL"）
    :param default: 可选，配置项不存在时返回的默认值
    :return: 配置项的值（字符串），若不存在且未指定默认值则返回 None
    """
    return _load_env().get(key, default)

def as_dict() -> Dict[str, str]:
    """
    对外暴露的方法：获取全部环境配置的字典副本
    注：返回的是副本，修改不会影响内部缓存
    :return: 包含所有配置的字典（key: 配置名，value: 配置值）
    """
    return dict(_load_env())

def repo_root() -> Path:
    """
    对外暴露的方法：获取代码仓库的根目录路径（tools/ 所在的父目录）
    常用于解析相对路径为仓库根目录下的绝对路径
    :return: 仓库根目录的 Path 对象
    """
    return _repo_root()

def clear_cache() -> None:
    """
    对外暴露的方法：清除配置缓存，强制下次调用 get() 时重新加载 .env 文件
    用于配置更新后立即生效的场景
    """
    global _ENV_CACHE
    _ENV_CACHE = None