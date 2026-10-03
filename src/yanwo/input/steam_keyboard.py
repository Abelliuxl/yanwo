"""调用 Steam 原生浮动键盘，并读取 Steam 界面的输入接管状态。"""
from __future__ import annotations

import ctypes
import json
from pathlib import Path
import shutil
import subprocess
import time

from ..core.gamescope import GamescopeFocus
from ..core.windows import _X
from ..core.runner import build_env


class SteamKeyboard:
    OPEN_URL = "steam://open/keyboard?XPosition=0&YPosition=0&Width=0&Height=0&Mode=0"
    CLOSE_URL = "steam://close/keyboard"

    def __init__(self):
        self._conn = None
        self._input_atom = 0
        self._requested_until = 0.0
        self._retry_at = 0.0
        self.requested = False

    def _command(self, url):
        steam = shutil.which("steam")
        if steam is None:
            raise RuntimeError("没有找到 Steam，无法打开原生键盘")
        result = subprocess.run([steam, url], capture_output=True, timeout=5)
        if result.returncode:
            raise RuntimeError("Steam 未接受虚拟键盘请求")

    def focused_edit(self, recipe):
        """查询同一 Wine 前缀中鼠标点击后得到焦点的可编辑控件，只读取几何信息。"""
        step = next((s for s in recipe.steps if s.kind == "wine"), None)
        if step is None:
            return None
        helper = Path(__file__).with_name("native") / "focused-edit.exe"
        result = subprocess.run([str(step.get("wine")), str(helper)],
                                env=build_env(step, recipe), capture_output=True,
                                text=True, timeout=3)
        if result.returncode:
            return None
        field = json.loads(result.stdout)
        if not field or field["w"] <= 0 or field["h"] <= 0:
            return None
        return field

    def open(self, field=None):
        url = self.OPEN_URL
        if field:
            url = ("steam://open/keyboard?XPosition={x}&YPosition={y}"
                   "&Width={w}&Height={h}&Mode={mode}").format(**field)
        self._command(url)
        self.requested = True
        self._requested_until = time.monotonic() + 3.0

    def close(self):
        if self.requested:
            self._command(self.CLOSE_URL)
        self.requested = False
        self._requested_until = 0.0

    def input_taken(self):
        """Steam keyboard/菜单接管输入时，让燕窝完全停止鼠标和按键注入。"""
        now = time.monotonic()
        if self._conn is None and now >= self._retry_at:
            self._retry_at = now + 10.0
            control = GamescopeFocus()
            if control.discover():
                self._conn = _X(control.display)
                self._input_atom = self._conn.lib.XInternAtom(
                    ctypes.c_void_p(self._conn.dpy), b"STEAM_INPUT_FOCUS", 0)
        active = False
        if self._conn:
            for win in self._conn.list():
                if not win.mapped:
                    continue
                raw = self._conn._raw_prop(win.wid, self._input_atom)
                if raw and int.from_bytes(raw[:4], "little"):
                    active = True
                    break
        # 给 Steam 响应请求的时间；键盘关闭后由输入焦点状态自动恢复。
        if active:
            self._requested_until = 0.0
        if not active and now >= self._requested_until:
            self.requested = False
        return active
