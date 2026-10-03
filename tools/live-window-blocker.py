#!/usr/bin/env python3
"""Apply configured auxiliary-window suppression to an existing Yanwo session."""
from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from yanwo.recipe import find_recipe
from yanwo.core.session import Session


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("recipe")
    parser.add_argument("--parent", type=int, required=True)
    args = parser.parse_args()
    parent = Path(f"/proc/{args.parent}/stat")
    # Include the start time so reusing a Unix PID cannot extend this hotfix.
    token = parent.read_text().rsplit(")", 1)[1].split()[19]
    recipe = find_recipe(args.recipe)
    if recipe is None:
        raise SystemExit("Recipe not found")
    session = Session(recipe, ui=None)
    try:
        session._start_window_blockers()
        while parent.exists():
            if parent.read_text().rsplit(")", 1)[1].split()[19] != token:
                break
            if any(p.poll() is not None for p in session._window_blockers):
                raise SystemExit("Native window blocker exited")
            time.sleep(0.25)
    except FileNotFoundError:
        pass
    finally:
        session._stop_window_rules()


if __name__ == "__main__":
    main()
