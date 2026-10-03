"""手柄守护线程：读设备 → 映射 → 按当前模式分发。

三种模式（由 Hub 按阶段切换）：
    hub      Hub 菜单里：十字键/左摇杆选，A 确认，B 返回
    launcher 官方启动器里：右摇杆当鼠标，A 左键，B 右键，Start 回车，X Esc
    off      游戏运行中：完全放空，交给游戏自己的手柄支持
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from .cursor import make_cursor
from .jsdevice import open_all, read_many
from .mapper import Mapper
from .profile import Profile, default_profile_path

MODE_OFF = "off"
MODE_HUB = "hub"
MODE_LAUNCHER = "launcher"


class InputDaemon(threading.Thread):
    def __init__(
        self,
        on_intent: Callable[[str, int], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        profile: Profile | None = None,
        device_hint: list[str] | None = None,
        backend: str = "xdotool",
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__(daemon=True, name="yanwo-input")
        self.log = logger or logging.getLogger("yanwo.input")
        self.on_intent = on_intent
        self.on_status = on_status
        self.profile = profile or Profile.load(default_profile_path())
        self.device_hint = device_hint or []
        self.cursor = make_cursor(backend)
        self.mode = MODE_HUB
        self.connected = False
        self.ever_active = False
        self.device_name = ""
        self.enabled = True
        # 采样/刷新周期：5ms ≈ 200Hz。这是"光标丝滑"的关键（配合 XTest 后端）
        self.poll_s = 0.005
        self._stop = threading.Event()

    # ---------- 对外 ----------
    def set_mode(self, mode: str) -> None:
        if mode != self.mode:
            self.log.info("输入模式 -> %s", mode)
        self.mode = mode

    def status(self) -> str:
        if not self.enabled:
            return "手柄：已禁用"
        if not self.connected:
            return "手柄：未找到设备（/dev/input/js*）"
        if not self.ever_active:
            return f"手柄：{self.device_name}　（动一下手柄/摇杆即可接管）"
        return f"手柄：✅ {self.device_name}"

    def stop(self) -> None:
        self._stop.set()

    # ---------- 内部 ----------
    def _notify_status(self) -> None:
        if self.on_status:
            try:
                self.on_status(self.status())
            except Exception:  # noqa: BLE001
                pass

    def _dispatch(self, intents: list[tuple[str, int]]) -> None:
        mode = self.mode
        for kind, val in intents:
            if mode == MODE_OFF:
                continue
            if mode == MODE_HUB:
                if self.on_intent:
                    try:
                        self.on_intent(kind, val)
                    except Exception:  # noqa: BLE001
                        self.log.exception("处理手柄意图失败")
            else:
                self._launcher_action(kind, val)

    def _launcher_action(self, kind: str, val: int) -> None:
        if kind == "confirm":
            self.cursor.click(1)
        elif kind == "back":
            self.cursor.click(3)
        elif kind == "third":
            self.cursor.key("Escape")
        elif kind == "start":
            self.cursor.key("Return")
        elif kind == "nav":
            self.cursor.key("Up" if val < 0 else "Down")

    def run(self) -> None:
        """同时监听所有 js 设备，只转发"当前活跃"那一个的事件。

        为什么要这样：Steam Input 可能用 EVIOCGRAB 抓住物理手柄（这时读它收不到
        任何事件），而它自己造一个虚拟手柄（你机器上是 js2/js3）。所以我们不写死
        设备，而是谁真的出事件就跟谁，并在需要时自动切换。
        """
        while not self._stop.is_set():
            if not self.enabled:
                time.sleep(0.5)
                continue
            devs = open_all()
            if not devs:
                self.connected = False
                self.log.warning("没找到手柄设备（/dev/input/js*）")
                self._notify_status()
                if self._stop.wait(10.0):
                    return
                continue

            self.log.info("监听到 %d 个手柄设备: %s",
                          len(devs), ", ".join(f"{d.path}={d.name}" for d in devs))
            # 先把状态显示出来（还没动过手柄时），动一下就会切换到"活跃"设备
            self.connected = True
            self.device_name = f"{devs[0].path} {devs[0].name}"
            self._notify_status()
            mapper = Mapper(self.profile)
            active = None
            active_last = 0.0
            last = time.time()
            try:
                while not self._stop.is_set():
                    now = time.time()
                    dt = min(0.1, now - last)
                    last = now
                    # 一次 select 覆盖所有设备（别每台各等一次，否则光标会一顿一顿）
                    batch = [
                        (d, ev) for d, ev in read_many(devs, self.poll_s) if not ev.is_init
                    ]

                    if batch:
                        in_batch = {d for d, _ in batch}
                        if active not in in_batch and (
                            active is None or now - active_last > 1.0
                        ):
                            newdev = batch[-1][0]
                            if newdev is not active:
                                self.log.info("手柄输入切换到: %s %s", newdev.path, newdev.name)
                                mapper = Mapper(self.profile)
                                active = newdev
                        active_last = now

                    for d, ev in batch:
                        if d is not active:
                            continue
                        self._dispatch(mapper.feed(ev))

                    if active is not None:
                        self.ever_active = True
                        if not self.connected or self.device_name != f"{active.path} {active.name}":
                            self.connected = True
                            self.device_name = f"{active.path} {active.name}"
                            self._notify_status()
                        nav = mapper.nav_step(allow_left_stick=self.mode != MODE_LAUNCHER)
                        if nav:
                            self._dispatch([("nav", nav)])
                        if self.mode == MODE_LAUNCHER:
                            vx, vy = mapper.cursor_velocity()
                            if vx or vy:
                                self.cursor.move(
                                    vx * self.profile.speed_px_s * dt,
                                    vy * self.profile.speed_px_s * dt,
                                )
            finally:
                for d in devs:
                    d.close()
                self.connected = False
                self._notify_status()
