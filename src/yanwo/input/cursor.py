"""光标/按键输出后端。

P2 默认后端是 xdotool：**不需要 root**（用户明确要求，且以后上架 Steam 更不能要）。
将来如果需要跨 Wayland 的通用方案，可以再实现一个 uinput 后端（需一次性 udev 规则）。
"""
from __future__ import annotations

import logging
import os
import subprocess

log = logging.getLogger("yanwo.input")


class XdotoolCursor:
    name = "xdotool"

    def __init__(self) -> None:
        self._dx = 0.0
        self._dy = 0.0

    def _run(self, argv: list[str]) -> None:
        try:
            subprocess.run(argv, capture_output=True, timeout=3)
        except Exception as e:  # noqa: BLE001
            log.debug("xdotool 失败 %s: %s", argv, e)

    def move(self, dx: float, dy: float) -> None:
        """累计小数像素，够 1px 才真正调用 xdotool。"""
        self._dx += dx
        self._dy += dy
        ix, iy = int(self._dx), int(self._dy)
        if ix == 0 and iy == 0:
            return
        self._dx -= ix
        self._dy -= iy
        self._run(["xdotool", "mousemove_relative", "--", str(ix), str(iy)])

    def click(self, button: int = 1) -> None:
        self._run(["xdotool", "click", str(button)])

    def key(self, key: str) -> None:
        self._run(["xdotool", "key", key])

    def scroll(self, direction: int, times: int = 3) -> None:
        btn = "4" if direction < 0 else "5"
        for _ in range(max(1, times)):
            self._run(["xdotool", "click", btn])


class NullCursor:
    name = "none"

    def move(self, dx: float, dy: float) -> None:  # noqa: D102
        pass

    def click(self, button: int = 1) -> None:  # noqa: D102
        pass

    def key(self, key: str) -> None:  # noqa: D102
        pass

    def scroll(self, direction: int, times: int = 3) -> None:  # noqa: D102
        pass


def make_cursor(backend: str = "xdotool"):
    if backend == "xdotool" and os.environ.get("DISPLAY"):
        return XdotoolCursor()
    return NullCursor()
