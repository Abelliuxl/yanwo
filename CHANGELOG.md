# 变更记录

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的写法。

## [0.4.0-demo] - 2026-10-04

窗口问题配置化（用户："这个优化点每个游戏都可能不一样，把它做成能拓展的配置模式"）。

### Added
- **窗口规则引擎** `core/windows.py`：
  - 纯 ctypes 直连 X11 读窗口（标题/pid/几何/映射状态），无进程开销
  - 规则来自配方 `[windows]`：`match`(标题正则) / `actions` / `priority` / `stop` / `repeat_seconds` / `enabled`
  - 动作：`lower`（**game mode 实测唯一有效**）/ `close` / `focus` / `raise` / `move:x,y` /
    `resize:w,h` / `remap` / `hide` / `click`
  - **每条动作执行后回读验证**，把"没生效"写进日志（不会假装成功）
  - 默认只作用于可见、非 1x1 的窗口；窗口集合变化或到 `repeat_seconds` 时触发
- 燕云配方加了 `[windows]`：`MpayAgeTipsForm` → `lower`（年龄提示压底，登录窗自然在前）；
  `登录` → `focus`（desktop 有效）

### Fixed
- `XGetWindowProperty` 少传 `actual_format` 参数导致**标题被截断/乱码**（现在读 `_NET_WM_NAME`，中文正常）
- 窗口列表过滤 IME/托盘等 1x1 隐藏窗口（`map_state` 偏移 92 实测确认）

### Docs
- RECIPES：`[windows]` 参考 + **动作支持情况对照表**（game mode vs desktop mode）
- DEV-NOTES 14/15：gamescope 只管自己的窗口布局；X11 读窗口的两个坑

### Tests
- 27 项（新增：窗口标题匹配/中文/隐藏窗口过滤/坏正则不炸/优先级排序）

## [0.3.0-demo] - 2026-10-04

按实机反馈修的三点（P2 手感/逻辑）。

### Fixed
- **光标卡顿**：两个真因 —— ① 主循环对每个 js 设备各 `select` 一次（4×20ms=80ms/轮）；
  ② 每次移动都 spawn `xdotool`（1.51ms/次）。
  现在：`read_many()` 一次 select 覆盖所有设备（4.81ms/轮），并新增 **XTest 后端**
  （ctypes 直连 libX11/libXtst，0.003ms/次，零进程开销）→ 循环 ~200Hz，光标丝滑。
- **摇杆逻辑**：光标改为**左摇杆为主**（右摇杆也认），符合一般手柄游戏习惯；
  Hub 菜单里左摇杆/十字键导航；官方启动器阶段左摇杆只移光标、不触发方向键（十字键仍映射方向键）。

### Changed
- `cursor.make_cursor()` 自动选择后端：XTest → xdotool → 空实现；启动时记录用的是哪个
- 光标**完全保持系统原装**：不改形状也不改大小（Wine/Qt 会反复重设光标，抢过来不可靠；
  用户实测原装够用，见 DEV-NOTES 13）

### Added
- `input/profiles/xbox360.toml` 支持 `move_x2/move_y2`（副摇杆轴）
- ROADMAP P3：多窗口/登录窗口切换、自创光标（Xcursor 主题）两条待定事项

### Tests
- 21 项（新增：双摇杆都能移光标、Hub/启动器两种模式下左摇杆行为差异）

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
