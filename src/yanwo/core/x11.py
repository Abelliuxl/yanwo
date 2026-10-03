"""X11 小工具（xdotool / xprop 封装）。

——"先优雅关窗、再动手"这套做法来自 yysls 的踩坑：
   对网易启动器如果直接 SIGKILL，下载缓存会被判为损坏 → 重下 125G。
   所以收尾顺序永远是：发 WM_DELETE_WINDOW（等于点右上角 X）→ 等几秒 → 才 TERM/KILL。
"""
from __future__ import annotations

import os
import subprocess


def _env() -> dict[str, str]:
    e = dict(os.environ)
    e.setdefault("DISPLAY", ":0")
    return e


def _run(argv: list[str], timeout: float = 5.0) -> str:
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=_env())
        return r.stdout
    except Exception:  # noqa: BLE001
        return ""


def windows_of_pid(pid: int) -> list[str]:
    return [w for w in _run(["xdotool", "search", "--pid", str(pid)]).split() if w]


def close_windows(pids: list[int]) -> int:
    """给这些进程的窗口发关闭事件；返回窗口个数。"""
    n = 0
    for pid in pids:
        for wid in windows_of_pid(pid):
            _run(["xdotool", "windowclose", wid])
            n += 1
    return n


def active_window_pid() -> int | None:
    out = _run(["xprop", "-root", "_NET_ACTIVE_WINDOW"])
    if "0x" not in out:
        return None
    wid = out.split("0x")[-1].strip().split(",")[0]
    pid = _run(["xprop", "-id", "0x" + wid, "_NET_WM_PID"]).split("=")[-1].strip()
    return int(pid) if pid.isdigit() else None
