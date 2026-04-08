#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if docker compose version >/dev/null 2>&1; then
  docker compose down
elif command -v docker-compose >/dev/null 2>&1; then
  docker-compose down
else
  echo "[ERROR] 未找到 docker compose 命令。"
  exit 1
fi

echo "Interview Trainer 已停止。"
