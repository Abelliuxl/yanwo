#!/usr/bin/env python3
"""gamescope 截图 + 画面分析（看 game mode 里**真实**画出来的是什么）。

为什么需要它：game mode 下想判断"某个窗口到底有没有被显示"，X 的堆叠顺序、
`_NET_ACTIVE_WINDOW` 属性、`XGetImage(root)` 全都不可靠（前者会骗人，
后者在 gamescope 上直接 BadMatch）。而 `gamescopectl screenshot`
能拿到 gamescope 真正合成的画面 —— 这是唯一的真相来源。

用法：
    tools/gs-shot.py shot.png                  # 截一张（默认 type 4 = 屏幕缓冲）
    tools/gs-shot.py --find shot.png           # 截图并列出"画了东西的矩形"
    tools/gs-shot.py --crop shot.png 1560 600 720 960 view.png   # 裁剪出可看的小图
    tools/gs-shot.py --scale shot.png 700 394 view.png           # 缩放成可看的小图

type: 1=base_plane_only 2=all_real_layers 3=full_composition 4=screen_buffer
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from png import crop, px, read_png, scale, write_png  # noqa: E402


def shot(path: str, kind: int = 4, wait: float = 8.0) -> bool:
    """截图。gamescope 是异步写文件的（命令立刻返回，文件稍后才出现），所以要等。"""
    env = dict(os.environ)
    env.setdefault("GAMESCOPE_WAYLAND_DISPLAY", "gamescope-0")
    p = Path(path)
    if p.exists():
        p.unlink()
    r = subprocess.run(["gamescopectl", "screenshot", path, str(kind)],
                       env=env, capture_output=True, timeout=30)
    if r.returncode != 0:
        return False
    deadline = time.time() + wait
    while time.time() < deadline:
        if p.is_file() and p.stat().st_size > 1000:
            time.sleep(0.2)      # 等写完
            return True
        time.sleep(0.1)
    return False


def find_rects(path: str, cell: int = 40, thresh: int = 10) -> list[tuple[int, int, int, int]]:
    """按 cell×cell 网格找"非黑"连通块，用来快速看出画面里有哪几块东西。"""
    w, h, d, _ = read_png(path)
    cw, ch = w // cell, h // cell
    grid = [[0] * cw for _ in range(ch)]
    for gy in range(ch):
        for gx in range(cw):
            s = 0
            n = 0
            for dy in range(0, cell, 8):
                for dx in range(0, cell, 8):
                    r, g, b = px(d, w, gx * cell + dx, gy * cell + dy)
                    s += (r + g + b) / 3
                    n += 1
            grid[gy][gx] = 1 if s / n > thresh else 0
    seen = [[0] * cw for _ in range(ch)]
    out: list[tuple[int, int, int, int]] = []
    for gy in range(ch):
        for gx in range(cw):
            if grid[gy][gx] and not seen[gy][gx]:
                st = [(gx, gy)]
                seen[gy][gx] = 1
                xs, ys = [], []
                while st:
                    x, y = st.pop()
                    xs.append(x)
                    ys.append(y)
                    for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                        if 0 <= nx < cw and 0 <= ny < ch and grid[ny][nx] and not seen[ny][nx]:
                            seen[ny][nx] = 1
                            st.append((nx, ny))
                if len(xs) >= 3:
                    out.append((min(xs) * cell, min(ys) * cell,
                                (max(xs) - min(xs) + 1) * cell, (max(ys) - min(ys) + 1) * cell))
    return sorted(out, key=lambda r: -r[2] * r[3])


def main() -> int:
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    if a[0] == "--find":
        p = a[1]
        if not shot(p):
            print("截图失败（gamescope 在跑吗？）")
            return 1
        w, h, _, _ = read_png(p)
        print(f"{p}: {w}x{h}")
        for x, y, rw, rh in find_rects(p):
            print(f"  画面块 {rw}x{rh}+{x}+{y}")
        return 0
    if a[0] in ("--crop", "--scale"):
        p, dst = a[1], a[-1]
        w, h, d, _ = read_png(p)
        if a[0] == "--crop":
            x, y, cw, ch = (int(v) for v in a[2:6])
            write_png(dst, cw, ch, crop(d, w, h, x, y, cw, ch))
        else:
            nw, nh = int(a[2]), int(a[3])
            write_png(dst, nw, nh, scale(d, w, h, nw, nh))
        print(f"-> {dst}")
        return 0
    kind = int(a[1]) if len(a) > 1 else 4
    if shot(a[0], kind):
        w, h, _, _ = read_png(a[0])
        print(f"{a[0]}: {w}x{h} (type {kind})")
        return 0
    print("截图失败")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
