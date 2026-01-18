# files_query tool for mcp-server
# 用于mcp-server的文件查询工具
# 从根目录的.env文件中通过tools.config读取FILES_ROOT配置
# 若FILES_ROOT为相对路径，则基于代码仓库根目录解析
# 返回字符串（markdown格式或错误信息）以保证兼容性

import os
import stat
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# 导入配置相关工具：读取配置项、获取代码仓库根目录
from tools.config import get as cfg_get, repo_root as cfg_repo_root

# 默认文件读取最大字节数限制（200KB）
DEFAULT_FILE_READ_MAX_BYTES = 200 * 1024  # 200 KB


class FilesQueryTool:
    # 工具名称
    name = "files_query"
    # 工具别名，用于兼容不同的调用方式
    aliases = ["files.query", "files"]
    # 工具描述：说明工具功能
    description = (
        "列出和读取由.env中FILES_ROOT配置的目录下的文件"
    )
    # 输入参数schema：定义调用工具时允许的参数格式和类型
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "read"]},  # 操作类型：list(列出文件)、read(读取文件)
            "path": {"type": "string"},  # 文件/目录路径：read操作必填
            "max_bytes": {"type": "integer"}  # 读取文件的最大字节数限制
        },
        "required": []  # 无强制必填参数（action有默认值，path仅read时必填）
    }

    def run(self, params: Dict[str, Any]) -> str:
        """
        工具核心执行方法：处理用户传入的参数，执行对应的文件操作并返回结果
        :param params: 调用工具时传入的参数字典
        :return: markdown格式的结果字符串或错误信息字符串
        """
        try:
            # 校验参数类型：必须是字典
            if not isinstance(params, dict):
                return "Error: params must be a dict"

            # 解析操作类型：默认值为list，转为小写确保匹配
            action = (params.get("action") or "list").lower()
            # 解析文件/目录路径参数
            rel_path = params.get("path")
            # 解析最大读取字节数参数
            max_bytes = params.get("max_bytes")

            # 确定最终的文件读取字节限制
            if isinstance(max_bytes, int) and max_bytes > 0:
                read_limit = int(max_bytes)  # 使用用户传入的有效值
            else:
                # 从环境配置读取限制，读取失败则使用默认值
                env_limit = cfg_get("FILE_READ_MAX_BYTES")
                try:
                    read_limit = int(env_limit) if env_limit else DEFAULT_FILE_READ_MAX_BYTES
                except Exception:
                    read_limit = DEFAULT_FILE_READ_MAX_BYTES

            # 读取FILES_ROOT配置（文件操作的根目录）
            files_root_cfg = cfg_get("FILES_ROOT") or ""
            if not files_root_cfg:
                return "Error: FILES_ROOT not configured in .env"

            # 解析FILES_ROOT路径：处理用户目录(~)、相对路径/绝对路径
            files_root_cfg = os.path.expanduser(files_root_cfg.strip())
            candidate = Path(files_root_cfg)
            if not candidate.is_absolute():
                # 相对路径：基于代码仓库根目录解析为绝对路径
                root = (cfg_repo_root() / candidate).resolve()
            else:
                # 绝对路径：直接解析
                root = candidate.resolve()

            # 校验FILES_ROOT目录是否存在
            if not root.exists() or not root.is_dir():
                return f"Error: FILES_ROOT directory not found: {root}"

            # 根据操作类型执行对应逻辑
            if action == "list":
                return self._list_files_markdown(root)  # 列出目录下所有文件
            elif action == "read":
                if not rel_path:
                    return "Error: 'path' parameter is required for action='read'"
                return self._read_file_markdown(root, rel_path, read_limit)  # 读取指定文件
            else:
                return "Error: unknown action. Supported: list, read"

        # 捕获所有异常并返回错误信息
        except Exception as e:
            return f"Error: exception: {str(e)}"

    def _is_within_root(self, root: Path, candidate: Path) -> bool:
        """
        私有辅助方法：检查目标文件/目录是否在FILES_ROOT范围内（防止路径遍历攻击）
        :param root: FILES_ROOT根目录路径对象
        :param candidate: 待检查的目标路径对象
        :return: 若在范围内返回True，否则返回False
        """
        try:
            # 通过解析绝对路径并检查前缀的方式验证
            return str(candidate.resolve()).startswith(str(root))
        except Exception:
            return False

    def _list_files_markdown(self, root: Path) -> str:
        """
        私有辅助方法：遍历FILES_ROOT目录，生成包含文件信息的markdown格式字符串
        :param root: FILES_ROOT根目录路径对象
        :return: markdown格式的文件列表字符串
        """
        rows: List[List[str]] = []
        # 递归遍历根目录下所有文件
        for dirpath, dirnames, filenames in os.walk(root):
            for fname in filenames:
                fpath = Path(dirpath) / fname
                try:
                    # 获取文件属性
                    st = fpath.stat()
                    size = st.st_size  # 文件大小（字节）
                    # 转换修改时间为UTC时区的ISO格式（Z结尾）
                    mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")
                    # 计算文件相对于根目录的路径
                    rel = str(fpath.resolve().relative_to(root))
                    # 收集文件信息行
                    rows.append([rel, str(size), mtime])
                except Exception:
                    # 忽略获取属性失败的文件
                    continue

        # 无文件时返回提示信息
        if not rows:
            return f"No files found under {root}"

        # 按文件路径排序
        rows.sort(key=lambda r: r[0])

        # 构建markdown表格
        header = "| path | size (bytes) | mtime (UTC) |"  # 表格头
        sep = "| --- | ---: | --- |"  # 表格分隔线
        # 组装最终markdown内容
        lines = [f"# Files under {root}", "", header, sep]
        for r in rows:
            lines.append(f"| {r[0]} | {r[1]} | {r[2]} |")

        return "\n".join(lines)

    def _read_file_markdown(self, root: Path, rel_path: str, max_bytes: int) -> str:
        """
        私有辅助方法：读取指定文件内容，生成包含文件信息和内容的markdown格式字符串
        :param root: FILES_ROOT根目录路径对象
        :param rel_path: 相对于根目录的文件路径
        :param max_bytes: 最大读取字节数限制
        :return: markdown格式的文件内容字符串或错误信息
        """
        # 解析目标文件的绝对路径
        candidate = (root / rel_path).resolve()

        # 安全校验：防止读取根目录外的文件
        if not self._is_within_root(root, candidate):
            return f"Error: access to path '{rel_path}' is outside FILES_ROOT"

        # 校验文件是否存在
        if not candidate.exists():
            return f"Error: file not found: {rel_path}"

        # 校验路径是否为文件（而非目录）
        if not candidate.is_file():
            return f"Error: path is not a file: {rel_path}"

        try:
            # 获取文件属性
            st = candidate.stat()
            size = st.st_size  # 文件总大小
            # 转换修改时间为UTC时区的ISO格式
            mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")
            mode = stat.filemode(st.st_mode)  # 文件权限模式（如-rw-r--r--）

            # 构建文件信息头
            header_lines = [
                f"# File: {rel_path}",
                "",
                f"- path: {candidate}",
                f"- size: {size} bytes",
                f"- mtime: {mtime}",
                f"- mode: {mode}",
                ""
            ]

            # 读取文件内容（二进制模式，防止编码问题）
            with open(candidate, "rb") as f:
                # 读取max_bytes+1字节，用于判断是否需要截断
                content_bytes = f.read(max_bytes + 1)

            # 判断是否截断（读取的字节数超过限制）
            truncated = len(content_bytes) > max_bytes
            try:
                # 尝试解码为UTF-8文本
                text = content_bytes.decode("utf-8")
                if truncated:
                    text = text[:max_bytes]  # 截断到最大字节数
                # 构建内容体（代码块格式）
                body = ["```", text, "```"]
                if truncated:
                    # 添加截断提示
                    body.insert(0, f"> Note: content truncated to {max_bytes} bytes")
            except Exception:
                # 解码失败：说明是二进制文件或非UTF-8文本文件
                return "\n".join(header_lines + ["> Binary or non-text file (cannot display as UTF-8)."])

            # 拼接文件信息头和内容体
            return "\n".join(header_lines + body)

        except Exception as e:
            return f"Error: reading file failed: {str(e)}"


# 创建工具实例，供外部调用
tool = FilesQueryTool()