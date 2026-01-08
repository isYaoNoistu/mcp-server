#!/usr/bin/env bash
# start_project.sh - MCP Server 初始化脚本
# 功能：创建Python虚拟环境、安装依赖、配置并启动systemd服务
# 要求：Linux+systemd、Python≥3.10
# 使用：chmod +x start_project.sh && ./start_project.sh

set -euo pipefail

# 颜色输出定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 国内PyPI源配置
PYPI_MIRROR_MAIN="https://pypi.tuna.tsinghua.edu.cn/simple/"
PYPI_MIRROR_FALLBACK="https://mirrors.aliyun.com/pypi/simple/"

# 日志输出函数
info() { echo -e "${GREEN}[INFO] $1${NC}"; }
warn() { echo -e "${YELLOW}[WARN] $1${NC}"; }
error() { echo -e "${RED}[ERROR] $1${NC}"; exit 1; }

# 基础路径/用户配置
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
INVOKER_USER="$(id -un)"
PY_CANDIDATES=("python3.10" "python3.11" "python3" "python")

info "项目根目录：$PROJECT_DIR"
info "检查Python >= 3.10 环境..."

# 步骤1：检查Python版本
PYTHON_CMD=""
for cmd in "${PY_CANDIDATES[@]}"; do
  if command -v "$cmd" >/dev/null 2>&1; then
    if "$cmd" - <<'PYTEST' >/dev/null 2>&1
import sys
sys.exit(0 if sys.version_info >= (3,10) else 2)
PYTEST
    then
      PYTHON_CMD="$cmd"
      break
    fi
  fi
done
[ -z "$PYTHON_CMD" ] && error "未找到Python >= 3.10，请先安装"

PY_VERSION_FULL="$("$PYTHON_CMD" --version 2>&1)"
PY_VERSION_SHORT=$(echo "$PY_VERSION_FULL" | awk '{print $2}' | cut -d. -f1-2)
info "使用Python：$(command -v "$PYTHON_CMD") ($PY_VERSION_FULL)"

# 步骤2：安装Debian/Ubuntu系统依赖（python3.x-venv）
if command -v apt >/dev/null 2>&1; then
  VENV_PACKAGE="python${PY_VERSION_SHORT}-venv"
  info "检查系统依赖 ${VENV_PACKAGE}..."

  if ! dpkg -s "$VENV_PACKAGE" >/dev/null 2>&1; then
    warn "安装 ${VENV_PACKAGE}..."
    apt update -y >/dev/null 2>&1 || warn "apt缓存更新失败"
    apt install -y "$VENV_PACKAGE" || error "安装 ${VENV_PACKAGE} 失败"
  fi
  info "${VENV_PACKAGE} 已安装 ✅"
else
  warn "非Debian/Ubuntu系统，跳过venv包检查"
fi

# 步骤3：创建/重建虚拟环境
VENV_DIR="$PROJECT_DIR/.venv"
VENV_PY="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

[ -d "$VENV_DIR" ] && { info "删除旧虚拟环境：$VENV_DIR"; rm -rf "$VENV_DIR"; }
info "创建虚拟环境：$VENV_DIR..."
"$PYTHON_CMD" -m venv "$VENV_DIR" || error "虚拟环境创建失败"

# 兜底安装pip
if [ ! -x "$VENV_PIP" ]; then
  info "手动安装pip到虚拟环境..."
  "$VENV_PY" -m ensurepip --upgrade || error "pip安装失败"
fi
[ ! -x "$VENV_PIP" ] && error "虚拟环境中无pip可执行文件"
info "虚拟环境创建完成 ✅"

# 步骤4：升级pip到最新版
get_trusted_host() { echo "$1" | awk -F'//' '{print $2}' | awk -F'/' '{print $1}'; }
upgrade_pip_safely() {
  local mirror=$1 host=$(get_trusted_host "$mirror")
  info "升级pip（源：$mirror）..."
  "$VENV_PIP" install --upgrade --force-reinstall pip -i "$mirror" --trusted-host "$host" --no-cache-dir && return 0
  warn "pip升级失败（源：$mirror）"
  return 1
}

