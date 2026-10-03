"""项目内的标准路径。所有路径都从这里取，别在别处硬编码。"""
from __future__ import annotations

import os
from pathlib import Path

# src/yanwo/paths.py -> 仓库根
REPO_ROOT = Path(__file__).resolve().parents[2]

RECIPES_DIR = Path(os.environ.get("YANWO_RECIPES_DIR", REPO_ROOT / "recipes"))
STATE_DIR = Path(os.environ.get("YANWO_STATE_DIR", REPO_ROOT / "state"))
LOG_DIR = Path(os.environ.get("YANWO_LOG_DIR", REPO_ROOT / "logs"))

for _d in (STATE_DIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

HOME = Path.home()

# GE-Proton 的默认位置（配方里可以覆盖）
DEFAULT_PROTON_DIR = HOME / ".local/share/Steam/compatibilitytools.d/GE-Proton10-32"
