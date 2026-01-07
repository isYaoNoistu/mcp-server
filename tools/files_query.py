# files_query tool for mcp-server
# Exports a module-level `tool` object compatible with mcp-server registry.
# Purpose:
#  - Expose a configured directory (FILES_ROOT) whose files can be listed or read.
#  - Support listing all files under the directory (recursive) and reading a single file.
#  - Always returns a STRING (Markdown or error string) so it's compatible with Dify/Cherry Studio.
#
# Configure FILES_ROOT below (absolute or relative to server working dir).
# If you want to "reset" the old read_file tool, replace it with this file.

import os
import stat
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List

# <-- Configure the root directory that the tool may access -->
# Set to the directory you want AI to analyze / read files from.
# Example: FILES_ROOT = "workspace/project" or "/data/analysis_dir"
FILES_ROOT = r"C:\Users\15509\Desktop\杂记\DDNS方案"  # default - change to your target directory
# Maximum bytes to read from a file. If file larger, content will be truncated.
FILE_READ_MAX_BYTES = 200 * 1024  # 200 KB
# ------------------------------------------------------------------------------

class FilesQueryTool:
    name = "files_query"
    aliases = ["files.query", "files"]
    description = (
        "List and read files under a configured directory (FILES_ROOT). "
        "Use action=list to show files, action=read with path to read a file."
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
            "max_bytes": {"type": "integer", "description": "Optional override for FILE_READ_MAX_BYTES (in bytes)"}
        },
        "required": []
    }

    def run(self, params: Dict[str, Any]) -> str:
        """
        params (dict):
          - action: "list" (default) or "read"
          - path: relative path to a file under FILES_ROOT (required for read)
          - max_bytes: optional integer override for read truncation
        Returns:
          - A string (markdown) listing files or file content, or Error: ... on failure.
        """
        try:
            # normalize param types
            if not isinstance(params, dict):
                return "Error: params must be a dict"

            action = (params.get("action") or "list").lower()
            rel_path = params.get("path")
            max_bytes = params.get("max_bytes")
            if isinstance(max_bytes, int) and max_bytes > 0:
                read_limit = int(max_bytes)
            else:
                read_limit = FILE_READ_MAX_BYTES

            # Resolve root
            root = Path(FILES_ROOT).resolve()
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
        """
        Return a markdown table of files: path | size | mtime
        """
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
                    # skip unreadable files but continue
                    continue

        if not rows:
            return f"No files found under {root}"

        # sort by path
        rows.sort(key=lambda r: r[0])

        header = "| path | size (bytes) | mtime (UTC) |"
        sep = "| --- | ---: | --- |"
        lines = [f"# Files under {root}", "", header, sep]
        for r in rows:
            lines.append(f"| {r[0]} | {r[1]} | {r[2]} |")

        return "\n".join(lines)

    def _read_file_markdown(self, root: Path, rel_path: str, max_bytes: int) -> str:
        """
        Read a file under root safely. Prevent path traversal.
        Returns markdown with file metadata and content (truncated if large).
        """
        # Normalize path: prevent leading slash and .. components
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

            # Read bytes up to max_bytes
            with open(candidate, "rb") as f:
                content_bytes = f.read(max_bytes + 1)

            truncated = len(content_bytes) > max_bytes
            # Try to decode as UTF-8 for readable content. Use replacement to avoid failure.
            try:
                text = content_bytes.decode("utf-8")
                # If truncated, note it
                if truncated:
                    text = text[:max_bytes]
                # Return as fenced code block in markdown
                body = ["```", text, "```"]
                if truncated:
                    body.insert(0, f"> Note: content truncated to {max_bytes} bytes")
            except Exception:
                # Binary file or cannot decode
                return "\n".join(header_lines + ["> Binary or non-text file (cannot display as UTF-8)."])

            return "\n".join(header_lines + body)

        except Exception as e:
            return f"Error: reading file failed: {str(e)}"


# module-level tool object required by mcp-server registry
tool = FilesQueryTool()