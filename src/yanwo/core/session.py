"""一次"进入游戏"的编排：状态机 + 收尾规则。

状态流转（见 docs/DESIGN.md 第四节）：

    HUB → PREPARE → LAUNCHING → LAUNCHER ──发现游戏进程──▶ GAME
                                  │                        │
                                  │◀──── 游戏退出（按 policy）
                                  ▼
                                 回到 HUB（或按 policy 关掉官方启动器）
"""
from __future__ import annotations

import logging
import os
import signal
import time
from enum import Enum

from ..recipe import Recipe
from . import detect, runner, x11
from .safety import VramMonitor, external_guard_active


class Phase(str, Enum):
    IDLE = "idle"
    PREPARE = "prepare"
    LAUNCHING = "launching"
    LAUNCHER = "launcher"
    GAME = "game"
    DONE = "done"


class Session:
    def __init__(self, recipe: Recipe, ui, logger: logging.Logger | None = None):
        self.recipe = recipe
        self.ui = ui
        self.log = logger or logging.getLogger("yanwo.session")
        self.phase = Phase.IDLE
        self._stop = False
        self._reason = ""
        self._monitor: VramMonitor | None = None

    # ---------- 对外 ----------
    def request_stop(self, reason: str = "user") -> None:
        self.log.info("请求停止: %s", reason)
        self._stop = True
        self._reason = reason

    # ---------- 内部工具 ----------
    def _status(self, text: str) -> None:
        self.log.info("状态: %s", text)
        self.ui.set_status(text)

    def _set_phase(self, p: Phase) -> None:
        self.phase = p
        self.log.info("阶段 -> %s", p.value)

    def _prefix_pids(self) -> dict[int, str]:
        return detect.procs_of_prefix(self.recipe.prefix_hint)

    def _graceful_close(self, pids: list[int]) -> None:
        n = x11.close_windows(pids)
        self.log.info("已向 %d 个窗口发关闭事件，等 6 秒", n)
        time.sleep(6)

    def _force_kill_prefix(self) -> None:
        pids = list(self._prefix_pids())
        if not pids:
            return
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        time.sleep(3)
        for pid in list(self._prefix_pids()):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass

    def cleanup(self) -> None:
        """收尾：先优雅关窗，再（必要时）整组清掉。"""
        self._set_phase(Phase.DONE)
        if self._monitor:
            self._monitor.stop()
        pids = list(self._prefix_pids())
        if not pids:
            return
        self._graceful_close(pids)
        if self.recipe.policy_get("kill_orphan_wine", True):
            left = list(self._prefix_pids())
            if left:
                self.log.info("仍有 %d 个进程，收尾清理", len(left))
                self._force_kill_prefix()

    # ---------- 主流程 ----------
    def run(self) -> None:
        r = self.recipe
        try:
            self._set_phase(Phase.PREPARE)
            self._status(f"准备：{r.name}")
            if r.install:
                self.log.info("该配方带 [install]，P1 暂不自动安装（见 docs/ROADMAP.md）")

            self._set_phase(Phase.LAUNCHING)
            self._status("正在启动官方启动器…")
            runner.launch_chain(r)

            # 显存安全阀：系统已有独立守卫时让位给它
            if not external_guard_active() and r.safety:
                self._monitor = VramMonitor(
                    r.prefix_hint, r.safety, self._on_vram_trip, self._prefix_pids
                )
                self._monitor.start()
                self.log.info("已启用配方自带显存监控 %s", r.safety)
            elif external_guard_active():
                self.log.info("检测到 vram-guard.service，交由它看护显存")

            self._set_phase(Phase.LAUNCHER)
            self._status("等待官方启动器…")
            if r.detect_launcher:
                detect.wait_for(r.detect_launcher, r.prefix_hint, timeout=120)

            self.ui.hide()  # 让位给官方启动器窗口
            self._wait_loop()
        except Exception as e:  # noqa: BLE001
            self.log.exception("启动失败: %s", e)
            self._status(f"启动失败：{e}")
            time.sleep(3)
        finally:
            self.cleanup()
            self.ui.show()
            self._status("")
            self.ui.refresh()

    def _wait_loop(self) -> None:
        r = self.recipe
        seen_game = False
        while not self._stop:
            launcher_alive = (
                detect.any_running(r.detect_launcher, r.prefix_hint)
                if r.detect_launcher
                else bool(self._prefix_pids())
            )
            game_alive = (
                detect.any_running(r.detect_game, r.prefix_hint) if r.detect_game else False
            )

            if game_alive and not seen_game:
                seen_game = True
                self._set_phase(Phase.GAME)
                self._status("游戏运行中…")
            elif not game_alive and seen_game:
                self.log.info("游戏已退出")
                seen_game = False
                on_exit = r.policy_get("on_game_exit", "wait_launcher")
                if on_exit == "close_launcher":
                    self.log.info("policy: 关闭官方启动器")
                    return
                self._set_phase(Phase.LAUNCHER)
                self._status("官方启动器仍在运行…")

            if not launcher_alive and not game_alive:
                self.log.info("启动器与游戏都已退出")
                return
            time.sleep(2)

    def _on_vram_trip(self, reason: str) -> None:
        self.log.warning("显存安全阀触发: %s", reason)
        self._status(f"显存异常，正在安全退出（{reason}）")
        self.request_stop("vram")
