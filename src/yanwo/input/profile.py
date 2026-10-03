"""手柄映射配置（profile）。

默认值对应 Linux joystick API 下的 Xbox 360 兼容手柄（xpad / XInput 接收器）：
  轴: 0=左摇杆X 1=左摇杆Y 3=右摇杆X 4=右摇杆Y 6=十字键X 7=十字键Y
  键: 0=A 1=B 2=X 3=Y 4=LB 5=RB 6=Back 7=Start
如果你的是别的布局，用 `yanwo calibrate` 看编号，然后改 input/profiles/*.toml。
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from ..paths import REPO_ROOT

PROFILE_DIR = REPO_ROOT / "input" / "profiles"


@dataclass
class Profile:
    name: str = "xbox360"
    # 轴编号
    axis_move_x: int = 3
    axis_move_y: int = 4
    axis_hat_x: int = 6
    axis_hat_y: int = 7
    # 键编号
    btn_confirm: int = 0    # A
    btn_back: int = 1       # B
    btn_third: int = 2      # X
    btn_fourth: int = 3     # Y
    btn_start: int = 7      # Start
    btn_select: int = 6     # Back/Select
    # 光标手感
    deadzone: int = 6000          # 摇杆死区（满量程 32767）
    speed_px_s: int = 1300        # 满推时每秒移动像素
    accel: float = 0.35           # 低偏移时的慢速系数
    scroll_step: int = 3          # 扳机/键一次滚轮的格数
    nav_repeat_ms: int = 320      # 十字键按住时的重复间隔

    extra: dict = field(default_factory=dict)

    @staticmethod
    def load(path: Path | None) -> "Profile":
        p = Profile()
        if path and path.is_file():
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            for k, v in (data.get("axes", {}) or {}).items():
                if hasattr(p, f"axis_{k}"):
                    setattr(p, f"axis_{k}", int(v))
            for k, v in (data.get("buttons", {}) or {}).items():
                if hasattr(p, f"btn_{k}"):
                    setattr(p, f"btn_{k}", int(v))
            for k, v in (data.get("feel", {}) or {}).items():
                if hasattr(p, k):
                    setattr(p, k, type(getattr(p, k))(v))
            p.name = data.get("name", p.name)
        return p

    def to_toml(self) -> str:
        return (
            f'name = "{self.name}"\n\n'
            "[axes]\n"
            f"move_x = {self.axis_move_x}\n"
            f"move_y = {self.axis_move_y}\n"
            f"hat_x = {self.axis_hat_x}\n"
            f"hat_y = {self.axis_hat_y}\n\n"
            "[buttons]\n"
            f"confirm = {self.btn_confirm}\n"
            f"back = {self.btn_back}\n"
            f"third = {self.btn_third}\n"
            f"fourth = {self.btn_fourth}\n"
            f"start = {self.btn_start}\n"
            f"select = {self.btn_select}\n\n"
            "[feel]\n"
            f"deadzone = {self.deadzone}\n"
            f"speed_px_s = {self.speed_px_s}\n"
            f"accel = {self.accel}\n"
        )


def default_profile_path() -> Path | None:
    cands = sorted(PROFILE_DIR.glob("*.toml")) if PROFILE_DIR.is_dir() else []
    return cands[0] if cands else None
