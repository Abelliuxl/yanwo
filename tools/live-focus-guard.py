#!/usr/bin/env python3
"""仅收起当前会话的年龄辅助窗，不反复重置登录顶层焦点。

真正的编辑控件恢复由 focused-edit.exe 负责。不要在键盘期间调用
XSetInputFocus 把焦点强制交给顶层窗，否则可能销毁 MPAY 临时编辑框。
优先使用主程序的窗口规则；此脚本仅保留为已有会话的诊断工具。
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
                c = w.connection()
                if c is None:
                    time.sleep(0.5)
                    continue
                for age in w.match_title(AGE_RE, wins, only_visible=False):
                    if age.mapped:
                        c.unmap(age.wid)
                        print(f"unmap 年龄卡 {age.wid:#x}（防抢焦点）", flush=True)
        except Exception as error:  # noqa: BLE001
            print(f"guard error: {error}", flush=True)
        time.sleep(0.3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
