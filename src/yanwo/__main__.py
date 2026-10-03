"""燕窝 Yanwo 的 CLI 入口，同时也是 `python3 -m yanwo` 的实现。"""
from __future__ import annotations

import argparse
import logging
import os
import sys

from .app import HubApp
from .core.session import Session
from .log import get_logger
from .paths import LOG_DIR
from .recipe import find_recipe, load_recipes
from .ui.console import ConsoleUI
from .ui.text_menu import TextMenuUI


def _cmd_list(_args) -> int:
    recipes = load_recipes()
    if not recipes:
        print("（recipes/ 里还没有配方）")
        return 0
    print(f"共 {len(recipes)} 个配方：")
    for r in recipes:
        print(f"  {r.id:<20} {r.name}  {('· ' + r.subtitle) if r.subtitle else ''}")
    return 0


def _cmd_run(args) -> int:
    r = find_recipe(args.id)
    if not r:
        print(f"没找到配方：{args.id}", file=sys.stderr)
        return 2
    ui = ConsoleUI()
    ui.set_games([(r.name, r.subtitle)])
    print(f"[yanwo] 直接运行 {r.name}（无界面）")
    Session(r, ui, get_logger("yanwo.cli")).run()
    return 0


def _cmd_selftest(_args) -> int:
    """不进入事件循环的自检：配方能读、UI 能建、步骤字段齐全。"""
    ok = True
    recipes = load_recipes()
    print(f"[selftest] 配方 {len(recipes)} 个")
    for r in recipes:
        print(f"[selftest]   - {r.id}: {r.name}")
        for i, s in enumerate(r.steps):
            if s.kind == "wine" and not s.get("exe"):
                print(f"[selftest]     !! step[{i}] wine 缺 exe")
                ok = False
            if s.kind == "wine" and not s.get("prefix"):
                print(f"[selftest]     !! step[{i}] wine 缺 prefix")
                ok = False
        if not r.detect_launcher:
            print("[selftest]     (提示) 没有 detect.launcher_procs，退出判断只能靠进程组")
    ui = TextMenuUI([(r.name, r.subtitle) for r in recipes], lambda i: None)
    ui.root.update_idletasks()
    ui.root.update()
    ui.destroy()
    print("[selftest] UI 构建/销毁 OK")
    print("[selftest] 结果:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="yanwo", description="燕窝 Yanwo —— 第三方游戏启动器")
    p.add_argument("--fullscreen", action="store_true", help="全屏（游戏模式/客厅用）")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("list", help="列出配方")
    pr = sub.add_parser("run", help="直接运行某个配方（无界面）")
    pr.add_argument("id")
    sub.add_parser("selftest", help="自检（不进入事件循环）")

    args = p.parse_args(argv)
    if args.cmd == "list":
        return _cmd_list(args)
    if args.cmd == "run":
        return _cmd_run(args)
    if args.cmd == "selftest":
        return _cmd_selftest(args)

    recipes = load_recipes()
    if not recipes:
        print("recipes/ 里没有配方，先加一个 recipes/<id>/game.toml", file=sys.stderr)
        return 1
    # 从 Steam（或桌面入口加 --fullscreen）启动时，自动全屏——比依赖 LaunchOptions 稳
    fullscreen = args.fullscreen or bool(os.environ.get("SteamGameId") or os.environ.get("SteamAppId"))
    try:
        HubApp(recipes, fullscreen=fullscreen).run()
    except Exception as e:  # noqa: BLE001
        # 图形环境起不来时至少留下清楚的日志（方便在游戏模式里排查）
        logging.getLogger("yanwo").exception("Hub 启动失败: %s", e)
        print(f"燕窝 Yanwo 启动失败: {e}\n详见 {LOG_DIR}/yanwo.log", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
