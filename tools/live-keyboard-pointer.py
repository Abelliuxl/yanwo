#!/usr/bin/env python3
"""Enable keyboard-time pointer input in an existing session until Yanwo exits."""
from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from yanwo.input.daemon import InputDaemon
from yanwo.input.steam_keyboard import SteamKeyboard
from yanwo.recipe import find_recipe


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent", type=int, required=True)
    parser.add_argument("--recipe", default="yysls-guofu")
    args = parser.parse_args()
    parent = Path(f"/proc/{args.parent}/stat")
    token = parent.read_text().rsplit(")", 1)[1].split()[19]
    keyboard = SteamKeyboard()
    recipe = find_recipe(args.recipe)
    def select_field(kind, point):
        if kind == "keyboard_pointer_click" and recipe:
            keyboard.click_field(recipe, point)
    bridge = InputDaemon(on_intent=select_field)  # No reopen callback.
    bridge.set_mode("off")
    bridge.keyboard_active = True
    bridge.start()
    active_since = None
    try:
        while parent.exists() and parent.read_text().rsplit(")", 1)[1].split()[19] == token:
            active = keyboard.input_taken() and keyboard.focus_mode == 2
            now = time.monotonic()
            if active_since is None and active:
                active_since = now
            elif not active:
                active_since = None
            # Let the old app's 300ms poll pause its bridge first, so this hotfix
            # never intentionally duplicates its click injection during takeover.
            ready = active_since is not None and now - active_since >= 0.4
            if not ready:
                bridge._keyboard_pointer_moved = False
                if bridge._keyboard_pointer:
                    bridge._keyboard_pointer.transform = None
            bridge.keyboard_display = keyboard.control_display
            bridge.keyboard_cursor_active = ready
            bridge.set_mode("cursor" if ready else "off")
            time.sleep(0.05)
    except FileNotFoundError:
        pass
    finally:
        bridge.stop()


if __name__ == "__main__":
    main()
