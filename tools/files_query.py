# files_query tool for mcp-server
# Reads FILES_ROOT from root .env via tools.config, no hardcoded FILES_ROOT.
# Exports module-level `tool` object, returns strings (markdown or Error).

import os
import stat
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from tools.config import get as cfg_get

# Default maximum bytes to read if not set in .env
DEFAULT_FILE_READ_MAX_BYTES = 200 * 1024  # 200 KB

class FilesQueryTool:
    name = "files_query"
    aliases = ["files.query", "files"]
    description = (
        "List and read files under directory configured by FILES_ROOT in .env."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "read"],
                "description": "list: list all files under FILES_ROOT; read: read a single file"
            },
            "path": {"type": "string", "description": "Relative file path under FILES_ROOT (for read)"},
            "max_bytes": {"type": "integer", "description": "Optional override for read truncation"}
        },
        "required": []
    }

    def run(self, params: Dict[str, Any]) -> str:
        try:
            if not isinstance(params, dict):
                return "Error: params must be a dict"

            action = (params.get("action") or "list").lower()
            rel_path = params.get("path")
            max_bytes = params.get("max_bytes")
            if isinstance(max_bytes, int) and max_bytes > 0:
                read_limit = int(max_bytes)
            else:
                # read limit from .env or default
                env_limit = cfg_get("FILE_READ_MAX_BYTES")
                try:
                    read_limit = int(env_limit) if env_limit else DEFAULT_FILE_READ_MAX_BYTES
                except Exception:
                    read_limit = DEFAULT_FILE_READ_MAX_BYTES

            # Determine FILES_ROOT from .env (required)
            files_root_cfg = cfg_get("FILES_ROOT") or ""
            if not files_root_cfg:
                return "Error: FILES_ROOT not configured in .env"
            root = Path(files_root_cfg).resolve()
            if not root.exists() or not root.is_dir():
                return f"Error: FILES_ROOT directory not found: {root}"

            if action == "list":
                return self._list_files_markdown(root)
            elif action == "read":
                if not rel_path:
                    return "Error: 'path' parameter is required for action='read'"
                return self._read_file_markdown(root, rel_path, read_limit)
            else:
                return "Error: unknown action. Supported: list, read"

        except Exception as e:
            return f"Error: exception: {str(e)}"

    def _is_within_root(self, root: Path, candidate: Path) -> bool:
        try:
            return str(candidate.resolve()).startswith(str(root))
        except Exception:
            return False

    def _list_files_markdown(self, root: Path) -> str:
        rows: List[List[str]] = []
        for dirpath, dirnames, filenames in os.walk(root):
            for fname in filenames:
                fpath = Path(dirpath) / fname
                try:
                    st = fpath.stat()
                    size = st.st_size
                    mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")
                    rel = str(fpath.resolve().relative_to(root))
                    rows.append([rel, str(size), mtime])
                except Exception:
                    continue

        if not rows:
            return f"No files found under {root}"

        rows.sort(key=lambda r: r[0])

        header = "| path | size (bytes) | mtime (UTC) |"
        sep = "| --- | ---: | --- |"
        lines = [f"# Files under {root}", "", header, sep]
        for r in rows:
            lines.append(f"| {r[0]} | {r[1]} | {r[2]} |")

        return "\n".join(lines)

    def _read_file_markdown(self, root: Path, rel_path: str, max_bytes: int) -> str:
        candidate = (root / rel_path).resolve()

        if not self._is_within_root(root, candidate):
            return f"Error: access to path '{rel_path}' is outside FILES_ROOT"

        if not candidate.exists():
            return f"Error: file not found: {rel_path}"

        if not candidate.is_file():
            return f"Error: path is not a file: {rel_path}"

        try:
            st = candidate.stat()
            size = st.st_size
            mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")
            mode = stat.filemode(st.st_mode)
            header_lines = [
                f"# File: {rel_path}",
                "",
                f"- path: {candidate}",
                f"- size: {size} bytes",
                f"- mtime: {mtime}",
                f"- mode: {mode}",
                ""
            ]

            with open(candidate, "rb") as f:
                content_bytes = f.read(max_bytes + 1)

            truncated = len(content_bytes) > max_bytes
            try:
                text = content_bytes.decode("utf-8")
                if truncated:
                    text = text[:max_bytes]
                body = ["```", text, "```"]
                if truncated:
                    body.insert(0, f"> Note: content truncated to {max_bytes} bytes")
            except Exception:
                return "\n".join(header_lines + ["> Binary or non-text file (cannot display as UTF-8)."])

            return "\n".join(header_lines + body)

        except Exception as e:
            return f"Error: reading file failed: {str(e)}"

tool = FilesQueryTool()