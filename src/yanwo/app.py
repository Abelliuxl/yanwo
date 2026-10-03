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
from .input.steam_keyboard import SteamKeyboard
from .log import get_logger
from .recipe import Recipe
from .ui.text_menu import TextMenuUI


class HubApp:
    def __init__(self, recipes: list[Recipe], fullscreen: bool = False, ui=None) -> None:
        self.log: logging.Logger = get_logger("yanwo.app")
        self.recipes = list(recipes)
        self.session: Session | None = None
        self._session_thread: threading.Thread | None = None
        self._quit = False
        self.steam_keyboard = SteamKeyboard()
        self._keyboard_pending = False
        self.ui = ui if ui is not None else TextMenuUI(
            self._game_list(), self._on_launch, fullscreen=fullscreen
        )
        # 手柄桥：Hub 菜单和官方启动器阶段都靠它
        self.input = InputDaemon(
            on_intent=self._on_intent, on_status=self._on_pad_status, logger=self.log
        )
        self._apply_bridge_config(None)
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

    def _apply_bridge_config(self, recipe) -> None:
        """把配方的 [bridge] 配置应用到桥（暂停组合键等）。没有配方时用默认。"""
        combo = list(getattr(recipe, "bridge_pause_combo", []) or []) if recipe else []
        self.input.pause_combo = combo
        if combo:
            self.log.info("输入桥暂停组合键: %s（按一次暂停、再按恢复）", "+".join(combo))

    # ---------- 手柄 ----------
    def _on_intent(self, kind: str, val: int) -> None:
        ui = self.ui
        if kind == "pointer_click":
            if self._keyboard_pending or self._quit:
                return
            self._keyboard_pending = True
            if hasattr(ui, "_post"):
                ui._post(lambda: ui.root.after(120, self._open_keyboard))
            else:
                self._open_keyboard()
            return
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

    def _open_keyboard(self) -> None:
        try:
            if self.input.mode in ("launcher", "cursor") and self.session:
                field = self.steam_keyboard.focused_edit(self.session.recipe)
                if field:
                    self.steam_keyboard.open(field)
                    self.log.info("点击可编辑输入框，已请求 Steam 原生键盘")
        except Exception as error:
            self.log.warning("打开原生键盘失败: %s", error)
            self.ui.set_status("打开 Steam 键盘失败，请按 Steam + X 重试")
        finally:
            self._keyboard_pending = False
            try:
                self.input.keyboard_active = self.steam_keyboard.input_taken()
            except Exception as error:
                self.log.warning("读取 Steam 输入状态失败: %s", error)
                self.input.keyboard_active = False

    def _close_keyboard(self) -> None:
        try:
            self.steam_keyboard.close()
        except Exception as error:
            self.log.warning("关闭 Steam 键盘失败: %s", error)

    def _on_launch(self, idx: int) -> None:
        if not (0 <= idx < len(self.recipes)):
            return
        if self.session and self.session.phase not in (Phase.IDLE, Phase.DONE):
            self.log.info("已有会话在运行，忽略本次启动请求")
            return
        recipe = self.recipes[idx]
        self.log.info("启动：%s (%s)", recipe.name, recipe.id)
        self._apply_bridge_config(recipe)
        self.session = Session(
            recipe, self.ui, self.log, on_input_mode=self._on_input_mode
        )
        self.session.clicker = self.input.cursor  # 供窗口规则里的 click 动作使用
        self._session_thread = threading.Thread(
            target=self.session.run, daemon=True, name=f"session-{recipe.id}"
        )
        self._session_thread.start()

    def _tick(self) -> None:
        if self._quit:
            self._close_keyboard()
            if self.session:
                self.session.request_stop("quit")
            self.ui.destroy()
            return
        if not self._keyboard_pending:
            try:
                self.input.keyboard_active = (self.input.mode in ("launcher", "cursor")
                                               and self.steam_keyboard.input_taken())
            except Exception:
                self.log.exception("检测 Steam 输入状态失败")
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
        self._close_keyboard()
        try:
            self.input.stop()
        except Exception:  # noqa: BLE001
            pass
        if self.session:
            self.session.request_stop("shutdown")
            if self._session_thread is not None:
                self._session_thread.join(timeout=20)
            else:
                self.session.cleanup()
