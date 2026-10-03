# 变更记录

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的写法。

## [0.2.0-demo] - 2026-10-04

P2：手柄输入桥。让"不支持手柄"的启动器能用十字键/摇杆操作。

### Added
- `input/jsdevice.py`：/dev/input/js* 读取（select + 8 字节事件解析 + 半包处理 + 多设备打开）
- `input/profile.py` + `input/profiles/xbox360.toml`：映射档（轴/键编号、死区、速度、加速度、重复间隔）
- `input/mapper.py`：原始事件 → 语义意图（nav/confirm/back/third/fourth/start），含死区与十字键按住重复
- `input/cursor.py`：xdotool 输出后端（**零 root**）；`NullCursor` 兜底
- `input/daemon.py`：守护线程 + **三模式**（hub / launcher / off）+ 多设备自动跟随
- Hub 菜单吃手柄：十字键/左摇杆选择、A 启动、B 退出；界面上显示手柄连接状态
- `yanwo calibrate`：诊断用，实时打印手柄轴/键编号

### Changed
- `Session` 新增 `on_input_mode` 回调，按阶段切换桥：准备/菜单=hub，等待/官方启动器=launcher，游戏运行=off

### Fixed
- `detect` 跳过僵尸进程（`/proc/<pid>/comm` 在僵尸上仍然存在，会导致状态机永远卡住）
- `Session` 主动 `poll()` 回收自己起的子进程
- Tk 更新全部走线程安全队列（不再从子线程直接碰 Tk）

### Tests
- 19 项单测（新增：mapper 按键边沿/死区/十字键重复、profile 往返、daemon 三模式、事件半包解析）

## [0.1.0-demo] - 2026-10-04

第一个可用骨架（P1）。目标是把"一条配方驱动的启动链"跑通，UI 先用最简单的文字菜单占位。

### Added
- 项目骨架：`src/yanwo/`（app / recipe / core / ui / input）、`bin/yanwo` 入口
- 配方系统：`recipes/<id>/game.toml`，支持 `${var}` 变量展开（变量间可互相引用）
- 启动链执行 `core/runner.py`：`kind="wine"` 完整实现（WINEPREFIX / LD_LIBRARY_PATH /
  `dll_overrides`→`WINEDLLOVERRIDES` / `dll_paths`→`WINEDLLPATH` / 自定义 env / 工作目录）；
  `native` / `shell` / `steam` 已留接口
- 状态机 `core/session.py`：PREPARE → LAUNCHING → LAUNCHER → GAME → 收尾，
  按"进程名 + WINEPREFIX"识别（不依赖父子关系）
- 收尾规则：先 `xdotool windowclose` 优雅关窗、再清残留 wine 进程（避免下载缓存被判损坏）
- 显存安全阀 `core/safety.py`：按配方 `[safety]` 监控，且检测到独立 `vram-guard.service` 时自动让位
- Demo UI `ui/text_menu.py`：文字上下菜单（tkinter，零依赖），UI 与核心解耦
- 燕云十六声（国服）配方，内置两个关键修复：
  ① Qt 软件渲染（`QT_OPENGL=software` / `QT_QUICK_BACKEND=software`）防启动器显存泄漏
  ② D3D12 强制 VKD3D-Proton / DXVK（否则游戏一进 InitState 就闪退）
- 打包物：`packaging/yanwo.desktop`、`packaging/icons/yanwo.svg`、
  `packaging/steam_shortcut.py`（多条目版 Steam 快捷方式管理）
- 文档：README、docs/DESIGN.md、docs/RECIPES.md、docs/ROADMAP.md、docs/DEV-NOTES.md
- 命令：`yanwo`（菜单）/ `yanwo list` / `yanwo run <id>` / `yanwo selftest`

### Known limitations
- 输入桥（手柄→光标/点击）尚未实现，见 ROADMAP P2
- `[install]` 只记录不执行
- 仍是文字菜单，不是封面墙

### Verified
- 燕云十六声（国服）走这条链能正常起官方启动器并进游戏（2026-10-04 实测）
