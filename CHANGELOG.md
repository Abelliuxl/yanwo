# 变更记录

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的写法。

## [Unreleased] - 2026-10-04

- 修复原生键盘弹出瞬间年龄提示卡（`MpayAgeTipsForm`）抢走游戏输入焦点、导致键盘什么都输不进去的问题：
  窗口规则线程新增焦点守卫，发现辅助窗拿到 `:1` 的输入焦点就 unmap 它并把焦点还给登录窗，
  会话结束再恢复；规则循环收紧到 0.5s。新增 `tools/live-focus-guard.py` 可给正在跑的会话热打补丁。
- 修复邮箱/手机号输入框下半部分点击不触发键盘（MPAY 输入行命中区比内部 Edit 控件高）。
- 修复 SteamOS 燕云首次登录年龄牌遮挡：在 gamescope 控制 display 指定登录窗，
  并临时纠正年龄窗类型；登录结束自动归还焦点。实机合成截图确认二维码可见。
- 新增配方动作 `gamescope_focus` / `gamescope_dialog`，全程维护且恢复原属性。
- 进入游戏阶段立即评估鼠标门控，避免此前已出现的登录窗无法操作。
- 第 0.8.0 版“只能桌面登录”的结论已推翻，详见 DEV-NOTES 第 20 节。

## [0.8.0-demo] - 2026-10-04

燕云登录窗"看不见"的**彻底定案**（实机 + gamescope 源码），以及配套工具。

### Added
- `tools/gs-shot.py`：gamescope 截图 + 画面分析工具（`--find` 列出画面里的块、
  `--crop/--scale` 导出可看的图）。game mode 下判断"窗口到底显示了没"的唯一可靠手段
- `tools/png.py`：自带 PNG 读写/裁剪/缩放（本机没有 PIL/numpy）
- `core/windows.py`：`_X.pixel()/input_focus()`，以及**X 错误处理器**
  （libX11 默认遇 BadMatch 会 exit(1)，一次 XGetImage 就能干掉 Hub）

### Changed
- 燕云配方的窗口规则**只保留 `activate`**（唯一有效且无害的动作），并把定案结论写进注释

### Fixed
- 之前"年龄窗挡着登录窗"的各种尝试（lower/close/hide/opacity/remap）都是错的方向：
  真相是 **gamescope 把年龄窗内容拉伸铺满了登录窗矩形**，而登录窗这一层 gamescope
  根本不画（只画 focus + override 两层）。**正确做法是到桌面模式登录一次**。

### Docs
- DEV-NOTES 19：完整证据链（三个窗口的几何/内容、gamescope 源码位置、
  8 种操作的实测结果表）+ `gamescopectl screenshot` 这个通用技巧

## [0.7.0-demo] - 2026-10-04

第三轮实机反馈：**年龄窗不再动它，改为把登录窗激活到最前**；光标只用右摇杆。

### Added
- `activate` 动作：发 EWMH `_NET_ACTIVE_WINDOW`。**这是 game mode 下唯一真的能"置前"的办法**
  （gamescope 收到后调用它自己的 XRaiseWindow → restack_win → 内部绘制列表重排）。
  燕云配方：登录窗 `match = "^(登录|Login|登入)"` → `actions = ["activate"]`，
  每 6 秒重申一次；**年龄提示完全不管了**
- `verdict_activate()`：判据改为**堆叠索引**（gamescope 从不写 `_NET_ACTIVE_WINDOW` 到 root）
- `_X.pixel()` 像素探针（desktop 可用；gamescope 上读 root 会 BadMatch → 返回 -1）
- `pointer_stick`：移光标用哪根摇杆，**默认 `right`（只用右摇杆）**

### Changed
- **左摇杆不再移光标**（用户要求）：Steam 覆盖界面/切窗口吃的是左摇杆，只用右摇杆就不会打架。
  Hub 菜单导航仍可用左摇杆；想改回 `pointer_stick = "left"` 或 `"both"`
- 饱和度/测试同步更新

### Fixed
- **`_X` 装了 X 错误处理器**：libX11 默认处理器遇到 BadMatch/XGetImage 失败会直接 `exit(1)`
  ——一次探测就能把 Hub 干掉。现在降级成 `last_error`，探测失败返回 -1
- 之前 `activate` 的"没生效"是**误报**：我在用 gamescope 根本不写的 root 属性当判据

### Docs
- DEV-NOTES 17 重写：从 gamescope 源码得出的"置前"机制 + 三个坑（属性不写、外部 raise 被吞、XGetImage BadMatch）

### Tests
- 42 项（新增 activate 判定 3 项）

## [0.6.0-demo] - 2026-10-04

按实机反馈第二轮修（年龄窗仍在前 + Steam 覆盖界面和光标打架）。

### Fixed
- **年龄提示仍然挡在前面**：上一次用 `lower` 压层级，X 堆叠确实变了但**gamescope 的视觉层级不跟它走**。
  改成 `close`（发 WM_DELETE_WINDOW 让应用自己关掉这个提示），要更温和可换 `hide`。
  配方注释里写清了为什么 `lower` 在 game mode 下没用。

### Added
- **输入桥暂停开关**：`[bridge] pause_combo`（默认 `["select","third"]` = Select+X），
  按一次暂停（**完全不再注入**，让 Steam 覆盖界面/切窗口自己吃手柄），再按恢复；
  Hub 底部显示 `⏸ 已暂停`
- `[bridge] pause_windows`：命中这些标题的窗口时自动暂停（正则）
- `BridgeGate` 支持 `pause_windows`（优先级高于 cursor_windows）

### Docs
- DEV-NOTES 17：gamescope 视觉层级 ≠ X 堆叠；DEV-NOTES 18：桥与覆盖界面打架的原因与缓解

### Tests
- 34 项（新增：组合键检测、暂停时禁止注入、pause_windows 强制关）

## [0.5.0-demo] - 2026-10-04

游戏里的 UI 窗口也要能用光标（用户："登陆窗口也应该是要有模拟鼠标的，只有游戏的本体是不需要鼠标的"）。

### Added
- `[bridge] cursor_windows`（标题正则列表）+ `cursor_on_dialogs`（默认 true）：
  **游戏本体阶段按窗口自动开关光标桥** —— 命中登录窗/公告/设置等，或出现任意弹窗
  （`WM_TRANSIENT_FOR` 非 0）→ 切到 `cursor` 模式；只剩主窗口 → 切回 `off`
- 输入桥新增 `cursor` 模式（动作与 `launcher` 相同），Hub 菜单仍是 `hub` 模式
- `BridgeGate`：判定逻辑可单测（只剩主窗口/有弹窗/命中标题/忽略 IME 辅助窗 4 种情况）
- 窗口守护改为**全程**运行：规则只观察前 `watch_seconds` 秒，桥门控一直评估到会话结束
- 燕云配方配上登录/公告/设置等 `cursor_windows`

### Fixed
- `WM_TRANSIENT_FOR` 读不出来：32 位属性只有 4 字节，原来判 `len(raw) >= 8` 永远得到 0
  （现在能正确识别"弹窗"，通用启发式才生效）

### Tests
- 31 项（新增 BridgeGate 4 项）

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
