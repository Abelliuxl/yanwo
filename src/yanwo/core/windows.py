"""窗口规则引擎（每个游戏在配方里声明，不在代码里写死）。

为什么需要它（2026-10-04 实测结论）：
  * **game mode**：窗口的 **层级/位置完全由 gamescope(steamcompmgr) 掌管**，
    外部客户端发 `XRaiseWindow` / `XMoveWindow` / `XSetInputFocus` / `XConfigureWindow`
    **全部无效**（实测堆叠顺序和坐标纹丝不动）；`unmap+map` 也没用。
  * **desktop mode**（KWin）：这些请求都正常生效。
  * 所以规则引擎不假设"一定成功"，而是**执行后回读**，把"没生效"写进日志，
    方便每个游戏各自试探哪种动作管用。

配方里这样写（见 docs/RECIPES.md）：

    [windows]
    enabled = true
    watch_seconds = 120
    [[windows.rules]]
    name = "年龄提示"
    match = "MpayAgeTipsForm"      # 标题正则
    actions = ["close"]            # 见 _ACTIONS
    priority = 20
    stop = false                   # 默认 false：所有匹配的规则都执行
    [[windows.rules]]
    name = "登录"
    match = "^(登录|Login)"
    actions = ["focus"]
    priority = 10
"""
from __future__ import annotations

import ctypes
import logging
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field

from .gamescope import GamescopeFocus

log = logging.getLogger("yanwo.windows")

# 支持的动作（配方里 actions = [...] 写这些名字）
_ACTIONS = {
    "focus": "置前 + 请求输入焦点（desktop 下=KWin 生效；game mode 通常被忽略）",
    "raise": "只置前（XRaiseWindow）",
    "lower": "压到最底（XLowerWindow）",
    "move:x,y": "移动窗口到 x,y",
    "resize:w,h": "改变窗口大小",
    "remap": "unmap 后重新 map（有些 WM 会把它当成新窗口放上层）",
    "hide": "隐藏（unmap）",
    "close": "发送关闭事件（等于点右上角 X，最礼貌的一种）",
    "click": "把光标移到窗口中心并左键点一下（用 XTest，game mode 下也可能无效）",
}


@dataclass
class WindowInfo:
    wid: int
    title: str = ""
    pid: int = 0
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0
    mapped: bool = False
    transient_for: int = 0        # 非 0 = 这是某个窗口的弹窗/对话框

    @property
    def is_dialog(self) -> bool:
        return self.transient_for != 0

    def __str__(self) -> str:
        kind = "弹窗" if self.is_dialog else "窗口"
        return (f"[{self.wid:#x}] {kind} {self.title or '?'} "
                f"{self.w}x{self.h}+{self.x}+{self.y} pid={self.pid}")


class _XErrorEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("resourceid", ctypes.c_ulong),
        ("serial", ctypes.c_ulong),
        ("error_code", ctypes.c_ubyte),
        ("request_code", ctypes.c_ubyte),
        ("minor_code", ctypes.c_ubyte),
    ]


_ERROR_HANDLER = None  # 必须留引用，否则 GC 掉 → 崩


