"""光标/按键输出后端。

P2 默认后端是 xdotool：**不需要 root**（用户明确要求，且以后上架 Steam 更不能要）。
将来如果需要跨 Wayland 的通用方案，可以再实现一个 uinput 后端（需一次性 udev 规则）。
"""
from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import threading

log = logging.getLogger("yanwo.input")


class XTestCursor:
    """直接调 libX11/libXtst 的 XTest 扩展。

    比 spawn `xdotool` 快几个数量级（微秒 vs 1.5ms/进程），
    也不会每秒拉起上百个进程 —— 这是"光标丝滑"的关键。
    """

    name = "xtest"

    def __init__(self, display: str | None = None) -> None:
        self._lock = threading.Lock()
        self._dx = 0.0
        self._dy = 0.0
        self._x11 = ctypes.CDLL("libX11.so.6")
        self._xtst = ctypes.CDLL("libXtst.so.6")
        self._x11.XInitThreads()
        self._x11.XOpenDisplay.restype = ctypes.c_void_p
        self._x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self._x11.XFlush.argtypes = [ctypes.c_void_p]
        self._x11.XStringToKeysym.restype = ctypes.c_ulong
        self._x11.XStringToKeysym.argtypes = [ctypes.c_char_p]
        self._x11.XKeysymToKeycode.restype = ctypes.c_ubyte
        self._x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self._xtst.XTestFakeRelativeMotionEvent.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_ulong,
        ]
        self._xtst.XTestFakeButtonEvent.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong,
        ]
        self._xtst.XTestFakeKeyEvent.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong,
        ]
        self._dpy = self._x11.XOpenDisplay(display.encode() if display else None)
        if not self._dpy:
            raise RuntimeError("XOpenDisplay 失败")

    def _flush(self) -> None:
        self._x11.XFlush(ctypes.c_void_p(self._dpy))

    def move(self, dx: float, dy: float) -> None:
        self._dx += dx
        self._dy += dy
        ix, iy = int(self._dx), int(self._dy)
        if ix == 0 and iy == 0:
            return
        self._dx -= ix
        self._dy -= iy
        with self._lock:
            self._xtst.XTestFakeRelativeMotionEvent(
                ctypes.c_void_p(self._dpy), ix, iy, 0
            )
            self._flush()

    def click(self, button: int = 1) -> None:
        with self._lock:
            self._xtst.XTestFakeButtonEvent(ctypes.c_void_p(self._dpy), button, 1, 0)
            self._xtst.XTestFakeButtonEvent(ctypes.c_void_p(self._dpy), button, 0, 0)
            self._flush()

    def key(self, key: str) -> None:
        ks = self._x11.XStringToKeysym(key.encode())
        if not ks:
            return
        kc = self._x11.XKeysymToKeycode(ctypes.c_void_p(self._dpy), ks)
        if not kc:
            return
        with self._lock:
            self._xtst.XTestFakeKeyEvent(ctypes.c_void_p(self._dpy), kc, 1, 0)
            self._xtst.XTestFakeKeyEvent(ctypes.c_void_p(self._dpy), kc, 0, 0)
            self._flush()

    def scroll(self, direction: int, times: int = 3) -> None:
        btn = 4 if direction < 0 else 5
        for _ in range(max(1, times)):
            self.click(btn)


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


def make_cursor(backend: str = "auto"):
    """优先 XTest（快），失败退回 xdotool，再不行就空实现。"""
    if not os.environ.get("DISPLAY"):
        return NullCursor()
    if backend in ("auto", "xtest"):
        try:
            c = XTestCursor(os.environ.get("DISPLAY"))
            log.info("光标后端: XTest（直连 X11，无进程开销）")
            return c
        except Exception as e:  # noqa: BLE001
            log.warning("XTest 后端不可用(%s)，退回 xdotool", e)
    if backend in ("auto", "xdotool", "xtest"):
        log.info("光标后端: xdotool")
        return XdotoolCursor()
    return NullCursor()
