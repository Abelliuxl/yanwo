"""进程探测：靠"进程名 + 同一个 WINEPREFIX"识别，而不是靠父子关系。

原因：Wine/Proton 会重新挂父进程，父子的 ppid 链不可靠；用
/proc/<pid>/environ 里的 WINEPREFIX 判断同一个游戏环境最稳。
"""
from __future__ import annotations

import glob
import os
import time


def _read(path: str) -> bytes:
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return b""


def procs_of_prefix(prefix_hint: str) -> dict[int, str]:
    """返回 {pid: 进程名}，只含 WINEPREFIX 里带 prefix_hint 的进程。"""
    hint = prefix_hint.encode()
    out: dict[int, str] = {}
    for p in glob.glob("/proc/[0-9]*"):
        pid = int(p.rsplit("/", 1)[1])
        if pid == os.getpid():
            continue
        env = _read(p + "/environ")
        if not env:
            continue
        if not any(
            kv.startswith(b"WINEPREFIX=") and hint in kv for kv in env.split(b"\0")
        ):
            continue
        comm = _read(p + "/comm").decode("utf-8", "replace").strip()
        out[pid] = comm
    return out


def find(names: list[str], prefix_hint: str = "") -> dict[int, str]:
    """在（可选的）同一前缀里找名字命中的进程。名字忽略大小写。"""
    if not names:
        return {}
    wanted = {n.lower() for n in names}
    pool = procs_of_prefix(prefix_hint) if prefix_hint else _all_procs()
    return {pid: c for pid, c in pool.items() if c.lower() in wanted}


def _all_procs() -> dict[int, str]:
    out: dict[int, str] = {}
    for p in glob.glob("/proc/[0-9]*"):
        pid = int(p.rsplit("/", 1)[1])
        c = _read(p + "/comm").decode("utf-8", "replace").strip()
        if c:
            out[pid] = c
    return out


def any_running(names: list[str], prefix_hint: str = "") -> bool:
    return bool(find(names, prefix_hint))


def wait_for(
    names: list[str],
    prefix_hint: str = "",
    timeout: float = 60.0,
    interval: float = 1.0,
    should_run: bool = True,
) -> bool:
    """等 names 出现(should_run=True)或全部消失(False)。超时返回 False。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if any_running(names, prefix_hint) == should_run:
            return True
        time.sleep(interval)
    return False


def wait_any_gone(prefix_hint: str, timeout: float = 20.0, interval: float = 1.0) -> bool:
    """等整个 prefix 的 Wine 进程组清空。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not procs_of_prefix(prefix_hint):
            return True
        time.sleep(interval)
    return False