class _X:
    """极简 X11 封装（ctypes，无进程开销）。"""

    def __init__(self, display: str | None = None) -> None:
        self.lib = ctypes.CDLL("libX11.so.6")
        L = self.lib
        L.XOpenDisplay.restype = ctypes.c_void_p
        L.XOpenDisplay.argtypes = [ctypes.c_char_p]
        L.XDefaultRootWindow.restype = ctypes.c_ulong
        L.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        L.XQueryTree.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.POINTER(ctypes.c_ulong)),
            ctypes.POINTER(ctypes.c_uint),
        ]
        L.XFetchName.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_char_p)]
        L.XInternAtom.restype = ctypes.c_ulong
        L.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        L.XGetWindowProperty.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_long, ctypes.c_long,
            ctypes.c_int, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte)),
        ]
        L.XGetGeometry.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint),
        ]
        L.XFlush.argtypes = [ctypes.c_void_p]
        L.XGetWindowAttributes.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p]
        L.XGetImage.restype = ctypes.c_void_p
        L.XGetImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                                ctypes.c_uint, ctypes.c_uint, ctypes.c_ulong, ctypes.c_int]
        L.XGetPixel.restype = ctypes.c_ulong
        L.XGetPixel.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        L.XDestroyImage.argtypes = [ctypes.c_void_p]
        L.XGetInputFocus.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong),
                                     ctypes.POINTER(ctypes.c_int)]
        L.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        L.XSendEvent.restype = ctypes.c_int
        L.XSendEvent.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_long, ctypes.c_void_p
        ]
        for fn, argtypes in (
            ("XRaiseWindow", [ctypes.c_void_p, ctypes.c_ulong]),
            ("XLowerWindow", [ctypes.c_void_p, ctypes.c_ulong]),
            ("XMoveWindow", [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int]),
            ("XResizeWindow", [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_uint, ctypes.c_uint]),
            ("XUnmapWindow", [ctypes.c_void_p, ctypes.c_ulong]),
            ("XMapWindow", [ctypes.c_void_p, ctypes.c_ulong]),
            ("XSetInputFocus", [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]),
        ):
            f = getattr(L, fn)
            f.restype = ctypes.c_int
            f.argtypes = argtypes
        self.dpy = L.XOpenDisplay(display.encode() if display else None)
        if not self.dpy:
            raise RuntimeError("XOpenDisplay 失败")
        self.root = L.XDefaultRootWindow(ctypes.c_void_p(self.dpy))
        L.XGetWindowProperty.restype = ctypes.c_int
        L.XFree.argtypes = [ctypes.c_void_p]
        self._pid_atom = L.XInternAtom(ctypes.c_void_p(self.dpy), b"_NET_WM_PID", 0)
        self._utf8_atom = L.XInternAtom(ctypes.c_void_p(self.dpy), b"UTF8_STRING", 0)
        self._name_atom = L.XInternAtom(ctypes.c_void_p(self.dpy), b"_NET_WM_NAME", 0)
        self._transient_atom = L.XInternAtom(ctypes.c_void_p(self.dpy), b"WM_TRANSIENT_FOR", 0)
        self._active_atom = L.XInternAtom(ctypes.c_void_p(self.dpy), b"_NET_ACTIVE_WINDOW", 0)
        self.last_error = 0
        # libX11 的默认错误处理器会直接 exit(1)：一个 BadMatch 就能把 Hub 干掉。
        # 换成"记下来、不退出"，这样探测类调用（XGetImage）失败也不会连累主程序。
        global _ERROR_HANDLER
        if _ERROR_HANDLER is None:
            L.XSetErrorHandler.restype = ctypes.c_void_p
            L.XSetErrorHandler.argtypes = [ctypes.c_void_p]

            def _handler(_dpy, ev):
                try:
                    self.last_error = ctypes.cast(ev, ctypes.POINTER(_XErrorEvent)).contents.error_code
                except Exception:  # noqa: BLE001
                    pass
                return 0

            _ERROR_HANDLER = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)(_handler)
            L.XSetErrorHandler(_ERROR_HANDLER)

    # ---- 查询 ----
    def _prop(self, wid: int, atom: int) -> tuple[bytes, int]:
        """XGetWindowProperty 的正确参数顺序（少传 actual_format 会整串错位，标题会截断）。"""
        actual = ctypes.c_ulong()
        fmt = ctypes.c_int()
        nitems = ctypes.c_ulong()
        after = ctypes.c_ulong()
        data = ctypes.POINTER(ctypes.c_ubyte)()
        ok = self.lib.XGetWindowProperty(
            ctypes.c_void_p(self.dpy), ctypes.c_ulong(wid), ctypes.c_ulong(atom),
            0, 1024, 0, 0,
            ctypes.byref(actual), ctypes.byref(fmt), ctypes.byref(nitems),
            ctypes.byref(after), ctypes.byref(data),
        )
        if ok != 0 or not data or nitems.value == 0:
            return b"", 0
        nbytes = nitems.value * (fmt.value // 8 or 1)
        return ctypes.string_at(data, nbytes), fmt.value

    def _raw_prop(self, wid: int, atom: int) -> bytes:
        return self._prop(wid, atom)[0]

    def _name(self, wid: int) -> str:
        """优先 _NET_WM_NAME（UTF-8，中文才不会变成 ??），退路 WM_NAME。"""
        raw = self._raw_prop(wid, self._name_atom)
        if raw:
            return raw.decode("utf-8", "replace").strip("\x00").strip()
        nm = ctypes.c_char_p()
        if self.lib.XFetchName(ctypes.c_void_p(self.dpy), ctypes.c_ulong(wid), ctypes.byref(nm)) and nm.value:
            return nm.value.decode("utf-8", "replace").strip()
        return ""

    def _pid(self, wid: int) -> int:
        raw, fmt = self._prop(wid, self._pid_atom)
        if raw and fmt == 32:
            return int.from_bytes(raw[:8], "little")
        return 0

    # XWindowAttributes 里 map_state 在 x86_64 上的偏移。
    # 结构体开头是 x,y,width,height,border_width,depth,Visual*,Window,int,int,... —— 偏移 92 实测正确
    # （0=IsUnmapped 1=IsUnviewable 2=IsViewable）。
    _MAP_STATE_OFFSET = 92

    def _mapped(self, wid: int) -> bool:
        buf = ctypes.create_string_buffer(256)
        if self.lib.XGetWindowAttributes(ctypes.c_void_p(self.dpy), ctypes.c_ulong(wid), buf) == 0:
            return False
        return ctypes.c_int.from_buffer(buf, self._MAP_STATE_OFFSET).value == 2

    def _geom(self, wid: int):
        root = ctypes.c_ulong(); x = ctypes.c_int(); y = ctypes.c_int()
        w = ctypes.c_uint(); h = ctypes.c_uint(); bw = ctypes.c_uint(); depth = ctypes.c_uint()
        if self.lib.XGetGeometry(
            ctypes.c_void_p(self.dpy), ctypes.c_ulong(wid), ctypes.byref(root),
            ctypes.byref(x), ctypes.byref(y), ctypes.byref(w), ctypes.byref(h),
            ctypes.byref(bw), ctypes.byref(depth),
        ):
            return x.value, y.value, w.value, h.value
        return 0, 0, 0, 0

    def list(self) -> list[WindowInfo]:
        r = ctypes.c_ulong(); c_ = ctypes.c_ulong()
        p = ctypes.POINTER(ctypes.c_ulong)(); n = ctypes.c_uint()
        if not self.lib.XQueryTree(
            ctypes.c_void_p(self.dpy), ctypes.c_ulong(self.root),
            ctypes.byref(r), ctypes.byref(c_), ctypes.byref(p), ctypes.byref(n),
        ):
            return []
        out = []
        for i in range(n.value):  # X 返回：底 → 顶
            wid = int(p[i])
            title = self._name(wid)
            if not title:
                continue
            x, y, w, h = self._geom(wid)
            traw, _ = self._prop(wid, self._transient_atom)
            # 32 位属性只有 4 字节，要补齐再解析（别判 len>=8）
            transient = int.from_bytes(traw[:4].ljust(4, b"\0"), "little") if traw else 0
            out.append(WindowInfo(wid, title, self._pid(wid), x, y, w, h,
                                  self._mapped(wid), transient))
        return out

    def index_of(self, wid: int, wins: list[WindowInfo]) -> int:
        for i, w in enumerate(wins):
            if w.wid == wid:
                return i
        return -1

    # ---- 动作 ----
    def raise_(self, wid: int) -> None:
        self.lib.XRaiseWindow(ctypes.c_void_p(self.dpy), ctypes.c_ulong(wid))
        self.lib.XFlush(ctypes.c_void_p(self.dpy))

    def lower(self, wid: int) -> None:
        self.lib.XLowerWindow(ctypes.c_void_p(self.dpy), ctypes.c_ulong(wid))
        self.lib.XFlush(ctypes.c_void_p(self.dpy))

    def move(self, wid: int, x: int, y: int) -> None:
        self.lib.XMoveWindow(ctypes.c_void_p(self.dpy), ctypes.c_ulong(wid), x, y)
        self.lib.XFlush(ctypes.c_void_p(self.dpy))

    def resize(self, wid: int, w: int, h: int) -> None:
        self.lib.XResizeWindow(ctypes.c_void_p(self.dpy), ctypes.c_ulong(wid), w, h)
        self.lib.XFlush(ctypes.c_void_p(self.dpy))

    def unmap(self, wid: int) -> None:
        self.lib.XUnmapWindow(ctypes.c_void_p(self.dpy), ctypes.c_ulong(wid))
        self.lib.XFlush(ctypes.c_void_p(self.dpy))

    def map_(self, wid: int) -> None:
        self.lib.XMapWindow(ctypes.c_void_p(self.dpy), ctypes.c_ulong(wid))
        self.lib.XFlush(ctypes.c_void_p(self.dpy))

    def focus(self, wid: int) -> None:
        self.raise_(wid)
        self.lib.XSetInputFocus(ctypes.c_void_p(self.dpy), ctypes.c_ulong(wid), 2, 0)
        self.lib.XFlush(ctypes.c_void_p(self.dpy))

    def pixel(self, x: int, y: int) -> int:
        """读屏幕上某个点的真实像素（0xRRGGBB）。

        这是**唯一可靠的"视觉验证"** —— 堆叠顺序/_NET_ACTIVE_WINDOW 都可能说谎，
        只有像素不会：某个动作有没有真的把窗口挪到最前，看这个点在动作前后变没变。
        """
        self.last_error = 0
        img = self.lib.XGetImage(ctypes.c_void_p(self.dpy), ctypes.c_ulong(self.root),
                                 int(x), int(y), 1, 1, ~0, 2)  # ZPixmap
        self.lib.XSync(ctypes.c_void_p(self.dpy), 0)
        if not img or self.last_error:
            return -1   # gamescope 下读 root 会 BadMatch（它自己合成画面，X 端没有内容）
        try:
            return int(self.lib.XGetPixel(ctypes.c_void_p(img), 0, 0))
        finally:
            self.lib.XDestroyImage(ctypes.c_void_p(img))

    def input_focus(self) -> int:
        """当前 X 输入焦点（XGetInputFocus）。"""
        w = ctypes.c_ulong(0)
        revert = ctypes.c_int(0)
        self.lib.XGetInputFocus(ctypes.c_void_p(self.dpy), ctypes.byref(w), ctypes.byref(revert))
        return int(w.value)

    def active_window(self) -> int:
        """当前 _NET_ACTIVE_WINDOW（WM 认可的"活动窗口"）。"""
        raw = self._raw_prop(self.root, self._active_atom)
        return int.from_bytes(raw[:4].ljust(4, b"\0"), "little") if raw else 0

    def activate(self, wid: int, timestamp: int = 0) -> None:
        """EWMH `_NET_ACTIVE_WINDOW`：向 WM **请求**"请把某窗口激活/置前"。

        XRaiseWindow / XSetInputFocus 是自己动手改，gamescope(steamcompmgr) 一律忽略；
        而 `_NET_ACTIVE_WINDOW` 是它**自己会处理**的客户端消息 —— game mode 下唯一可能生效的
        "置前"手段。data[0]=2 表示来源是"分页器/外部工具"（WM 通常会照做）。
        """

        class _ClientMessage(ctypes.Structure):
            _fields_ = [
                ("type", ctypes.c_int),
                ("serial", ctypes.c_ulong),
                ("send_event", ctypes.c_int),
                ("display", ctypes.c_void_p),
                ("window", ctypes.c_ulong),
                ("message_type", ctypes.c_ulong),
                ("format", ctypes.c_int),
                ("data", ctypes.c_long * 5),
            ]

        ev = _ClientMessage()
        ev.type = 33            # ClientMessage
        ev.window = wid
        ev.message_type = self._active_atom
        ev.format = 32
        ev.data[0] = 2          # source indication: 2 = pager
        ev.data[1] = timestamp  # 0 = CurrentTime
        ev.data[2] = 0
        mask = (1 << 20) | (1 << 19)   # SubstructureRedirectMask | SubstructureNotifyMask
        self.lib.XSendEvent(ctypes.c_void_p(self.dpy), ctypes.c_ulong(self.root), 0, mask,
                            ctypes.byref(ev))
        self.lib.XFlush(ctypes.c_void_p(self.dpy))


_conn: _X | None = None
_conn_lock = threading.Lock()


def connection(display: str | None = None) -> _X | None:
    global _conn
    with _conn_lock:
        if _conn is None:
            try:
                _conn = _X(display)
            except Exception as e:  # noqa: BLE001
                log.warning("连 X 失败: %s", e)
                return None
    return _conn


def list_windows() -> list[WindowInfo]:
    c = connection()
    return c.list() if c else []


def match_title(pattern: str, wins: list[WindowInfo], only_visible: bool = True) -> list[WindowInfo]:
    try:
        rx = re.compile(pattern)
    except re.error as e:
        log.warning("规则标题正则写错了 %r: %s", pattern, e)
        return []
    out = []
    for w in wins:
        if not rx.search(w.title):
            continue
        if only_visible and (not w.mapped or (w.w <= 1 and w.h <= 1)):
            continue  # IME/托盘等 1x1 辅助窗口别误伤
        out.append(w)
    return out


# 这些窗口永远不参与规则/门控（自家 Hub、WM、IME 辅助窗等）
_IGNORE_TITLE = re.compile(r"^(燕窝|Yanwo|steamcompmgr|Default|Input$|QTrayIconMessageWindow)")


def game_windows(wins: list[WindowInfo] | None = None) -> list[WindowInfo]:
    """可见的、非辅助窗口（按底→顶顺序）。规则和光标门控都只看这个列表。"""
    wins = list_windows() if wins is None else wins
    return [w for w in wins if w.mapped and not (w.w <= 1 and w.h <= 1)
            and not _IGNORE_TITLE.search(w.title)]


@dataclass
class BridgeGate:
    """决定"游戏阶段要不要开光标桥"。

    规则（配方 [bridge] 里声明）：
      * cursor_windows：标题正则列表，命中任意一个就开
      * cursor_on_dialogs：出现任意"弹窗/对话框"（WM_TRANSIENT_FOR 非 0）就开
    默认只看游戏自己的窗口（game_windows()）。
    """

    cursor_windows: list[str] = field(default_factory=list)
    cursor_on_dialogs: bool = True
    pause_windows: list[str] = field(default_factory=list)

    def wants_cursor(self, wins: list[WindowInfo] | None = None) -> tuple[bool, str]:
        ws = game_windows(wins)
        if not ws:
            return False, "没有可见窗口"
        for pat in self.pause_windows:
            hit = match_title(pat, ws, only_visible=False)
            if hit:
                return False, f"命中暂停窗口 {pat!r} → {hit[0].title}"
        for pat in self.cursor_windows:
            hit = match_title(pat, ws, only_visible=False)
            if hit:
                return True, f"命中窗口 {pat!r} → {hit[0].title}"
        if self.cursor_on_dialogs:
            dialogs = [w for w in ws if w.is_dialog]
            if dialogs:
                return True, f"有弹窗 → {dialogs[-1].title}"
        return False, "只剩游戏主窗口"


def describe(wins: list[WindowInfo]) -> str:
    return " | ".join(f"{w.title}({w.w}x{w.h})" for w in wins) or "（无）"


def verdict_activate(idx_before: int, idx_after: int, active: int, wid: int) -> str:
    """activate 的判定。

    gamescope **处理** _NET_ACTIVE_WINDOW（内部 XRaiseWindow → restack_win 改它自己的绘制列表），
    但它**从不把 _NET_ACTIVE_WINDOW 写到 root 上**（源码里那个 atom 只用来比对消息类型）。
    所以判据是"堆叠索引有没有上去"，只有真正的 EWMH WM(KWin) 才用得上 active 属性。
    """
    if idx_after > idx_before:
        return f"activate：OK（层级 {idx_before}→{idx_after}，已置前）"
    if active == wid:
        return f"activate：OK（WM 已记为活动窗口，层级 {idx_before}→{idx_after}）"
    return (f"activate：**没生效**（层级 {idx_before}→{idx_after}，"
            f"_NET_ACTIVE_WINDOW={active:#x}）")


def apply_actions(win: WindowInfo, actions: list[str], clicker=None) -> list[str]:
    """执行动作并**回读验证**，返回每条的结果说明（含"没生效"）。"""
    c = connection()
    if c is None:
        return ["连不上 X"]
    results: list[str] = []
    for act in actions:
        before = [w for w in c.list() if w.wid == win.wid]
        idx_before = c.index_of(win.wid, c.list())
        try:
            if act == "activate":
                c.activate(win.wid)
                c.raise_(win.wid)
                c.focus(win.wid)
            elif act == "focus":
                c.focus(win.wid)
            elif act == "raise":
                c.raise_(win.wid)
            elif act == "lower":
                c.lower(win.wid)
            elif act.startswith("move:"):
                x, y = (int(v) for v in act.split(":", 1)[1].split(","))
                c.move(win.wid, x, y)
            elif act.startswith("resize:"):
                w, h = (int(v) for v in act.split(":", 1)[1].split(","))
                c.resize(win.wid, w, h)
            elif act == "remap":
                c.unmap(win.wid)
                time.sleep(0.2)
                c.map_(win.wid)
            elif act == "hide":
                c.unmap(win.wid)
            elif act == "close":
                subprocess.run(["xdotool", "windowclose", hex(win.wid)],
                               capture_output=True, timeout=5)
            elif act == "click":
                if clicker is not None:
                    clicker.move(win.w.w / 2 - win.x, win.h / 2 - win.y)
                    time.sleep(0.2)
                    clicker.click(1)
                else:
                    results.append("click：(没有光标后端)")
                    continue
            else:
                results.append(f"{act}：未知动作")
                continue
        except Exception as e:  # noqa: BLE001
            results.append(f"{act}：异常 {e}")
            continue
        time.sleep(0.25)
        after = [w for w in c.list() if w.wid == win.wid]
        idx_after = c.index_of(win.wid, c.list())
        if act == "click":
            results.append("click：已点（效果无法回读）")
        elif act == "activate":
            results.append(verdict_activate(idx_before, idx_after, c.active_window(), win.wid))
        elif act == "close":
            results.append("close：已发送关闭事件" + ("" if after else "（窗口已消失）"))
        elif not after:
            results.append(f"{act}：窗口已消失")
        elif act in ("focus", "raise") and idx_after <= idx_before:
            results.append(f"{act}：**没生效**（层级 {idx_before}→{idx_after}；"
                           "外部直接改层级会被 WM 吞掉，game mode 请用 activate）")
        elif act.startswith("move:") and before and after and (after[0].x, after[0].y) == (before[0].x, before[0].y):
            results.append(f"{act}：**没生效**（坐标没变，被 WM 忽略）")
        else:
            results.append(f"{act}：OK")
    return results


class WindowRules:
    """按优先级把一个"规则表"作用到游戏窗口上。"""

    def __init__(self, rules: list[dict], logger: logging.Logger | None = None,
                 clicker=None, watch_seconds: float = 120.0,
                 gate: "BridgeGate | None" = None, on_gate=None) -> None:
        self.rules = sorted(rules or [], key=lambda r: -int(r.get("priority", 0)))
        self.log = logger or log
        self.clicker = clicker
        self.watch_seconds = watch_seconds
        self.gate = gate
        self.on_gate = on_gate          # callable(bool needs_cursor, str why)
        self._gate_state: bool | None = None
        self._seen: set[str] = set()
        self._last_apply: dict[str, float] = {}
        self._stop = threading.Event()
        self._gamescope = GamescopeFocus()

    def sync_gamescope(self) -> None:
        focus_rules = [r for r in self.rules if r.get("enabled", True)
                       and "gamescope_focus" in r.get("actions", [])]
        if not focus_rules:
            return
        wins = list_windows()
        target = next((w for r in focus_rules for w in match_title(r.get("match", ""), wins)), None)
        dialogs = [w.wid for r in self.rules if r.get("enabled", True)
                   and "gamescope_dialog" in r.get("actions", [])
                   for w in match_title(r.get("match", ""), wins)
                   if target and w.pid == target.pid]
        previous = self._gamescope.target
        self._gamescope.update(target.wid if target else 0, dialogs)
        if previous != self._gamescope.target:
            self.log.info("gamescope 显示窗口 -> %#x", self._gamescope.target)

    def stop(self) -> None:
        self._stop.set()

    def _titles(self, wins: list[WindowInfo]) -> set[str]:
        return {w.title for w in wins}

    def tick(self) -> None:
        wins = list_windows()
        titles = self._titles(wins)
        changed = titles != self._seen
        if changed:
            new = titles - self._seen
            self._seen = titles
            if new:
                self.log.info("窗口变化: %s", describe(wins))
        now = time.time()
        for rule in self.rules:
            if not rule.get("enabled", True):
                continue
            key = str(rule.get("name") or rule.get("match"))
            repeat = float(rule.get("repeat_seconds", 0) or 0)
            due = changed or (repeat > 0 and now - self._last_apply.get(key, 0) >= repeat)
            if not due:
                continue
            hits = match_title(rule.get("match", ""), wins)
            if not hits:
                continue
            self._last_apply[key] = now
            acts = [a for a in rule.get("actions", [])
                    if a not in ("gamescope_focus", "gamescope_dialog")]
            if not acts:
                continue
            for win in hits:
                res = apply_actions(win, acts, self.clicker)
                self.log.info("窗口规则「%s」→ %s : %s", key, win, "; ".join(res))
            if rule.get("stop", False):
                break  # 默认所有匹配规则都执行；写 stop = true 表示"这条生效后不再往下看"

    def _eval_gate(self) -> None:
        if not self.gate or not self.on_gate:
            return
        want, why = self.gate.wants_cursor()
        if want != self._gate_state:
            self._gate_state = want
            self.log.info("光标桥门控 -> %s（%s）", "开" if want else "关", why)
            try:
                self.on_gate(want, why)
            except Exception:  # noqa: BLE001
                self.log.exception("切换光标桥失败")

    def run(self) -> None:
        """规则只在前 watch_seconds 秒生效；桥门控全程评估（直到会话结束）。"""
        deadline = time.time() + self.watch_seconds
        try:
            while not self._stop.is_set():
                try:
                    self.sync_gamescope()  # 登录可晚于 watch_seconds；全程维护并自动释放。
                    if time.time() < deadline:
                        self.tick()
                    self._eval_gate()
                except Exception:  # noqa: BLE001
                    self.log.exception("窗口规则执行出错")
                self._stop.wait(2.0)
        finally:
            try:
                self._gamescope.release()
            except Exception:  # noqa: BLE001
                self.log.exception("归还 gamescope 显示焦点失败")
