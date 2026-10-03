"""统一日志：文件 + stderr 各一份。"""
from __future__ import annotations

import logging
import sys

from .paths import LOG_DIR

_FMT = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")


_ROOT = "yanwo"


def get_logger(name: str = _ROOT) -> logging.Logger:
    """取 logger。handler 统一挂在父 logger "yanwo" 上，
    这样子 logger（yanwo.input / yanwo.core.xxx …）的日志也能进文件。"""
    root = logging.getLogger(_ROOT)
    if not root.handlers:
        root.setLevel(logging.DEBUG)
        fh = logging.FileHandler(LOG_DIR / "yanwo.log", encoding="utf-8")
        fh.setFormatter(_FMT)
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(_FMT)
        root.addHandler(fh)
        root.addHandler(sh)
    lg = root if name == _ROOT else logging.getLogger(name)
    lg.setLevel(logging.DEBUG)
    return lg
