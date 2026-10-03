# 燕窝 Yanwo · 设计

## 1. 它是什么 / 不是什么

**是**：一个跑在 Linux 上的**进程编排器 + 输入桥**。它管"什么时候起谁、什么时候把输入桥接上、退出了回哪儿"。

**不是**：不是容器、不是虚拟机、不是兼容层。它自己不负责跑 Windows 程序——那是 GE-Proton/Wine 干的事，燕窝只是把它们串起来。

```
Steam 库
 └─ 非 Steam 快捷方式「燕窝 Yanwo」（原生 Linux 程序）
      └─ bin/yanwo → Hub
           ├─ UI：游戏列表（手柄可操作）
           ├─ 会话：按 recipes/<id>/game.toml 起官方启动器 → 游戏 → 收尾
           └─ 输入桥（P2）：只在需要它的阶段把手柄翻译成鼠标/键盘
```

## 2. 关键决策（已定）

| # | 决策 | 理由 |
|---|---|---|
| D1 | Hub 是**原生 Linux 程序**（Python + stdlib，UI 用 tkinter），不套 Wine | 能直读 `/dev/input`、能掌控 Wine 进程与环境；没有套娃成本 |
| D2 | Steam 库里**只留一个条目**（燕窝） | 用户已确认；代价是时长/截图算在燕窝名下 |
| D3 | 游戏描述 = **recipes/ 目录下的 game.toml**，代码里不出现具体游戏 | 加游戏 = 加目录，不动代码 |
| D4 | **不获取 root**，不装系统包 | 以后要上架 Steam，不能要管理员权限 |
| D5 | 输入桥用 **xdotool**（X11/XWayland）为第一后端；uinput 仅作备选且需用户自愿配 udev | 零权限；实测可用 |
| D6 | 输入桥**分阶段开关**：Hub/官方启动器阶段开，游戏运行阶段关 | 否则玩游戏时乱动鼠标会带着视角乱转 |
| D7 | 收尾顺序：**先发 WM_DELETE_WINDOW，等 6 秒，再 TERM/KILL** | 直接 SIGKILL 会让网易启动器判"数据损坏"→重下 125G（真实事故） |
| D8 | UI 与核心解耦：`ui/base.py` 定义接口，`text_menu.py` 是 Demo 实现 | 以后换 Qt/QML 大图界面只改一个文件 |
| D9 | 显存安全阀**整合进配方**（`[safety]`）；若系统已有独立 `vram-guard.service` 则让位 | 避免双杀；P3 去掉独立服务 |
| D10 | 桌面模式与游戏模式都支持（`.desktop` + Steam 条目） | 用户要求"第三方 Proton 兼容器"在桌面也该能用 |

## 3. 状态机

```
IDLE
 └─(Hub 里选中游戏)→ PREPARE      准备环境（P1：校验/展开变量；P3：必要时跑安装）
        → LAUNCHING               按 [[steps]] 依次起进程
        → LAUNCHER               等 detect.launcher_procs 出现；输入桥 ON；Hub 窗口隐藏
             ├─(detect.game_procs 出现)→ GAME      输入桥 OFF；游戏用自己的手柄支持
             │      └─(游戏进程消失)→ 按 policy.on_game_exit：
             │             wait_launcher → 回 LAUNCHER
             │             close_launcher→ 优雅关掉官方启动器 → DONE
             └─(官方启动器自己退出)→ 按 policy.on_launcher_exit → DONE
任何状态
 ├─(Steam"停止"/SIGTERM)→ request_stop → 走同一套收尾 → DONE
 └─([safety] 触发)→ 标记原因 → 走同一套收尾 → DONE
DONE → 显示 Hub → IDLE
```

**为什么不能靠父子关系**：Wine/Proton 会重新挂父进程，`ppid` 链不可靠。所以进程识别一律用
「进程名 + 同一个 `WINEPREFIX`」（见 `core/detect.py`）。

## 4. 退出/收尾规则（对应需求第 4 点）

| 场景 | 行为 |
|---|---|
| 游戏退出、官方启动器常驻（燕云就是这样） | `on_game_exit = "wait_launcher"`：留在启动器，用户可以再进 |
| 游戏退出、启动器应一起关（交棒型启动器） | `on_game_exit = "close_launcher"` |
| 官方启动器自己退出 | 回 Hub |
| 用户按 Steam 的"停止" | SIGTERM → `request_stop` → 收尾（不能硬杀，否则进程组留孤儿） |
| 显存失控 | `[safety]` 触发 → 收尾（保护桌面不冻死） |
| 收尾细节 | 先 `xdotool windowclose` 每个窗口 → 等 6s → 若还有残留 `kill_orphan_wine` 就 TERM→KILL |

## 5. 输入桥（P2 已实现）

```
手柄(evdev /dev/input/js*) → 桥 → 输出后端 → 启动器
                                  ├─ xdotool   （默认，零权限，X11/XWayland）
                                  ├─ uinput    （备选，跨 Wayland，需一次性 udev 规则 → 与"不要 root"冲突，默认不做）
                                  └─ steam-input（委托 Valve，零维护但依赖 Steam Input 配置）
```

- 实现：`input/jsdevice.py`（读 /dev/input/js*，必须 select）、`mapper.py`（语义意图）、
  `cursor.py`（xdotool 输出）、`daemon.py`（线程 + 三模式切换）
- **模式**：`hub`（十字键/A/B 操作 Hub 菜单）、`launcher`/`cursor`（左摇杆=光标、A=左键、B=右键、
  Start=回车、X=Esc）、`off`（交给游戏自己的手柄支持）。
  游戏阶段由**窗口门控**在 `cursor`/`off` 之间自动切换：出现登录窗/公告/任意弹窗 → 开，只剩主窗口 → 关
- **多设备自动跟随**：Steam Input 可能用 EVIOCGRAB 抓住物理手柄，所以同时打开所有 js 设备，
  谁真的出事件就跟谁，并在切换时记日志（`read_many()` 一次 select 覆盖全部，别每台各等一次）
- **光标轴**：左摇杆为主、右摇杆也认（一般手柄游戏都是左摇杆移光标）；Hub 里左摇杆/十字键是菜单导航
- **刷新率**：循环 5ms（~200Hz）；光标输出走 **XTest（ctypes 直连 libX11/libXtst，0.003ms/次）**，
  比 spawn `xdotool`（1.51ms/次）快 500 倍，也不会有进程开销
- **光标外观**：不管。保持系统原装（只移动、只点击）——改形状会被 Wine/Qt 覆盖，收益也小
- 校准：`yanwo calibrate` 看编号；映射档 `input/profiles/xbox360.toml`
- 与 Steam Input **二选一**：同时开会双重输入（建议给燕窝这条快捷方式禁用 Steam Input）

## 6. 命名

**燕窝 / Yanwo**：
- 中文两个字，英文一个词，中英直译一致；
- 隐喻成立——"巢"把游戏孵在一起；
- 图标：一只两层弧线的巢 + 巢里的 ▶（`packaging/icons/yanwo.svg`）。

## 7. 非目标

- 不重分发游戏本体、账号、密钥；
- 不接管 Steam 自己的游戏（那些交给 Steam 即可）；
- 不做反作弊绕过。
