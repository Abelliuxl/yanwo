"""调用 Steam 原生浮动键盘，并读取 Steam 界面的输入接管状态。"""
from __future__ import annotations

import ctypes
import json
import queue
import threading
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
        self.control_display = None
        self._input_atom = 0
        self._requested_until = 0.0
        self._retry_at = 0.0
        self.requested = False
        self.focus_mode = 0

    def _command(self, url):
        steam = shutil.which("steam")
        if steam is None:
            raise RuntimeError("没有找到 Steam，无法打开原生键盘")
        result = subprocess.run([steam, url], capture_output=True, timeout=5)
        if result.returncode:
            raise RuntimeError("Steam 未接受虚拟键盘请求")

    def focused_edit(self, recipe):
        """检测点击后的编辑控件，准备其输入焦点；不读取文本内容。"""
        return self._field_helper(recipe)

    def click_field(self, recipe, point):
        # Steam owns pointer events while its keyboard is open. Deliver this
        # explicit field re-selection to MPAY itself, never to the overlay.
        return self._field_helper(recipe, ["--click-field", str(int(point[0])), str(int(point[1]))])

    def _field_helper(self, recipe, args=()):
        step = next((s for s in recipe.steps if s.kind == "wine"), None)
        if step is None:
            return None
        helper = Path(__file__).with_name("native") / "focused-edit.exe"
        # Wine keeps the guard child's inherited Unix pipe open. Read the JSON
        # line immediately so opening the keyboard overlaps the live focus guard.
        process = subprocess.Popen([str(step.get("wine")), str(helper), *args],
                                   env=build_env(step, recipe), stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, text=True)
        result = queue.Queue(maxsize=1)

        def collect():
            try:
                result.put(process.stdout.readline())
                process.wait()
            finally:
                process.stdout.close()

        threading.Thread(target=collect, daemon=True).start()
        try:
            field = json.loads(result.get(timeout=3))
        except (queue.Empty, ValueError):
            try:
                process.kill()
            except ProcessLookupError:
                pass
            return None
        if not field or field["w"] <= 0 or field["h"] <= 0:
            return None
        return field

    def open(self, field=None):
        url = self.OPEN_URL
        if field:
            url = ("steam://open/keyboard?XPosition={x}&YPosition={y}"
                   "&Width={w}&Height={h}&Mode={mode}").format(**field)
        # Clicking a field again while the keyboard is open only restores that
        # field. Reopening Steam's overlay causes another focus transition.
        if self.requested:
            return
        self._command(url)
        self.requested = True
        self._requested_until = time.monotonic() + 3.0

    def close(self):
        if self.requested:
            self._command(self.CLOSE_URL)
        self.requested = False
        self._requested_until = 0.0

    def input_taken(self):
        """读取 Steam 输入模式：2 为浮动键盘，其他非零值为菜单/覆盖界面。"""
        now = time.monotonic()
        if self._conn is None and now >= self._retry_at:
            self._retry_at = now + 10.0
            control = GamescopeFocus()
            if control.discover():
                self.control_display = control.display
                self._conn = _X(control.display)
                self._input_atom = self._conn.lib.XInternAtom(
                    ctypes.c_void_p(self._conn.dpy), b"STEAM_INPUT_FOCUS", 0)
        mode = 0
        if self._conn:
            for win in self._conn.list():
                if not win.mapped:
                    continue
                raw = self._conn._raw_prop(win.wid, self._input_atom)
                value = int.from_bytes(raw[:4], "little") if raw else 0
                if value:
                    # A full Steam menu takes priority over the floating keyboard.
                    if value != 2:
                        mode = value
                        break
                    mode = 2
        self.focus_mode = mode
        active = bool(mode)
        # 给 Steam 响应请求的时间；键盘关闭后由输入焦点状态自动恢复。
        if active:
            self._requested_until = 0.0
        if not active and now >= self._requested_until:
            self.requested = False
        return active
