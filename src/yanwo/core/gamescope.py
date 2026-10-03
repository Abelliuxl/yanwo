"""临时指定 gamescope 的显示窗口；窗口消失/会话结束时归还控制权。"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path


class GamescopeFocus:
    PROPERTY = "GAMESCOPECTRL_BASELAYER_WINDOW"

    def __init__(self):
        self.display: str | None = None
        self.target = 0
        self.previous = 0
        self.types: dict[int, str] = {}
        self.local_display = None
        self.local_previous = 0

    def _run(self, display, args):
        result = subprocess.run(["xprop", "-display", display, *args],
                                capture_output=True, text=True, timeout=2)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "xprop failed")
        return result.stdout

    def _get(self, display, prop):
        out = self._run(display, ["-root", prop])
        match = re.search(r"\(CARDINAL\) = (\d+)", out)
        return int(match[1]) if match else None

    def _set(self, value):
        self._run(self.display, ["-root", "-f", self.PROPERTY, "32c",
                                 "-set", self.PROPERTY, str(value)])

    def discover(self):
        # 最终画面用 root_ctx（server ID 0），不是游戏所在的 XWayland。
        for socket in sorted(Path("/tmp/.X11-unix").glob("X*")):
            display = ":" + socket.name[1:]
            try:
                if self._get(display, "GAMESCOPE_XWAYLAND_SERVER_ID") == 0:
                    self.display = display
                    return True
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                continue
        return False

    def update(self, target, dialogs=()):
        if not target:
            self.release()
            return
        if self.display is None and not self.discover():
            return  # 普通桌面 WM 无需此操作。
        current = self._get(self.display, self.PROPERTY)
        if current is None or (current and current != self.target and current != target):
            return  # Steam/其它工具已经指定了窗口，不抢它的控制权。
        if not self.target:
            self.previous = current
        game_display = os.environ.get("DISPLAY", ":0")
        if game_display != self.display:
            local = self._get(game_display, self.PROPERTY)
            if local is not None and local in (0, self.target, target):
                if self.local_display is None:
                    self.local_display, self.local_previous = game_display, local
                if local != target:
                    self._run(game_display, ["-root", "-f", self.PROPERTY, "32c",
                                             "-set", self.PROPERTY, str(target)])
        for wid in dialogs:
            out = self._run(game_display, ["-id", hex(wid), "_NET_WM_WINDOW_TYPE"])
            if wid not in self.types:
                self.types[wid] = out.split(" = ", 1)[1].strip() if " = " in out else ""
            if not out.strip().endswith(" = _NET_WM_WINDOW_TYPE_DIALOG"):
                self._run(game_display, ["-id", hex(wid), "-f", "_NET_WM_WINDOW_TYPE", "32a",
                                         "-set", "_NET_WM_WINDOW_TYPE", "_NET_WM_WINDOW_TYPE_DIALOG"])
        if current != target:
            self._set(target)
        self.target = target

    def release(self):
        if self.local_display is not None:
            if self._get(self.local_display, self.PROPERTY) == self.target:
                self._run(self.local_display, ["-root", "-f", self.PROPERTY, "32c",
                                               "-set", self.PROPERTY, str(self.local_previous)])
            self.local_display = None
        if self.target:
            if self._get(self.display, self.PROPERTY) == self.target:
                self._set(self.previous)
            self.target = 0
        game_display = os.environ.get("DISPLAY", ":0")
        for wid, original in list(self.types.items()):
            try:
                # 只恢复仍由我们设置的属性。
                out = self._run(game_display, ["-id", hex(wid), "_NET_WM_WINDOW_TYPE"])
                if out.strip().endswith(" = _NET_WM_WINDOW_TYPE_DIALOG"):
                    args = ["-id", hex(wid)]
                    if original:
                        args += ["-f", "_NET_WM_WINDOW_TYPE", "32a", "-set", "_NET_WM_WINDOW_TYPE", original]
                    else:
                        args += ["-remove", "_NET_WM_WINDOW_TYPE"]
                    self._run(game_display, args)
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                pass  # 窗口可能已随登录完成而销毁。
            self.types.pop(wid, None)
