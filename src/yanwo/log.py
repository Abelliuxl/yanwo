"""统一日志：文件 + stderr 各一份。"""
from __future__ import annotations

import logging
import sys

from .paths import LOG_DIR

_FMT = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")


def get_logger(name: str = "yanwo") -> logging.Logger:
    lg = logging.getLogger(name)
    if lg.handlers:
        return lg
    lg.setLevel(logging.DEBUG)
    fh = logging.FileHandler(LOG_DIR / "yanwo.log", encoding="utf-8")
    fh.setFormatter(_FMT)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(_FMT)
    lg.addHandler(fh)
    lg.addHandler(sh)
    return lg
