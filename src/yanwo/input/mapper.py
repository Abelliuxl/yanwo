"""原始手柄事件 → 语义意图（Intent）。

Intent 是 (kind, value) 的二元组，kind ∈
    nav / confirm / back / third / fourth / start / select / hat
由 daemon 决定在不同阶段怎么用（Hub 里是菜单导航，启动器里是鼠标/键盘）。
"""
from __future__ import annotations

import time

from .jsdevice import RawEvent, TYPE_AXIS, TYPE_BUTTON
from .profile import Profile

NAV = "nav"
HAT = "hat"


class Mapper:
    def __init__(self, profile: Profile) -> None:
        self.p = profile
        self.axes: dict[int, int] = {}
        self.buttons: set[int] = set()
        self._hat_y = 0
        self._hat_x = 0
        self._nav_last_emit = 0.0
        self._nav_active = 0  # -1/0/1

    # ---------- 事件 ----------
    def feed(self, ev: RawEvent) -> list[tuple[str, int]]:
        out: list[tuple[str, int]] = []
        if ev.type == TYPE_AXIS:
            self.axes[ev.number] = ev.value
            if ev.number == self.p.axis_hat_y:
                self._hat_y = ev.value
            elif ev.number == self.p.axis_hat_x:
                self._hat_x = ev.value
            return out
        if ev.type != TYPE_BUTTON:
            return out

        pressed = ev.value != 0
        num = ev.number
        if pressed:
            if num in self.buttons:
                return out  # 忽略重复按下
            self.buttons.add(num)
        else:
            self.buttons.discard(num)
            return out

        p = self.p
        if num == p.btn_confirm:
            out.append(("confirm", 1))
        elif num == p.btn_back:
            out.append(("back", 1))
        elif num == p.btn_third:
            out.append(("third", 1))
        elif num == p.btn_fourth:
            out.append(("fourth", 1))
        elif num == p.btn_start:
            out.append(("start", 1))
        elif num == p.btn_select:
            out.append(("select", 1))
        else:
            out.append(("button", num))
        return out

    # ---------- 光标 ----------
    def _norm(self, v: int) -> float:
        dz = self.p.deadzone
        if abs(v) <= dz:
            return 0.0
        s = (abs(v) - dz) / max(1, 32767 - dz)
        return s if v > 0 else -s

    def cursor_velocity(self) -> tuple[float, float]:
        """归一化速度 (-1..1)。左右摇杆都认，谁推得多用谁（左摇杆为主）。"""
        best = (0.0, 0.0)
        best_mag = 0.0
        for ax, ay in (
            (self.p.axis_move_x, self.p.axis_move_y),      # 左摇杆（主）
            (self.p.axis_move_x2, self.p.axis_move_y2),    # 右摇杆（副）
        ):
            nx = self._norm(self.axes.get(ax, 0))
            ny = self._norm(self.axes.get(ay, 0))
            mag = max(abs(nx), abs(ny))
            if mag > best_mag:
                best_mag = mag
                best = (nx, ny)
        if best_mag == 0.0:
            return 0.0, 0.0
        f = self.p.accel + (1.0 - self.p.accel) * best_mag
        return best[0] * f, best[1] * f

    # ---------- 十字键导航（带按住重复） ----------
    def nav_step(self, allow_left_stick: bool = True) -> int:
        """返回 -1/0/+1（上/不动/下），按住按 nav_repeat_ms 重复。

        allow_left_stick：Hub 菜单里允许左摇杆导航；官方启动器阶段要关掉
        （那时左摇杆是"移光标"，否则一边移一边触发方向键）。
        """
        want = 0
        if self._hat_y <= -16000:
            want = -1
        elif self._hat_y >= 16000:
            want = 1
        if want == 0 and allow_left_stick:
            ly = self.axes.get(self.p.axis_move_y, 0)
            if ly <= -24000:
                want = -1
            elif ly >= 24000:
                want = 1

        now = time.time()
        if want == 0:
            self._nav_active = 0
            return 0
        if want != self._nav_active:
            self._nav_active = want
            self._nav_last_emit = now
            return want
        if (now - self._nav_last_emit) * 1000 >= self.p.nav_repeat_ms:
            self._nav_last_emit = now
            return want
        return 0

    def hat_state(self) -> tuple[int, int]:
        return self._hat_x, self._hat_y
