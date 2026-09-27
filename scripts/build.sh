#!/usr/bin/env bash
# 打包 XingViz 扩展到 dist/
set -euo pipefail
cd "$(dirname "$0")/.."
BLENDER="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"
mkdir -p dist
"$BLENDER" --command extension validate xingviz
"$BLENDER" --command extension build --source-dir xingviz --output-dir dist
