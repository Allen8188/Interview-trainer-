#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

OUT_DIR="dist"
PKG_ROOT="$OUT_DIR/InterviewTrainer-Windows"
ZIP_PATH="$OUT_DIR/InterviewTrainer-Windows.zip"

rm -rf "$PKG_ROOT" "$ZIP_PATH"
mkdir -p "$PKG_ROOT"

cp -r app "$PKG_ROOT"/
cp -r web "$PKG_ROOT"/
cp -r scripts "$PKG_ROOT"/
cp -r release/windows/. "$PKG_ROOT"/

find "$PKG_ROOT" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "$PKG_ROOT" -type f -name "*.pyc" -delete

cp Dockerfile "$PKG_ROOT"/
cp docker-compose.yml "$PKG_ROOT"/
cp requirements.txt "$PKG_ROOT"/
cp requirements-whisper.txt "$PKG_ROOT"/
cp README.md "$PKG_ROOT"/
cp LAUNCH.md "$PKG_ROOT"/

(cd "$OUT_DIR" && zip -r "$(basename "$ZIP_PATH")" "$(basename "$PKG_ROOT")")

echo "Built: $ZIP_PATH"
