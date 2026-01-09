#!/usr/bin/env python3
"""
scripts/add_tool.py

用途：
  - 将指定工具名���入仓库根的 .tool_state.json 的 enabled 列表（创建文件如不存在）。
  - 可选：在运行时向本地 mcp-server 发起 control_center enable 请求以立即启用该工具（不需重启）。
  - 跨平台（Windows / Linux），建议在项目虚拟环境中运行。

用法：
  python scripts/add_tool.py <tool_name> [--enable-runtime] [--server http://127.0.0.1:8000/mcp]

示例：
  # 仅把工具名写入 .tool_state.json（持久化），不触发运行时启用
  python scripts/add_tool.py mynewtool

  # 写入并在本地正在运行的 mcp-server 上启用（需要 control_center 已启用）
  python scripts/add_tool.py mynewtool --enable-runtime

注意：
  - 如果你希望新工具在下次启动自动启用，请确保 core/registry.py 的 ALLOW_AUTO_ENABLE_NEW_TOOLS 配置为 true（默认）。
  - 若 mcp-server 未运行或 control_center 被禁用，--enable-runtime 会返回错误信息但 .tool_state.json 已被更新。
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Optional
import requests

# Import tools.config to resolve repo root and .env handling
try:
    from tools.config import repo_root as cfg_repo_root
except Exception:
    cfg_repo_root = None

def repo_root() -> Path:
    if cfg_repo_root:
        return cfg_repo_root()
    # fallback: assume script is inside repo/scripts
    p = Path(__file__).resolve()
    return p.parents[2]

def load_tool_state(path: Path) -> dict:
    if not path.exists():
        return {"enabled": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"enabled": []}

def save_tool_state(path: Path, data: dict):
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

def add_tool_to_state(path: Path, tool_name: str) -> bool:
    data = load_tool_state(path)
    enabled = data.get("enabled") or []
    if tool_name in enabled:
        return False
    enabled.append(tool_name)
    # keep sorted for readability
    enabled = sorted(set(enabled))
    data["enabled"] = enabled
    save_tool_state(path, data)
    return True

def enable_tool_runtime(server_url: str, tool_name: str) -> (bool, str):
    """
    Call control_center enable via JSON-RPC to enable runtime.
    Returns (ok, message).
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "control_center",
            "arguments": {"action": "enable", "name": tool_name}
        }
    }
    headers = {"Content-Type": "application/json"}
    try:
        r = requests.post(server_url, json=payload, headers=headers, timeout=10)
        try:
            jr = r.json()
        except Exception:
            return False, f"HTTP {r.status_code} response (not JSON): {r.text[:400]}"
        if "error" in jr:
            return False, f"RPC error: {jr.get('error')}"
        return True, f"Enabled runtime: {jr.get('result') or jr}"
    except Exception as e:
        return False, f"Exception calling server: {e}"

def main():
    ap = argparse.ArgumentParser(description="Add tool name to .tool_state.json and optionally enable runtime via control_center.")
    ap.add_argument("tool", help="canonical tool name to add (e.g., mynewtool)")
    ap.add_argument("--enable-runtime", action="store_true", help="also call running MCP server to enable tool immediately (requires control_center enabled)")
    ap.add_argument("--server", default="http://127.0.0.1:8000/mcp", help="MCP server JSON-RPC endpoint for runtime enable (default http://127.0.0.1:8000/mcp)")
    args = ap.parse_args()

    root = repo_root()
    state_file = root / ".tool_state.json"
    added = add_tool_to_state(state_file, args.tool)
    if added:
        print(f"Added tool '{args.tool}' to {state_file}")
    else:
        print(f"Tool '{args.tool}' already present in {state_file}")

    if args.enable_runtime:
        ok, msg = enable_tool_runtime(args.server, args.tool)
        if ok:
            print(f"Runtime enable succeeded: {msg}")
        else:
            print(f"Runtime enable failed: {msg}", file=sys.stderr)
            # even if runtime enable fails, we have persisted to .tool_state.json

    else:
        print("Note: runtime not modified. If MCP server is running, you can enable runtime via control_center or restart service to pick up .env/.tool_state.json changes.")

if __name__ == "__main__":
    main()