#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

is_wsl=0
if grep -qiE "(microsoft|wsl)" /proc/version 2>/dev/null; then
  is_wsl=1
fi

open_url() {
  local url="$1"
  if [ "${IT_OPEN_BROWSER:-1}" != "1" ]; then
    echo "[INFO] 已禁用自动打开浏览器。请手动访问: $url"
    return 0
  fi
  # WSL: prioritize Windows-side browser launchers.
  if [ "$is_wsl" -eq 1 ]; then
    # Use exactly one launcher in WSL to avoid delayed duplicate open.
    if [ -x /mnt/c/Windows/explorer.exe ]; then
      /mnt/c/Windows/explorer.exe "$url" >/dev/null 2>&1 && return 0
    fi
    echo "[WARN] WSL 自动打开失败（未找到 explorer.exe）。请手动打开: $url"
    return 1
  fi

  # Native Linux/macOS.
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 && return 0
  elif command -v open >/dev/null 2>&1; then
    open "$url" >/dev/null 2>&1 && return 0
  fi
  echo "[WARN] 未找到可用的浏览器启动命令。请手动打开: $url"
  return 1
}

if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] 未检测到 docker 命令。"
  if [ "$is_wsl" -eq 1 ]; then
    echo "你当前在 WSL。请在 Windows 安装 Docker Desktop，并在 Docker Desktop -> Settings -> Resources -> WSL Integration 打开当前发行版。"
  else
    echo "请先安装 Docker Desktop (Windows/macOS) 或 Docker Engine (Linux)。"
  fi
  read -r -p "是否打开 Docker 下载页面? [Y/n] " ans
  ans="${ans:-Y}"
  if [[ "$ans" =~ ^[Yy]$ ]]; then
    open_url "https://www.docker.com/products/docker-desktop/"
  fi
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  DCMD="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DCMD="docker-compose"
else
  echo "[ERROR] 未找到 docker compose 命令。"
  exit 1
fi

$DCMD version >/dev/null 2>&1 || {
  echo "[ERROR] docker compose 不可用。请检查 Docker 安装。"
  exit 1
}

if ! docker info >/dev/null 2>&1; then
  echo "[ERROR] Docker daemon 未就绪。请先启动 Docker Desktop / Docker 服务。"
  if [ "$is_wsl" -eq 1 ]; then
    echo "WSL 提示：请在 Windows 启动 Docker Desktop，并确认开启 WSL Integration。"
  fi
  exit 1
fi

$DCMD up -d --build

echo "Interview Trainer 已启动: http://localhost:8000"
open_url "http://localhost:8000"
