"""执行启动链里的每一步。

P1 只实现 kind="wine"（其余占位，接口先定好，后面加不影响流程）。
"""
from __future__ import annotations

import logging
import os
import shlex
import subprocess
from pathlib import Path

from ..recipe import Recipe, Step

log = logging.getLogger("yanwo.runner")


def _join(v: object, sep: str) -> str:
    """列表按指定分隔符拼起来（WINEDLLOVERRIDES 用 ';'，WINEDLLPATH/LD_LIBRARY_PATH 用 ':'）。"""
    if isinstance(v, (list, tuple)):
        return sep.join(str(x) for x in v)
    return str(v)


def build_env(step: Step, recipe: Recipe, base: dict[str, str] | None = None) -> dict[str, str]:
    """按步骤拼环境变量：Proton 的 DLL 覆盖/搜索路径 + 配方自定义 env。"""
    env = dict(base or os.environ)
    prefix = step.get("prefix")
    if prefix:
        env["WINEPREFIX"] = str(prefix)

    # LD_LIBRARY_PATH：GE-Proton 的 wine 需要它才能跑起来
    proton_dir = step.get("proton_dir")
    if proton_dir:
        files = Path(str(proton_dir)) / "files"
        env["LD_LIBRARY_PATH"] = ":".join(
            [str(files / "lib/x86_64-linux-gnu"), str(files / "lib"), env.get("LD_LIBRARY_PATH", "")]
        ).rstrip(":")

    if "dll_overrides" in step.data:
        env["WINEDLLOVERRIDES"] = _join(step.get("dll_overrides"), ";")
    if "dll_paths" in step.data:
        env["WINEDLLPATH"] = _join(step.get("dll_paths"), ":")

    env.setdefault("WINEDEBUG", os.environ.get("WINEDEBUG", "err+all"))
    for k, v in (step.get("env") or {}).items():
        env[str(k)] = _join(v, ":")
    return env


def command_for(step: Step, recipe: Recipe) -> tuple[list[str], str | None]:
    """返回 (argv, cwd)。"""
    kind = step.kind
    cwd = step.get("workdir") or None
    if kind == "wine":
        wine = step.get("wine") or "${proton_wine}"
        exe = step.get("exe")
        if not exe:
            raise ValueError("wine 步骤缺少 exe")
        return [str(wine), str(exe), *[str(a) for a in step.get("args", [])]], cwd
    if kind == "shell":
        return ["/bin/sh", "-c", str(step.get("command", ""))], cwd
    if kind == "native":
        exe = step.get("exe")
        if not exe:
            raise ValueError("native 步骤缺少 exe")
        return [str(exe), *[str(a) for a in step.get("args", [])]], cwd
    if kind == "steam":
        return ["xdg-open", f"steam://rungameid/{step.get('appid')}"], None
    raise NotImplementedError(f"还没实现 kind={kind}")


def launch_step(step: Step, recipe: Recipe) -> subprocess.Popen:
    argv, cwd = command_for(step, recipe)
    env = build_env(step, recipe)
    if cwd and not Path(cwd).is_dir():
        raise FileNotFoundError(f"工作目录不存在: {cwd}")
    log.info("exec: %s  (cwd=%s)", shlex.join(argv), cwd or "-")
    log.debug("env 关键项: WINEPREFIX=%s WINEDLLOVERRIDES=%s",
              env.get("WINEPREFIX"), env.get("WINEDLLOVERRIDES"))
    return subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # 独立进程组，便于整组收尾
    )


def launch_chain(recipe: Recipe) -> list[subprocess.Popen]:
    return [launch_step(s, recipe) for s in recipe.steps]
