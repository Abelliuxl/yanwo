"""Demo UI：文字上下菜单（tkinter，零依赖、无需 root）。

刻意做得很朴素——它只是 P1 的占位实现。配色/字体/布局抽在文件顶部的常量里，
以后换成 Qt/QML 只会影响这一个文件。所有跨线程更新都走 _post()，避免 Tk 线程问题。
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from typing import Callable

CJK = "Noto Sans CJK SC"
BG = "#0f1115"
BG_SEL = "#f0c040"
FG = "#e9ecf1"
FG_SEL = "#101418"
DIM = "#7f8894"

TITLE_SIZE = 34
ITEM_SIZE = 26
SUB_SIZE = 14
TIP_SIZE = 13


class TextMenuUI:
    def __init__(
        self,
        games: list[tuple[str, str]],
        on_launch: Callable[[int], None],
        fullscreen: bool = False,
        on_quit: Callable[[], None] | None = None,
    ) -> None:
        self.games = list(games)
        self.on_launch = on_launch
        self.on_quit = on_quit
        self.sel = 0
        self._rows: list[tuple[tk.Frame, tk.Label, tk.Label]] = []

        self.root = tk.Tk()
        self.root.title("燕窝 Yanwo")
        self.root.configure(bg=BG)
        if fullscreen:
            self.root.attributes("-fullscreen", True)
        else:
            self.root.geometry("1000x620")
        self.root.protocol("WM_DELETE_WINDOW", self._quit)

        self.f_title = tkfont.Font(family=CJK, size=TITLE_SIZE, weight="bold")
        self.f_item = tkfont.Font(family=CJK, size=ITEM_SIZE)
        self.f_sub = tkfont.Font(family=CJK, size=SUB_SIZE)
        self.f_tip = tkfont.Font(family=CJK, size=TIP_SIZE)

        self._build()
        self.root.bind("<Escape>", lambda e: self._quit())
        self.root.bind("<Up>", lambda e: self._move(-1))
        self.root.bind("<Down>", lambda e: self._move(1))
        self.root.bind("<k>", lambda e: self._move(-1))
        self.root.bind("<j>", lambda e: self._move(1))
        self.root.bind("<Return>", lambda e: self._launch())
        self.root.bind("<space>", lambda e: self._launch())
        self.root.bind("<r>", lambda e: self.refresh())

    # ---------- 构建 ----------
    def _build(self) -> None:
        head = tk.Frame(self.root, bg=BG)
        head.pack(fill="x", padx=48, pady=(36, 8))
        tk.Label(head, text="燕窝", font=self.f_title, fg=FG, bg=BG).pack(side="left")
        tk.Label(head, text="  Yanwo · 第三方游戏启动器", font=self.f_sub, fg=DIM, bg=BG).pack(
            side="left", pady=(16, 0)
        )

        self.listbox = tk.Frame(self.root, bg=BG)
        self.listbox.pack(fill="both", expand=True, padx=48, pady=12)

        self.footer = tk.Label(self.root, text="", font=self.f_tip, fg=DIM, bg=BG, anchor="w")
        self.footer.pack(fill="x", padx=48, pady=(0, 6))
        self.status = tk.Label(self.root, text="", font=self.f_sub, fg=FG, bg=BG, anchor="w")
        self.status.pack(fill="x", padx=48, pady=(0, 28))

        self._render_rows()

    def _render_rows(self) -> None:
        for child in self.listbox.winfo_children():
            child.destroy()
        self._rows.clear()
        for i, (name, sub) in enumerate(self.games):
            row = tk.Frame(self.listbox, bg=BG, cursor="hand2")
            row.pack(fill="x", pady=4)
            lab = tk.Label(row, text=name, font=self.f_item, fg=FG, bg=BG, anchor="w")
            lab.pack(fill="x", padx=18, pady=(8, 0))
            sublab = tk.Label(row, text=sub or "", font=self.f_sub, fg=DIM, bg=BG, anchor="w")
            sublab.pack(fill="x", padx=18, pady=(0, 8))
            row.bind("<Button-1>", lambda e, idx=i: self._click(idx))
            lab.bind("<Button-1>", lambda e, idx=i: self._click(idx))
            row.bind("<Double-Button-1>", lambda e, idx=i: self._click(idx, launch=True))
            lab.bind("<Double-Button-1>", lambda e, idx=i: self._click(idx, launch=True))
            self._rows.append((row, lab, sublab))
        if not self.games:
            tk.Label(
                self.listbox,
                text="（recipes/ 里还没有配方）",
                font=self.f_item,
                fg=DIM,
                bg=BG,
            ).pack(pady=40)
        self._highlight()
        self.footer.configure(text="↑ ↓ / j k 选择     Enter 启动     R 刷新     Esc 退出")

    def _highlight(self) -> None:
        for i, (row, lab, sub) in enumerate(self._rows):
            on = i == self.sel
            row.configure(bg=BG_SEL if on else BG)
            lab.configure(bg=BG_SEL if on else BG, fg=FG_SEL if on else FG)
            sub.configure(bg=BG_SEL if on else BG, fg=FG_SEL if on else DIM)

    # ---------- 交互 ----------
    def _move(self, d: int) -> None:
        if not self.games:
            return
        self.sel = (self.sel + d) % len(self.games)
        self._highlight()

    def _click(self, idx: int, launch: bool = False) -> None:
        self.sel = idx
        self._highlight()
        if launch:
            self._launch()

    def _launch(self) -> None:
        if not self.games:
            return
        try:
            self.on_launch(self.sel)
        except Exception as e:  # noqa: BLE001
            self.set_status(f"启动失败：{e}")

    def _quit(self) -> None:
        if self.on_quit:
            try:
                self.on_quit()
            except Exception:  # noqa: BLE001
                pass
        self.root.destroy()

    # ---------- 线程安全的对外方法 ----------
    def _post(self, fn: Callable, *a) -> None:
        try:
            self.root.after(0, lambda: fn(*a))
        except RuntimeError:
            pass

    def set_games(self, games: list[tuple[str, str]]) -> None:
        self._post(self._set_games, games)

    def _set_games(self, games: list[tuple[str, str]]) -> None:
        self.games = list(games)
        self.sel = 0
        self._render_rows()

    def set_status(self, text: str) -> None:
        self._post(lambda t=text: self.status.configure(text=t))

    def hide(self) -> None:
        self._post(self.root.withdraw)

    def show(self) -> None:
        self._post(self.root.deiconify)

    def refresh(self) -> None:
        self._post(self._render_rows)

    def run(self) -> None:
        self.root.mainloop()

    def destroy(self) -> None:
        try:
            self.root.destroy()
        except Exception:  # noqa: BLE001
            pass
