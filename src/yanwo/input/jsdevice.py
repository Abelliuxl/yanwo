"""手柄设备（joystick API）的发现与读取。

要点（踩过的坑）：
  * js 设备**不能**靠 O_NONBLOCK 读，必须用 select() 等（否则 read 永久阻塞）。
  * 事件是固定 8 字节：`<IhBB`（time, value, type, number）；type 的高位 0x80
    表示"初始化事件"（打开设备时会把当前状态全推一遍），要跳过。
  * 同一台机器可能有好几个 js 设备（物理接收器 + Steam Input 造的虚拟手柄），
    所以提供"谁先出事件就用谁"的自动选择。
"""
from __future__ import annotations

import glob
import os
import select
import struct
import time
from dataclasses import dataclass

EVENT_FMT = "<IhBB"
EVENT_SIZE = struct.calcsize(EVENT_FMT)
TYPE_BUTTON = 0x01
TYPE_AXIS = 0x02
INIT_BIT = 0x80


@dataclass
class RawEvent:
    time_ms: int
    value: int
    type: int
    number: int
    is_init: bool = False


def parse_events(buf: bytes) -> tuple[list[RawEvent], bytes]:
    """把原始字节流切成事件；返回 (事件列表, 剩余半包)。"""
    evs: list[RawEvent] = []
    while len(buf) >= EVENT_SIZE:
        t, v, typ, num = struct.unpack(EVENT_FMT, buf[:EVENT_SIZE])
        buf = buf[EVENT_SIZE:]
        evs.append(RawEvent(t, v, typ & 0x7F, num, bool(typ & INIT_BIT)))
    return evs, buf


def device_name(path: str) -> str:
    base = os.path.basename(path)
    for p in (f"/sys/class/input/{base}/device/name", f"/sys/class/input/{base}/name"):
        try:
            with open(p) as f:
                return f.read().strip()
        except OSError:
            continue
    return "?"


def list_devices() -> list[tuple[str, str]]:
    out = []
    for path in sorted(glob.glob("/dev/input/js*")):
        out.append((path, device_name(path)))
    return out


class JsDevice:
    def __init__(self, path: str) -> None:
        self.path = path
        self.name = device_name(path)
        self.fd = -1
        self._buf = b""

    def open(self) -> bool:
        try:
            self.fd = os.open(self.path, os.O_RDONLY)
            return True
        except OSError:
            self.fd = -1
            return False

    def close(self) -> None:
        if self.fd >= 0:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = -1

    def fileno(self) -> int:
        return self.fd

    def read(self, timeout: float = 0.0) -> list[RawEvent]:
        """等 timeout 秒（0 = 不等，只取已就绪的）；有事件就全部读出来返回。"""
        if self.fd < 0:
            return []
        if timeout > 0:
            try:
                ready, _, _ = select.select([self.fd], [], [], timeout)
            except (OSError, ValueError):
                return []
            if not ready:
                return []
        evs: list[RawEvent] = []
        while True:
            try:
                chunk = os.read(self.fd, EVENT_SIZE * 32)
            except BlockingIOError:
                break
            except OSError:
                break
            if not chunk:
                break
            self._buf += chunk
            new, self._buf = parse_events(self._buf)
            evs.extend(new)
            if len(chunk) < EVENT_SIZE * 32:
                break
        return evs


def read_many(devs: list["JsDevice"], timeout: float = 0.005) -> list[tuple["JsDevice", RawEvent]]:
    """一次 select 覆盖所有设备，返回 (设备, 事件) 列表。

    关键：不要对每个设备各 select 一次（4 个设备 × 20ms = 80ms 一轮，
    光标就会一顿一顿的）。
    """
    fds = [d.fileno() for d in devs if d.fd >= 0]
    if not fds:
        return []
    try:
        ready, _, _ = select.select(fds, [], [], timeout)
    except (OSError, ValueError):
        return []
    out: list[tuple[JsDevice, RawEvent]] = []
    for d in devs:
        if d.fd < 0 or d.fileno() not in ready:
            continue
        for ev in d.read(0):
            out.append((d, ev))
    return out


def open_all() -> list[JsDevice]:
    """把所有 js 设备都打开（Steam Input 可能抓着物理设备，得能自动换到虚拟的）。"""
    out: list[JsDevice] = []
    for path, _ in list_devices():
        d = JsDevice(path)
        if d.open():
            out.append(d)
    return out


def pick_device(probe_timeout: float = 6.0, prefer: list[str] | None = None) -> JsDevice | None:
    """打开所有 js 设备，谁先产生真实事件就选谁。

    这样物理接收器和 Steam Input 虚拟手柄都能自适应；用户随便动一下摇杆即可。
    """
    prefer = prefer or []
    cands = list_devices()
    if not cands:
        return None
    devs = []
    for path, _ in cands:
        d = JsDevice(path)
        if d.open():
            devs.append(d)
    if not devs:
        return None
    # 先看偏好名单（配方/env 指定）
    for pat in prefer:
        for d in devs:
            if pat.lower() in d.name.lower():
                return d
    deadline = time.time() + probe_timeout
    while time.time() < deadline:
        for d in devs:
            for ev in d.read(0.05):
                if not ev.is_init:
                    return d
        time.sleep(0.02)
    return devs[0]  # 谁都不动，就先用第一个
