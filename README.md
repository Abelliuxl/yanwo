# 燕窝 Yanwo

> 第三方游戏聚合启动器：把 Steam 里本来没有、或者只有 Windows 版的游戏
> （网易国服那种），收进一个自己的壳里统一启动、统一收尾，顺便补上**手柄操作**。

- 名字：**燕窝 / Yanwo**（"巢"，把游戏孵在里面）
- 现在版本：**0.1.0-demo（P1）** —— 文字菜单 + 配方化启动一条链已经能跑
- 目标平台：SteamOS / Arch 系桌面，**不需要 root**，不装系统包
- 与 Steam 的关系：Steam 库里只留**一个**非 Steam 快捷方式 → 指向燕窝

---

## 现在能做什么（P1）

- `yanwo` 打开一个上下选择的文字菜单（Demo UI，tkinter，零依赖）
- 菜单内容来自 `recipes/<id>/game.toml`，**加游戏不用改代码**
- 选一个游戏 → 按配方起官方启动器（Wine/GE-Proton）→ 自动识别"启动器/游戏"两个阶段
- 退出时按配方规则收尾（先给窗口发关闭事件，再清残留 wine 进程，避免下载缓存被判损坏）
- 内置显存安全阀（系统里已有 `vram-guard.service` 时自动让位）

## 还不能做（P2+）

- 手柄输入桥（`[bridge]` 已留好位置，P2 实现）
- 自动安装游戏（`[install]` 只记录）
- 漂亮的封面墙 UI（现在是最朴素的文字菜单，UI 层已抽象）

---

## 快速开始

```bash
cd ~/workplace/yanwo

# 1) 看有哪些配方
bin/yanwo list

# 2) 自检（不弹窗，验证配方+UI 能构建）
bin/yanwo selftest

# 3) 打开菜单
bin/yanwo                 # 桌面模式
bin/yanwo --fullscreen    # 游戏模式 / 客厅

# 4) 不开界面，直接起某个游戏（调试用）
bin/yanwo run yysls-guofu
```

Steam 入口（可选，P1 先不动现有条目）：

```bash
# 先退出 Steam
systemctl --user stop app-steam@autostart.service
python3 packaging/steam_shortcut.py add "燕窝 Yanwo" ~/workplace/yanwo/bin/yanwo --overlay 0
systemctl --user start app-steam@autostart.service
```

桌面模式的应用菜单入口：

```bash
mkdir -p ~/.local/share/applications ~/.local/share/icons/hicolor/scalable/apps
cp packaging/yanwo.desktop ~/.local/share/applications/
cp packaging/icons/yanwo.svg ~/.local/share/icons/hicolor/scalable/apps/yanwo.svg
update-desktop-database ~/.local/share/applications 2>/dev/null || true
```

---

## 目录结构

```
workplace/yanwo/
├── bin/yanwo                 入口脚本（PYTHONPATH=src 直接跑，不安装）
├── recipes/                  一个游戏一个目录（纯数据）
│   └── yysls-guofu/game.toml 燕云十六声（国服）
├── src/yanwo/
│   ├── app.py                配方列表 + UI + 会话的粘合
│   ├── recipe.py             配方模型与加载
│   ├── core/
│   │   ├── session.py        ★ 状态机：启动链 + 阶段识别 + 收尾
│   │   ├── runner.py         执行 [[steps]]（wine/native/shell/steam）
│   │   ├── detect.py         按"进程名 + WINEPREFIX"识别进程
│   │   ├── safety.py         显存安全阀
│   │   └── x11.py            优雅关窗 / 前台窗口查询（xdotool）
│   ├── input/bridge.py       手柄输入桥（P2）
│   └── ui/                   界面层：text_menu.py（Demo）/ console.py / base.py（接口）
├── packaging/                .desktop、图标、Steam 快捷方式工具
├── docs/                     设计、配方协议、路线图、踩坑笔记
└── logs/ state/              运行态（已 gitignore）
```

## 文档

| 文档 | 内容 |
|---|---|
| [docs/DESIGN.md](docs/DESIGN.md) | 架构、关键决策、状态机与退出规则、命名 |
| [docs/RECIPES.md](docs/RECIPES.md) | 配方协议（每个字段的含义） |
| [docs/ROADMAP.md](docs/ROADMAP.md) | P0–P4 计划、待定问题 |
| [docs/DEV-NOTES.md](docs/DEV-NOTES.md) | 踩坑记录（DLL 覆盖、软件渲染、显存泄漏…） |
| [CHANGELOG.md](CHANGELOG.md) | 变更历史 |

## 已知限制

- 单一条目：Steam 的时长/截图/成就都会算在「燕窝」名下（已确认接受）。
- 游戏本体不随项目分发：配方只做"自动下载官方安装器 + 自动配置"。
- 官方启动器的公告/更新/年龄弹窗会打断自动流程 → 需要输入桥或人工点一下（P2 处理）。
