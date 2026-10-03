"""控制台 UI：给 `yanwo run <id>` 和调试用（无需图形环境）。"""
from __future__ import annotations


class ConsoleUI:
    def __init__(self) -> None:
        self._games: list[tuple[str, str]] = []
        self._status = ""

    def set_games(self, games: list[tuple[str, str]]) -> None:
        self._games = list(games)

    def set_status(self, text: str) -> None:
        self._status = text
        print(f"[yanwo] {text}", flush=True)

    def hide(self) -> None:
        pass

    def show(self) -> None:
        pass

    def refresh(self) -> None:
        pass

    def run(self) -> None:
        pass

    def destroy(self) -> None:
        pass
