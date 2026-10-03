#!/usr/bin/env bash
# 跑测试（无需图形；不需要真的起游戏）
set -euo pipefail
HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
cd "$HERE"
export PYTHONPATH="$HERE/src${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m unittest discover -s tests -v
