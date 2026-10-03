#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""燕窝 Yanwo —— Steam 非 Steam 快捷方式管理（多条目版）。

原来的 ~/Games/yysls/steam-shortcut.py 只能写一条（写文件时会清掉其它条目），
这个版本会**保留其它条目**，支持：list / add / repoint / remove / set-overlay。

改 shortcuts.vdf 前必须退出 Steam（否则 Steam 退出时会覆盖回去）：
    systemctl --user stop app-steam@autostart.service
    ... 改完 ...
    systemctl --user start app-steam@autostart.service
"""
from __future__ import annotations

import argparse
import glob
import os
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

STEAM = Path(os.path.expanduser("~/.local/share/Steam"))
USERDATA = STEAM / "userdata"


# --------------------------- 二进制 VDF ---------------------------
def _w_str(f, k, v):
    f.write(b"\x01" + k.encode() + b"\x00" + v.encode() + b"\x00")


def _w_int(f, k, v):
    f.write(b"\x02" + k.encode() + b"\x00" + struct.pack("<I", v & 0xFFFFFFFF))


def _write_map(f, d):
    for k, (t, val) in d.items():
        if t == "str":
            _w_str(f, k, val)
        elif t == "int":
            _w_int(f, k, val)
        elif t == "map":
            f.write(b"\x00" + k.encode() + b"\x00")
            _write_map(f, val)
            f.write(b"\x08")


def _read_cstr(f) -> str:
    out = bytearray()
    while True:
        c = f.read(1)
        if not c or c == b"\x00":
            break
        out += c
    return out.decode("utf-8", "replace")


def _read_map(f) -> dict:
    d = {}
    while True:
        t = f.read(1)
        if not t or t == b"\x08":
            return d
        if t == b"\x00":
            k = _read_cstr(f)
            d[k] = ("map", _read_map(f))
        elif t == b"\x01":
            k = _read_cstr(f)
            d[k] = ("str", _read_cstr(f))
        elif t == b"\x02":
            k = _read_cstr(f)
            d[k] = ("int", struct.unpack("<I", f.read(4))[0])
        else:
            raise ValueError("unknown vdf type %r" % t)


def read_shortcuts(path: Path) -> dict:
    with open(path, "rb") as f:
        if f.read(1) != b"\x00":
            raise ValueError("not a binary vdf")
        _read_cstr(f)  # "shortcuts"
        return _read_map(f)


def write_shortcuts(path: Path, entries: dict) -> None:
    with open(path, "wb") as f:
        f.write(b"\x00shortcuts\x00")
        _write_map(f, entries)
        f.write(b"\x08")  # 结束 shortcuts map
        f.write(b"\x08")  # 结束根对象


def app_id(exe: str, name: str) -> int:
    return (zlib.crc32(('"%s"' % exe).encode() + name.encode()) & 0xFFFFFFFF) | 0x80000000


def make_entry(name: str, exe: str, appid: int, startdir: str = "", overlay: int = 0) -> dict:
    return {
        "appid": ("int", appid),
        "AppName": ("str", name),
        "Exe": ("str", '"%s"' % exe),
        "StartDir": ("str", '"%s"' % (startdir or os.path.dirname(exe))),
        "icon": ("str", ""),
        "ShortcutPath": ("str", ""),
        "LaunchOptions": ("str", ""),
        "IsHidden": ("int", 0),
        "AllowDesktopConfig": ("int", 1),
        "AllowOverlay": ("int", overlay),
        "OpenVR": ("int", 0),
        "Devkit": ("int", 0),
        "DevkitGameID": ("str", ""),
        "DevkitOverrideAppID": ("int", 0),
        "LastPlayTime": ("int", 0),
        "FlatpakAppID": ("str", ""),
        "tags": ("map", {}),
    }


# --------------------------- 辅助 ---------------------------
def profiles() -> list[Path]:
    out = [Path(d) for d in glob.glob(str(USERDATA / "*")) if (Path(d) / "config").is_dir()]
    return sorted(out, key=lambda p: p.stat().st_mtime, reverse=True)


def shortcuts_path(profile: Path) -> Path:
    return profile / "config" / "shortcuts.vdf"


def steam_running() -> bool:
    return subprocess.run(["pgrep", "-x", "steam"], capture_output=True).returncode == 0


def load(path: Path) -> dict:
    if not path.exists():
        return {}
    return read_shortcuts(path)


def by_name(entries: dict, name: str) -> str | None:
    for k, v in entries.items():
        if v[0] == "map" and v[1].get("AppName", (None, ""))[1] == name:
            return k
    return None


def backup(path: Path) -> None:
    if path.exists():
        shutil.copy2(path, f"{path}.bak-{int(__import__('time').time())}")


# --------------------------- 命令 ---------------------------
def cmd_list(_a) -> int:
    for prof in profiles():
        sp = shortcuts_path(prof)
        print(f"profile: {prof}  存在: {sp.exists()}")
        if sp.exists():
            for k, v in sorted(load(sp).items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0):
                if v[0] == "map":
                    d = v[1]
                    print("  [%s] appid=%s overlay=%s\n      name=%s\n      exe=%s\n      start=%s"
                          % (k, d.get("appid", (None, "?"))[1],
                             d.get("AllowOverlay", (None, "?"))[1],
                             d.get("AppName", (None, "?"))[1],
                             d.get("Exe", (None, "?"))[1],
                             d.get("StartDir", (None, "?"))[1]))
    return 0


def _write(entries: dict) -> int:
    prof = profiles()[0]
    sp = shortcuts_path(prof)
    sp.parent.mkdir(parents=True, exist_ok=True)
    backup(sp)
    write_shortcuts(sp, entries)
    print(f"[+] 已写入 {sp}（共 {len(entries)} 条）")
    return 0


def cmd_add(a) -> int:
    if steam_running():
        print("[!] Steam 正在运行，先退出：systemctl --user stop app-steam@autostart.service")
        return 1
    exe = str(Path(a.exe).expanduser().resolve())
    if not Path(exe).exists():
        print(f"[!] 找不到 {exe}")
        return 1
    entries = load(shortcuts_path(profiles()[0]))
    aid = app_id(exe, a.name)
    key = by_name(entries, a.name) or (str(max([int(k) for k in entries] or [-1]) + 1))
    entries[key] = ("map", make_entry(a.name, exe, aid, a.startdir or "", a.overlay))
    print(f"[+] {a.name}  appid={aid} (0x{aid:08x})  overlay={a.overlay}")
    return _write(entries)


def cmd_remove(a) -> int:
    if steam_running():
        print("[!] Steam 正在运行，先退出")
        return 1
    prof = profiles()[0]
    sp = shortcuts_path(prof)
    entries = load(sp)
    key = by_name(entries, a.name)
    if key is None:
        print(f"[!] 没找到 {a.name}")
        return 1
    del entries[key]
    print(f"[+] 删除 {a.name}")
    return _write(entries)


def cmd_repoint(a) -> int:
    if steam_running():
        print("[!] Steam 正在运行，先退出")
        return 1
    prof = profiles()[0]
    sp = shortcuts_path(prof)
    entries = load(sp)
    key = by_name(entries, a.name)
    if key is None:
        print(f"[!] 没找到 {a.name}")
        return 1
    d = entries[key][1]
    exe = str(Path(a.exe).expanduser().resolve())
    d["Exe"] = ("str", '"%s"' % exe)
    d["StartDir"] = ("str", '"%s"' % (a.startdir or os.path.dirname(exe)))
    print(f"[+] {a.name} -> {exe}\n    appid 保持不变: {d['appid'][1]}")
    return _write(entries)


def cmd_overlay(a) -> int:
    if steam_running():
        print("[!] Steam 正在运行，先退出")
        return 1
    entries = load(shortcuts_path(profiles()[0]))
    key = by_name(entries, a.name)
    if key is None:
        print(f"[!] 没找到 {a.name}")
        return 1
    entries[key][1]["AllowOverlay"] = ("int", int(a.value))
    print(f"[+] {a.name} AllowOverlay={a.value}")
    return _write(entries)


def main() -> int:
    p = argparse.ArgumentParser(description="燕窝 Yanwo 的 Steam 快捷方式工具")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")

    for nm, fn in (("add", cmd_add), ("repoint", cmd_repoint)):
        sp = sub.add_parser(nm)
        sp.add_argument("name")
        sp.add_argument("exe")
        sp.add_argument("--startdir", default="")
        if nm == "add":
            sp.add_argument("--overlay", type=int, default=0)
        sp.set_defaults(fn=fn)

    sr = sub.add_parser("remove")
    sr.add_argument("name")
    sr.set_defaults(fn=cmd_remove)

    so = sub.add_parser("set-overlay")
    so.add_argument("name")
    so.add_argument("value", type=int, choices=[0, 1])
    so.set_defaults(fn=cmd_overlay)

    a = p.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
