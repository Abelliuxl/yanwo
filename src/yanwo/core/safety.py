"""显存安全阀（从 ~/Games/yysls/vram-guard.py 提炼）。

设计：
- 默认**不**自己开监控，如果系统里已经有独立的 vram-guard.service 在跑，就交给它，
  避免两边同时动手（双杀）。
- 以后（P3）会把独立服务去掉，统一由 Hub 按配方 [safety] 掌管。
- 触发时只回调 on_trip(reason)，**不直接杀**：由 session 走"先优雅关窗、再杀"的流程。
"""
from __future__ import annotations

import glob
import subprocess
import threading
import time

GB = 1024**3
CARD = "/sys/class/drm/card0/device"


def _read_int(path: str, default: int = 0) -> int:
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return default


def _pid_vram(pid: int) -> int:
    total = 0
    for fd in glob.glob(f"/proc/{pid}/fdinfo/*"):
        try:
            with open(fd) as f:
                for line in f:
                    if line.startswith("drm-total-vram:"):
                        total += int(line.split()[1]) * 1024
        except (OSError, ValueError):
            continue
    return total


def _group_vram(pids: list[int]) -> int:
    return sum(_pid_vram(p) for p in pids)


def external_guard_active() -> bool:
    try:
        r = subprocess.run(
            ["systemctl", "--user", "is-active", "vram-guard.service"],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip() == "active"
    except Exception:  # noqa: BLE001
        return False


class VramMonitor(threading.Thread):
    """按配方 [safety] 监控这个 prefix 的显存增长/上限。"""

    def __init__(self, prefix_hint: str, policy: dict, on_trip, procs_fn, interval: float = 2.0):
        super().__init__(daemon=True, name="vram-monitor")
        self.prefix_hint = prefix_hint
        self.policy = policy or {}
        self.on_trip = on_trip
        self.procs_fn = procs_fn  # callable() -> dict[pid, comm]
        self.interval = interval
        self._stop = threading.Event()
        self.tripped = False

    def stop(self) -> None:
        self._stop.set()

    def _limit_bytes(self, key: str, default_gb: float) -> int:
        gb = float(self.policy.get(key, default_gb))
        return int(gb * GB)

    def run(self) -> None:
        window = float(self.policy.get("window_seconds", 60))
        hard = self._limit_bytes("max_group_vram_gb", 8)
        growth = self._limit_bytes("max_growth_gb", 4)
        vram_pct = float(self.policy.get("max_global_vram_pct", 92))
        tot = _read_int(f"{CARD}/mem_info_vram_total")
        hist: list[tuple[float, int]] = []
        while not self._stop.wait(self.interval):
            procs = self.procs_fn()
            if not procs:
                continue
            g = _group_vram(list(procs))
            now = time.time()
            hist.append((now, g))
            hist = [(t, v) for t, v in hist if now - t <= window]
            delta = g - min(v for _, v in hist)
            uvram = _read_int(f"{CARD}/mem_info_vram_used")
            reason = None
            if uvram > tot * vram_pct / 100:
                reason = f"全局显存 {uvram/GB:.1f}G > {vram_pct:.0f}%"
            elif g > hard:
                reason = f"进程组显存 {g/GB:.1f}G > {hard/GB:.1f}G"
            elif delta > growth:
                reason = f"显存 {window:.0f}s 内增长 {delta/GB:.1f}G"
            if reason and not self.tripped:
                self.tripped = True
                self.on_trip(reason)
                return
