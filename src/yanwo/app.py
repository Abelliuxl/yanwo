"""Hub 应用：把配方列表、UI、会话串起来。

信号处理：Steam 点"停止"会向我们发 SIGTERM —— 我们把请求转给当前会话，
让它走"先优雅关窗、再整组清理"的收尾流程，而不是被硬杀。
"""
from __future__ import annotations

import logging
import signal
import threading

from .core.session import Phase, Session
from .input.daemon import InputDaemon
from .log import get_logger
from .recipe import Recipe
from .ui.text_menu import TextMenuUI


class HubApp:
    def __init__(self, recipes: list[Recipe], fullscreen: bool = False, ui=None) -> None:
        self.log: logging.Logger = get_logger("yanwo.app")
        self.recipes = list(recipes)
        self.session: Session | None = None
        self._quit = False
        self.ui = ui if ui is not None else TextMenuUI(
            self._game_list(), self._on_launch, fullscreen=fullscreen
        )
        # 手柄桥：Hub 菜单和官方启动器阶段都靠它
        self.input = InputDaemon(
            on_intent=self._on_intent, on_status=self._on_pad_status, logger=self.log
        )
        try:
            self.input.start()
        except Exception:  # noqa: BLE001
            self.log.exception("启动手柄桥失败")
        self._install_signals()

    # ---------- 内部 ----------
    def _game_list(self) -> list[tuple[str, str]]:
        return [(r.name, r.subtitle) for r in self.recipes]

    def _install_signals(self) -> None:
        def handler(signum, _frame):  # noqa: ANN001
            self.log.info("收到信号 %s，准备退出", signum)
            if self.session:
                self.session.request_stop(f"signal:{signum}")
            self._quit = True

        for s in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(s, handler)
            except ValueError:
                pass  # 非主线程时忽略

    # ---------- 手柄 ----------
    def _on_intent(self, kind: str, val: int) -> None:
        ui = self.ui
        if kind == "nav" and hasattr(ui, "move_by"):
            ui.move_by(val)
        elif kind == "confirm" and hasattr(ui, "activate"):
            ui.activate()
        elif kind == "back":
            if self.session and self.session.phase not in (Phase.IDLE, Phase.DONE):
                self.log.info("手柄 B：结束当前游戏会话")
                self.session.request_stop("gamepad-back")
            elif hasattr(ui, "request_quit"):
                ui.request_quit()

    def _on_pad_status(self, text: str) -> None:
        if hasattr(self.ui, "set_pad_status"):
            self.ui.set_pad_status(text)

    def _on_input_mode(self, mode: str) -> None:
        self.input.set_mode(mode)

    def _on_launch(self, idx: int) -> None:
        if not (0 <= idx < len(self.recipes)):
            return
        if self.session and self.session.phase not in (Phase.IDLE, Phase.DONE):
            self.log.info("已有会话在运行，忽略本次启动请求")
            return
        recipe = self.recipes[idx]
        self.log.info("启动：%s (%s)", recipe.name, recipe.id)
        self.session = Session(
            recipe, self.ui, self.log, on_input_mode=self._on_input_mode
        )
        self.session.clicker = self.input.cursor  # 供窗口规则里的 click 动作使用
        threading.Thread(
            target=self.session.run, daemon=True, name=f"session-{recipe.id}"
        ).start()

    def _tick(self) -> None:
        if self._quit:
            if self.session:
                self.session.request_stop("quit")
            self.ui.destroy()
            return
        root = getattr(self.ui, "root", None)
        if root is not None:
            root.after(300, self._tick)

    # ---------- 对外 ----------
    def run(self) -> None:
        root = getattr(self.ui, "root", None)
        if root is not None:
            root.after(300, self._tick)
        self.ui.run()

    def shutdown(self) -> None:
        self._quit = True
        try:
            self.input.stop()
        except Exception:  # noqa: BLE001
            pass
        if self.session:
            self.session.request_stop("shutdown")
            self.session.cleanup()
