#!/usr/bin/env python3
"""Apply event-driven gamescope focus repair to an already running session."""
from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from yanwo.recipe import find_recipe
from yanwo.core.windows import WindowRules
from yanwo.core.session import Session
from dataclasses import replace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("recipe")
    parser.add_argument("--parent", type=int, required=True)
    args = parser.parse_args()
    parent = Path(f"/proc/{args.parent}/stat")
    token = parent.read_text().rsplit(")", 1)[1].split()[19]
    recipe = find_recipe(args.recipe)
    if recipe is None:
        raise SystemExit("Recipe not found")
    rules = WindowRules(recipe.window_rules)
    shadows = Session(replace(recipe, windows={"hide_classes": recipe.windows.get("hide_classes", [])}), None)
    try:
        shadows._start_window_blockers()
        while parent.exists() and parent.read_text().rsplit(")", 1)[1].split()[19] == token:
            rules.sync_gamescope()
            rules._gamescope.start_watch()
            time.sleep(.25)
    except FileNotFoundError:
        pass
    finally:
        shadows._stop_window_rules()
        rules._gamescope.release()


if __name__ == "__main__":
    main()
