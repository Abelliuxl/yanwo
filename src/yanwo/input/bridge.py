"""输入桥（P2 占位）。

目标：把"不支持手柄"的启动器（比如燕云的官方启动器）变成"有个光标能点"。

设计约定（P2 实现，接口先钉住）：
  * 桥由 Hub 掌管，**只在需要它的阶段打开**：
        [bridge] active_when = ["hub", "launcher"]     # 游戏运行时关掉，交给游戏自己的手柄支持
  * 输出后端可插拔：xdotool(X11) / uinput(未来，需一次性 udev 规则) / steam-input(委托 Valve)
  * 目标后端默认 xdotool：**不需要 root**（用户已确认不要 root，上架 Steam 更不能要）
  * 只在目标窗口是前台时才注入，避免玩游戏时乱动视角。

现在只有一个空实现，调用它不会做任何事。
"""
from __future__ import annotations

import logging

log = logging.getLogger("yanwo.bridge")


class Bridge:
    def __init__(self, profile: str = "cursor_click", backend: str = "xdotool", enable: bool = False):
        self.profile = profile
        self.backend = backend
        self.enabled = enable
        self._thread = None

    def start(self) -> None:
        if not self.enabled:
            log.info("输入桥未启用（P2 待实现）")
            return
        log.warning("输入桥启用请求被忽略：本版本还没实现（见 docs/ROADMAP.md）")

    def stop(self) -> None:
        pass