if ! upgrade_pip_safely "$PYPI_MIRROR_MAIN"; then
  upgrade_pip_safely "$PYPI_MIRROR_FALLBACK" || error "所有源升级pip失败，请检查网络"
fi
PIP_VERSION=$("$VENV_PIP" --version | awk '{print $2}')
info "pip已升级到：$PIP_VERSION"

# 步骤5：安装setuptools + wheel
info "安装setuptools + wheel..."
if ! "$VENV_PIP" install --upgrade setuptools wheel -i "$PYPI_MIRROR_MAIN" --trusted-host "$(get_trusted_host "$PYPI_MIRROR_MAIN")"; then
  warn "切换阿里云源安装wheel..."
  "$VENV_PIP" install --upgrade setuptools wheel -i "$PYPI_MIRROR_FALLBACK" --trusted-host "$(get_trusted_host "$PYPI_MIRROR_FALLBACK")" || error "wheel安装失败"
fi

# 步骤6：安装项目依赖
REQ_FILE="$PROJECT_DIR/requirements.txt"
if [ -f "$REQ_FILE" ]; then
  info "安装项目依赖（源：$PYPI_MIRROR_MAIN）..."
  if ! "$VENV_PIP" install -r "$REQ_FILE" -i "$PYPI_MIRROR_MAIN" --trusted-host "$(get_trusted_host "$PYPI_MIRROR_MAIN")"; then
    warn "切换阿里云源安装依赖..."
    "$VENV_PIP" install -r "$REQ_FILE" -i "$PYPI_MIRROR_FALLBACK" --trusted-host "$(get_trusted_host "$PYPI_MIRROR_FALLBACK")" || warn "部分依赖安装失败"
  fi
else
  warn "无requirements.txt，跳过依赖安装"
fi

# 依赖
pip install uvicorn fastapi

# 步骤7：创建并启动systemd服务
SERVICE_NAME="mcp-server.service"
SERVICE_PATH="/etc/systemd/system/$SERVICE_NAME"
EXEC_START="$VENV_PY $PROJECT_DIR/mcp_server.py"

if command -v systemctl >/dev/null 2>&1; then
  SERVICE_UNIT="[Unit]
Description=mcp-server 服务
After=network.target

[Service]
Type=simple
User=${INVOKER_USER}
WorkingDirectory=${PROJECT_DIR}
ExecStart=${EXEC_START}
Restart=on-failure
RestartSec=5s
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target"

  info "创建systemd服务文件：$SERVICE_PATH..."
  TMP_UNIT="$(mktemp)"
  printf "%s" "$SERVICE_UNIT" > "$TMP_UNIT"
  SUDO="[ $(id -u) -ne 0 ] && echo sudo"
  eval $SUDO mv "$TMP_UNIT" "$SERVICE_PATH"
  eval $SUDO chown root:root "$SERVICE_PATH"
  eval $SUDO chmod 644 "$SERVICE_PATH"

  info "重载systemd配置..."
  eval $SUDO systemctl daemon-reload
  info "启用并启动服务：$SERVICE_NAME..."
  eval $SUDO systemctl enable --now "$SERVICE_NAME"

  info "服务状态："
  eval $SUDO systemctl status --no-pager "$SERVICE_NAME" || true
else
  warn "无systemctl，跳过服务创建"
  info "手动启动命令：$EXEC_START"
fi

info "==================== 初始化完成 ===================="
info "虚拟环境：$VENV_DIR | 服务名：$SERVICE_NAME"
info "日志查看：sudo journalctl -u $SERVICE_NAME -f"
info "服务重启：sudo systemctl restart $SERVICE_NAME"