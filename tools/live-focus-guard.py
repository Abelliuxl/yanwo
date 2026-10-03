#!/usr/bin/env python3
"""给正在运行的燕云会话热打"年龄窗抢焦点"补丁（不重启燕窝）。

根因（2026-10-04 实机确认）：点出 Steam 原生键盘时，年龄提示卡 MpayAgeTipsForm
会抢走游戏 X 显示(:1)的输入焦点（`xdotool getwindowfocus` = MpayAgeTipsForm），
于是键盘按键全进到那个空窗口、登录框什么都收不到。
实测：把它 unmap 掉，焦点立刻回到"登录"窗，且画面完整不黑屏
（baselayer 已被 gamescope_focus 钉在登录窗）。

本脚本常驻：只要登录窗在，就把年龄卡 unmap 掉（游戏再 map 出来就再 unmap），
从根上让它没法抢焦点。会话结束后退出。务必用 systemd-run 起，防被 logind 杀。
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import yanwo.core.windows as w  # noqa: E402

LOGIN_RE = r"^(登录|Login|登入)"
AGE_RE = r"^MpayAgeTipsForm$"   # 配方里 gamescope_dialog 标记的年龄卡


def main() -> int:
    os.environ.setdefault("DISPLAY", ":1")
    deadline = time.time() + 6 * 3600
    while time.time() < deadline:
        try:
            wins = w.list_windows()
            logins = w.match_title(LOGIN_RE, wins)
            if logins:
                target = logins[0].wid
                c = w.connection()
                if c is None:
                    time.sleep(0.5)
                    continue
                for age in w.match_title(AGE_RE, wins, only_visible=False):
                    if age.mapped:
                        c.unmap(age.wid)
                        print(f"unmap 年龄卡 {age.wid:#x}（防抢焦点）", flush=True)
                if c.input_focus() != target:
                    c.focus(target)
                    print(f"焦点交还登录窗 {target:#x}", flush=True)
        except Exception as error:  # noqa: BLE001
            print(f"guard error: {error}", flush=True)
        time.sleep(0.3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
