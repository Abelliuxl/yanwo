"""配方(recipe)模型与加载。

一个游戏 = recipes/<id>/game.toml，纯数据；Hub 代码里不允许出现具体游戏名。
协议见 docs/RECIPES.md。
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .paths import HOME, RECIPES_DIR, REPO_ROOT


@dataclass
class Step:
    """启动链里的一步（列在 [[steps]] 里）。"""

    kind: str
    data: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


@dataclass
class Recipe:
    id: str
    name: str
    subtitle: str = ""
    launcher_kind: str = "wine"
    steps: list[Step] = field(default_factory=list)
    detect_launcher: list[str] = field(default_factory=list)
    detect_game: list[str] = field(default_factory=list)
    policy: dict[str, Any] = field(default_factory=dict)
    safety: dict[str, Any] = field(default_factory=dict)
    bridge: dict[str, Any] = field(default_factory=dict)
    install: dict[str, Any] = field(default_factory=dict)
    vars: dict[str, Any] = field(default_factory=dict)
    dir: Path | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    # ---- 便捷访问 ----
    @property
    def prefix_hint(self) -> str:
        for s in self.steps:
            p = s.get("prefix")
            if p:
                return Path(str(p)).name
        return ""

    def policy_get(self, key: str, default: Any = None) -> Any:
        return self.policy.get(key, default)


def _resolve_ctx(ctx: dict[str, str], rounds: int = 5) -> dict[str, str]:
    """把 ctx 里互相引用的 ${var} 展开（vars 里可以写 prefix = "${compatdata}/pfx"）。"""
    for _ in range(rounds):
        changed = False
        for k, v in list(ctx.items()):
            nv = v
            for k2, v2 in ctx.items():
                nv = nv.replace("${" + k2 + "}", v2)
            if nv != v:
                ctx[k] = nv
                changed = True
        if not changed:
            break
    return ctx


def _expand(obj: Any, ctx: dict[str, str]) -> Any:
    """递归把字符串里的 ${var} 展开。未知变量原样保留（便于排查）。"""
    if isinstance(obj, str):
        out = obj
        for k, v in ctx.items():
            out = out.replace("${" + k + "}", str(v))
        return str(Path(out).expanduser()) if out.startswith("~") else out
    if isinstance(obj, list):
        return [_expand(x, ctx) for x in obj]
    if isinstance(obj, dict):
        return {k: _expand(v, ctx) for k, v in obj.items()}
    return obj


def _ctx(recipe_id: str, extra: dict[str, Any] | None = None) -> dict[str, str]:
    ctx = {
        "home": str(HOME),
        "repo": str(REPO_ROOT),
        "recipe_id": recipe_id,
        "recipe_dir": str(RECIPES_DIR / recipe_id),
        "steam": str(HOME / ".local/share/Steam"),
        "proton_dir": str(HOME / ".local/share/Steam/compatibilitytools.d/GE-Proton10-32"),
        "proton_wine": str(
            HOME / ".local/share/Steam/compatibilitytools.d/GE-Proton10-32/files/bin/wine"
        ),
        "proton_lib": str(
            HOME / ".local/share/Steam/compatibilitytools.d/GE-Proton10-32/files/lib"
        ),
    }
    if extra:
        ctx.update({k: str(v) for k, v in extra.items()})
    return ctx


def load_recipe(path: Path) -> Recipe:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    rid = raw.get("id") or path.parent.name
    ctx = _resolve_ctx(_ctx(rid, raw.get("vars")))
    raw = _expand(raw, ctx)

    steps = [Step(kind=s.pop("kind", "wine"), data=s) for s in raw.get("steps", [])]
    det = raw.get("detect", {})
    return Recipe(
        id=rid,
        name=raw.get("name", rid),
        subtitle=raw.get("subtitle", ""),
        launcher_kind=raw.get("launcher_kind", "wine"),
        steps=steps,
        detect_launcher=list(det.get("launcher_procs", [])),
        detect_game=list(det.get("game_procs", [])),
        policy=raw.get("policy", {}),
        safety=raw.get("safety", {}),
        bridge=raw.get("bridge", {}),
        install=raw.get("install", {}),
        vars=raw.get("vars", {}),
        dir=path.parent,
        raw=raw,
    )


def load_recipes(recipes_dir: Path | None = None) -> list[Recipe]:
    """扫描 recipes/*/game.toml，按 name 排序返回。坏配方只记日志、不炸整体。"""
    d = recipes_dir or RECIPES_DIR
    out: list[Recipe] = []
    for toml in sorted(d.glob("*/game.toml")):
        try:
            out.append(load_recipe(toml))
        except Exception as e:  # noqa: BLE001
            import logging

            logging.getLogger("yanwo").warning("配方加载失败 %s: %s", toml, e)
    out.sort(key=lambda r: r.name)
    return out


def find_recipe(rid: str) -> Recipe | None:
    for r in load_recipes():
        if r.id == rid:
            return r
    return None
