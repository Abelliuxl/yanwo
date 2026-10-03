# 踩坑笔记（环境相关，务必保留）

这些都是 2026-10-03 那台机器上**真金白银换来的**结论。写配方时请优先复用。

## 1. 游戏本体 D3D12 → 必须用 VKD3D-Proton，否则一进 InitState 就闪退

- 症状：`yysls.exe` 起来约 20–25 秒后 `exit game`，游戏自己的 `check_hex.txt` 写
  `MimallocAdapter: called before inited`；崩溃转储是 `0xC0000005`（空指针读），fault 在 `yysls.exe` 里。
- 根因：游戏是 **D3D12**。用普通 `wine`（不带 Proton 的 DLL 覆盖）时，Wine 会选**自带的旧 vkd3d**
  （进程 maps 里出现 `libvkd3d-1.dll`），能力不足 → 引擎初始化失败。
- 解法（已固化进配方 `dll_overrides` / `dll_paths`）：
  ```toml
  dll_overrides = ["d3d11=n,b","d3d10core=n,b","d3d10=n,b","d3d10_1=n,b",
                   "d3d9=n,b","dxgi=n,b","d3d12=n,b","d3d12core=n,b"]
  dll_paths = ["${proton_lib}/wine/vkd3d-proton","${proton_lib}/vkd3d","${proton_lib}/wine"]
  ```
- 验证：游戏进程 `/proc/<pid>/maps` 里**只有 `d3d12core`、没有 `libvkd3d`** = 用上 VKD3D-Proton 了。
- 参考：Proton 的 `files/lib/wine/vkd3d-proton/`（`d3d12.dll` 163KB + `d3d12core.dll` 5.1MB）会拷进 prefix，
  并把这些 DLL 的 override 设为 native（`proton` 脚本里的 `vkd3d_protonfiles` / `dxvkfiles`）。

## 2. 官方启动器（Qt）会以 ~120MB/s 泄漏显存 → 必须强制软件渲染

- 症状：`launcher.exe` 进程显存 1.4G 还在涨、约 105–117MB/s；7 分钟到 ~43GB，撑爆 16G 显存 + GTT，
  触发 amdgpu/TTM 在 `ttm_global_swapout` 的 ww_mutex 死锁 → **整个桌面冻死，只能硬重启**。
- 解法（已固化）：`QT_OPENGL=software` + `QT_QUICK_BACKEND=software`（写进 `[steps.env]`，
  Wine 会把 Unix 环境带给 Windows 进程）。之后启动器显存稳定 ~90MB。
- 备选：写进 prefix 注册表 `HKCU\Environment`（这样任何启动方式都生效）。

## 3. 别硬杀正在下载的启动器

- 直接 SIGKILL / 硬重启打断下载 → 起步器会把整包判为"数据损坏" → **从头重下 ~125G**（真实事故）。
- 所以收尾顺序固定：`xdotool windowclose`（等于点右上角 X）→ 等 6 秒 → 才 TERM/KILL。

## 4. 4K + KDE 300% 缩放下的 DPI

- 本机 HDMI 是 3840×2160 + KDE scale 3（`Xft.dpi=288`），Wine 默认 96 DPI → 启动器界面小得离谱。
- 解法：prefix 注册表 `HKCU\Control Panel\Desktop\LogPixels = 288`（+`Software\Wine\Fonts`）。
- 用普通 wine 改注册表：
  ```bash
  G=~/.local/share/Steam/compatibilitytools.d/GE-Proton10-32
  P=...
  WINEPREFIX=$P LD_LIBRARY_PATH=$G/files/lib/x86_64-linux-gnu:$G/files/lib \
    $G/files/bin/wine reg add 'HKCU\Control Panel\Desktop' /v LogPixels /t REG_DWORD /d 288 /f
  ```

## 5. 想拿到 Wine 的错误输出，别设 `WINEDEBUG=-all`

- 我们调 D3D12 问题时被这个害过：日志只剩 Mesa 的 RADV 警告，看不到 Wine 的错误。
- 建议 `WINEDEBUG=err+all`（或至少别全关）。

## 6. xdotool 需要正确的 DISPLAY/XAUTHORITY

- 桌面模式：`DISPLAY=:0`，`XAUTHORITY=/run/user/1000/xauth_XXXX`（可以找 `Xwayland` 进程的 environ 拿）。
- **游戏模式**：启动器跑在 gamescope 自己的 X 里，DISPLAY 不同 → 桥/关窗工具要能自动扫
  `/tmp/.X11-unix/` 或从进程 environ 里提取。

## 7. Steam 相关

- 重启 Steam：`systemctl --user stop/start app-steam@autostart.service`（比 kill 干净）。
- 改 `shortcuts.vdf` **必须**先停 Steam，否则 Steam 退出时会覆盖回去。
- `AppName` 改名/改 Exe 时会重新算 appid → prefix 目录名跟着变 → **会变成"重下 100G+"**。
  所以改目标时必须保留 appid（`packaging/steam_shortcut.py repoint` 已保证）。
- 非 Steam 游戏的 `steam://rungameid/<appid>` 不受支持（会 assert），别用它做自动化。

## 8. 排错资料位置（燕云为例）

| 东西 | 路径 |
|---|---|
| 启动器日志 | `<prefix>/drive_c/Program Files/yysls/Win32/deploy/launcher.log` |
| 引擎自己的 assert 文本 | `…/yysls_fast/LocalData/check_hex.txt` |
| 账号/初始化流程 | `…/yysls_fast/LocalData/game_account.log`（内容**按字节 -1 混淆**，解一下就能读） |
| 崩溃转储 | `…/users/steamuser/AppData/Local/UniSDK/CrashDump/<ver>/h72/`（`.dmp` 是标准 MDMP，异常流 type=6） |
| patch 日志 | `…/yysls_fast/LocalData/patch_log/patch_log_*.txt` |

判读：`launcher.log` 里 `enter game` → `detect window` 后**不再出现 `exit game`** = 游戏真的起来了。

## 9. 进程识别必须跳过僵尸

被 SIGKILL/SIGTERM 的进程如果没被父进程 `wait()`，会变成**僵尸**——`/proc/<pid>/comm`
**仍然存在**！只看 comm 会永远认为"它还活着"，状态机永远卡在等待。
修法：读 `/proc/<pid>/stat` 第 3 个字段（`)` 之后第一个 token），是 `Z/X` 就跳过；
同时自己起的子进程要主动 `Popen.poll()` 回收。

## 10. js 设备的读法

- js 设备**不能**靠 `O_NONBLOCK` 读：`os.read` 会永久阻塞，必须 `select([fd], timeout)`。
- 事件固定 8 字节 `<IhBB`（time, value, type, number），type 高位 0x80 = 初始化事件，要跳过。
- Linux xpad 布局：轴 0/1=左摇杆，3/4=右摇杆，6/7=十字键；键 0=A 1=B 2=X 3=Y 6=Back 7=Start。

## 11. Steam Input 会"抢"手柄

Steam Input 用 `EVIOCGRAB` 抓住输入设备后，**其它进程读物理 js/event 设备将收不到事件**
（你机器上会看到 Steam 造出来的虚拟手柄 `/dev/input/js2`、`js3`，名字类似
"Microsoft X-Box 360 pad 0/1"，物理的是 js0/js1）。
所以燕窝的做法是：**同时打开所有 js 设备，谁真的出事件就跟谁**，需要时自动切换。
如果两边都不出事件，就在 Steam 库里给燕窝这条快捷方式把 Steam Input 关掉
（库 → 属性 → 控制器 → 禁用），让物理设备空出来。

## 12. 光标"一卡一卡"的两个真因（2026-10-04 实测修掉）

1. **主循环里对每个设备各 `select` 一次**：4 个 js 设备 × 20ms 超时 = 80ms 一轮 → 12Hz，
   手感必然一顿一顿。修法：`read_many()` 用**一次 select 覆盖所有 fd**，再只读就绪的。
   实测：2 个设备一轮 4.81ms → 可以稳跑 ~200Hz。
2. **每次移动都 spawn 一个 `xdotool` 进程**（实测 1.51ms/次，200Hz 就会不停建进程）。
   修法：直接用 `libX11` + `libXtst` 的 **XTest** 扩展（ctypes 调用）：
   `XTestFakeRelativeMotionEvent` / `XTestFakeButtonEvent` / `XTestFakeKeyEvent`。
   实测 0.003ms/次（快 500 倍），零进程开销。
   注意点：ctypes 里要设 `argtypes/restype`、要先 `XInitThreads()`、跨线程用锁串行化，
   `XOpenDisplay` 是每线程/每连接独立。

## 13. 光标形状：什么都不做（结论）

**保持系统原装光标**，不改形状、不改大小。原因：
- Wine/Qt 会在鼠标进入/离开时反复重设自己的光标，用 `XDefineCursor` 抢过来会被覆盖；
- 做"自创光标覆盖层"要软件渲染一个常驻窗口 + 把真光标设成全透明，容易留下"光标消失"的坑；
- 收益小（用户 2026-10-04 实测：原装光标完全够用），所以不做。
桥只负责**移动**光标（XTest）和**点击**（XTest button events）。

## 14. game mode 下窗口不是你能随便摆的（2026-10-04 实测）

**结论**：game mode 时游戏跑在 gamescope 自己的 X display 上（本机是 `:1`，Steam UI 在 `:0`，
从进程的 `DISPLAY` 环境就能看出来），窗口的**层级/位置完全由 gamescope(steamcompmgr) 掌管**：

| 尝试 | 结果 |
|---|---|
| `XRaiseWindow` / `xdotool windowraise` | ❌ 堆叠顺序纹丝不动 |
| `XSetInputFocus` / `xdotool windowactivate` | ❌ 无效（root 上没有 `_NET_ACTIVE_WINDOW`，EWMH 不完整） |
| `XMoveWindow` / `XResizeWindow` | ❌ 坐标/尺寸不变 |
| `unmap` + `map`（假装新窗口） | ❌ 顺序不变 |
| **`XLowerWindow`** | ✅ **有效** |

所以处理"某个小弹窗挡在前面"的正确姿势是 **`lower` 那个碍事的窗口**（用户实测：燕云的
`MpayAgeTipsForm` 压到底后，`登录` 窗自然到最前）。desktop 模式下 KWin 则全都支持。

引擎（`core/windows.py`）对每条动作**回读验证**并记日志，避免"以为成功其实没生效"。

## 15. 读窗口信息踩的两个坑

1. **`XGetWindowProperty` 参数顺序**：12 个参数里少传 `actual_format` 会整串错位，
   `nitems` 读到的是 format（8）→ **标题被截成前 8 个字符**（"MpayAgeTipsForm" 变 "MpayAgeT"）。
   正确签名：`(dpy, w, prop, off, len, delete, req_type, &actual_type, &actual_format,
   &nitems, &bytes_after, &prop_return)`。
2. **中文标题要读 `_NET_WM_NAME`（UTF8_STRING）**，不要用 `XFetchName`（那是 `WM_NAME`，
   中文会变成 `??`）。Wine 两个都会设。
3. **32 位属性只有 4 字节**：读 `WM_TRANSIENT_FOR` / `_NET_WM_PID` 时别写 `len(raw) >= 8`
   才解析（会永远得到 0），要 `raw[:4].ljust(4, b"\0")`。Wine 这几个窗口靠它才能识别成"弹窗"。
4. `XWindowAttributes` 的 `map_state` 在 x86_64 上偏移 **92**（0=Unmapped 1=Unviewable 2=Viewable），
   用它过滤掉 IME/托盘那种 1x1 辅助窗口。

## 16. 游戏阶段的输入桥：按"窗口"而不是"阶段"开关（2026-10-04 需求）

游戏本体是 `yysls.exe` 一个进程，但它同时有：主窗口（3840x2160）+ `登录`(720x960) +
`MpayAgeTipsForm`(120x152)。**只有主窗口不需要鼠标**，登录/公告/设置这些 UI 窗口手柄点不了。

所以桥的模式做成三层（`[bridge]` 里声明的 `cursor_windows` / `cursor_on_dialogs`）：
游戏阶段里只要"命中标题"或"出现弹窗"（`WM_TRANSIENT_FOR` 非 0）→ 开 `cursor` 模式；
只剩主窗口 → 回到 `off`。门控由窗口守护线程**全程**评估（规则本身只观察前 `watch_seconds` 秒）。

## 17. game mode 里"置前"的唯一正确姿势：EWMH `_NET_ACTIVE_WINDOW`（2026-10-04 定案）

翻 gamescope 3.16.23.6 源码（`src/steamcompmgr.cpp`）得到的结论：

- `handle_client_message()`（:5388）：
  ```c
  else if ( ev->message_type == ctx->atoms.activeWindowAtom )
      XRaiseWindow( ctx->dpy, w->xwayland().id );
  ```
  即 gamescope **会处理** `_NET_ACTIVE_WINDOW`，做法是调用它**自己**的 `XRaiseWindow`。
  WM 自己发起的请求不会被 SubstructureRedirect 再次重定向，于是真的落到 X 服务器上，
  触发 `CirculateNotify` → gamescope 的 `circulate_win()` → `restack_win()`（:5091）
  → **它内部的绘制列表也跟着重排**（`paint_window(pFocus->focusWindow...)` 用的就是这个列表）。
- 反过来，我们**外部**直接发 `XRaiseWindow`/`XLowerWindow`：请求会被重定向成
  `CirculateRequest` → `circulate_request()` → 实际层级不一定变（实测没变）。
  **"lower 之后画面没变"就是这个原因，不是"gamescope 不跟 X 堆叠"。**
- 坑：gamescope 把 `_NET_ACTIVE_WINDOW` 声明进 `_NET_SUPPORTED`、也 intern 了 atom，
  但**从不 XChangeProperty 到 root**（全文件只有 :5388 那一次使用）。
  所以判据只能是**堆叠索引有没有上去**，不能读那个属性（读了永远是 0 → 会误报"没生效"）。
- 实测（:1 上两个同位置 Tk 窗口，A 在下 B 在上）：
  ```
  发给 root, SubstructureRedirect|SubstructureNotify  → A 层级 3→4 ✅
  ```
- 另：`XGetImage(root)` 在 gamescope 上必然 `BadMatch`（画面是 gamescope 合成的，X 端没有内容），
  所以"像素探针"在 game mode 下不可用。**注意 libX11 默认错误处理器会直接 exit(1)**，
  所以 `_X` 里装了 `XSetErrorHandler` 把它降级成 `last_error`，否则一次探测就能干掉 Hub。

## 18. 输入桥和 Steam 覆盖界面会打架（2026-10-04 用户反馈）

- 我们的桥**只读设备、不独占**（故意的：这样游戏自己仍能拿到手柄），
  所以唤出 Steam 覆盖界面/切窗口时，**两边同时收到手柄** → 光标和覆盖界面抢输入。
- 缓解：`[bridge] pause_combo = ["select","third"]`（Select+X）——按一次暂停桥（一个字节都不注入），
  再按恢复；暂停状态会显示在 Hub 底部（`⏸ 已暂停`）。
- 也留了 `pause_windows`（标题正则）用于"某窗口出现就自动暂停"，但 Steam 覆盖界面在 game mode 下
  通常是 gamescope 自己画的、**没有 X 窗口**，所以主要靠上面的快捷键。

## 19. 燕云登录窗在 game mode 下"看不见"的早期调查（2026-10-04）

> 本节“必须桌面登录”的结论已被第 20 节实机验证推翻；保留早期操作记录供排错。

### 现象
game mode 里屏幕中央显示一张放大的**「16+ CADPA 适龄提示」卡片**，盖住了二维码登录窗；
玩家以为登录窗有问题，其实**登录窗内容完全正常**（抓到它的像素：二维码登录框，
当时显示「登录失败 / 二维码已过期，请刷新后重新扫描 / 重新登录」）。

### 三个窗口（都是 yysls.exe 的，都是普通窗口，非 override-redirect）
| 窗口 | 几何 | 内容 |
|---|---|---|
| 燕云十六声 | 3840x2160+0+0 | 主窗口（登录阶段是黑屏） |
| 登录 | 720x960+1560+600 | 二维码登录框（白底，正常） |
| MpayAgeTipsForm | 120x152+0+0 | 年龄提示卡片（橙白） |

### 根因：gamescope 的 override 层会把内容拉伸到 focus 窗的矩形
`src/steamcompmgr.cpp` `paint_window_commit()`：
```c
if (w == scaleW) { sourceWidth = layer->tex->width(); ... }
else { sourceWidth = scaleW->GetGeometry().nWidth;   // ← w=override, scaleW=focus
       sourceHeight = scaleW->GetGeometry().nHeight; }
if (fit) { sourceWidth = max(sourceWidth, clamp(fit->x + fit->w, 0, outW)); ... }
```
`paint_all()` 对 override 的调用是 `paint_window(override, w=focus, ..., fit=override)`
（:2635），所以 **override 窗口的纹理被拉伸成 focus 窗口的尺寸**。
focus = 登录窗（720x960@1560,600）时，120x152 的年龄卡片就被拉成 720x960 盖住登录框。

年龄卡为什么会被选成 override：`win_maybe_a_dropdown()`（固定位置 + 小尺寸 + skipTaskbar
且非 dialog）→ 它被当成"弹出层"。三个窗口都带 `_NET_WM_STATE_SKIP_TASKBAR`，
`_WINE_HWND_EXSTYLE` 都是 0（所以不是 WS_EX_LAYERED 导致的）。

### 实测证据（用 `tools/gs-shot.py` 截图对比）
| 操作 | 结果 |
|---|---|
| `hide` 年龄窗 | 卡片消失，但**整屏黑**（登录窗这一层 gamescope 提交不上来） |
| `hide` 登录窗 | 卡片**原地不动** → 证明卡片内容来自年龄窗 |
| `hide` 年龄窗 + `hide` 主窗 | 仍然全黑 → 登录窗的内容 gamescope 根本不画 |
| `move` / `lower` / `raise` / `focus` | 被 WM 吞掉或对画面无影响 |
| `_NET_WM_WINDOW_OPACITY=0`（年龄窗） | 无变化（gamescope 不走这条排除路径） |
| `activate`（登录窗/主窗） | **有效**（改 X 堆叠 + gamescope 内部 restack），但对"谁被显示"没影响 |
| `remap` 主窗口 | 画面整个黑掉（D3D12 重映射副作用），约 1 分钟后自己恢复 |

### 结论与对策
- gamescope 只画 **focus 窗 + override 窗** 两层，其它窗口根本不画；且 override 会被拉伸
  到 focus 的矩形。燕云这种"主窗 + 登录弹窗 + 小提示窗"的结构在 game mode 下就是显示不出来。
- **对策：到桌面模式（KWin）登录一次**。KWin 下三个窗口都正常显示，登录状态会保存，
  之后回 game mode 直接进游戏，不需要再登录。
- 配方里只保留 `activate`（无害）；不要再用 hide/close/remap 折腾这些窗口。

### 顺手得到的两个通用工具/技巧
1. **`gamescopectl screenshot <path> [type]`** 可以拿到 gamescope 真正合成的画面
   （type: 1=base_plane_only 2=all_real_layers 3=full_composition 4=screen_buffer）。
   这是 game mode 下判断"窗口到底显示了没"的唯一可靠手段 —— `XGetImage(root)` 在
   gamescope 上必然 `BadMatch`（画面是它自己合成的，X 端没有内容）。
   ⚠️ libX11 默认错误处理器遇到 BadMatch 会 `exit(1)`，所以 `core/windows.py` 里装了
   `XSetErrorHandler` 把它降级成 `last_error`，否则一次探测就能把 Hub 干掉。
2. **`gamescopectl help`** 列出所有 gamescope 调试命令（还有 `log_<通道> debug` 可以
   打开调试日志，日志进 journal）。


## 20. SteamOS 内直接显示登录窗（2026-10-04，实机复现）

第 19 节漏掉了 gamescope 的全局显示窗口控制，以及无标题辅助窗。
`pick_primary_focus_and_override()` 的全局调用读取 **root_ctx** 的
`GAMESCOPECTRL_BASELAYER_WINDOW`。本机 root_ctx 是 `:0`，游戏窗在 `:1`。
在 `:1` 改该属性仅改变游戏侧焦点，不会指定最终合成画面的窗口。

实机修复由两步组成：

1. 在 gamescope server ID 0 的 root 设置 `GAMESCOPECTRL_BASELAYER_WINDOW` 为登录窗 XID。
2. 将同进程的 `MpayAgeTipsForm` 类型临时改为 `_NET_WM_WINDOW_TYPE_DIALOG`。
   它有 `WM_TRANSIENT_FOR`；类型纠正后不再满足 `win_maybe_a_dropdown()`，避免年龄纹理盖住二维码。

`tools/gs-shot.py` 抓到真正合成的二维码登录画面。将年龄类型恢复并重映射年龄窗，
再次出现遮挡；重新应用两步修复后恢复二维码。因此只指定显示焦点还不够。
无需隐藏/关闭年龄窗，无需重映射游戏主窗口，无需切桌面。

配方动作 `gamescope_focus` 与 `gamescope_dialog` 由守护线程全程维护。
登录窗消失或会话结束时恢复原显示控制值和窗口类型；若 Steam 已改控制值，保留 Steam 的选择。
用户已从 SteamOS 重新启动并确认登录窗口正常显示（2026-10-04）。扫码完成后的主窗口恢复仍需后续验证。


## 21. 登录输入与 Steam 原生键盘（2026-10-04，接入完成，完整交互待复测）

用户要求：右摇杆光标先能用；A 点击实际输入框才打开键盘；普通按钮不弹键盘；
键盘出现时避开输入框，关闭后恢复光标。此前按 Y 直接弹键盘的实现已撤掉。

发现显示焦点和游戏侧输入焦点是两处控制。只设置 server ID 0 的属性时，
游戏侧 `XGetInputFocus` 可以仍落在年龄窗；在游戏 XWayland root 同步指定登录窗后，
实际点击能切到邮箱登录并聚焦 `EditWnd_2HF8`。现在两处控制独立保存和恢复。

`tools/wine/focused-edit.c` 在同一个 Wine 前缀中读取 `GetGUIThreadInfo`、控件类、
矩形和鼠标位置。只接受可见、启用、非只读的 Edit/RichEdit，且鼠标必须在该控件内，
避免普通按钮点击后残留的文本焦点误开键盘。不读取账号、密码或任何文本内容。
实机曾读到 720×960 登录窗中的编辑框矩形 `(240,348,336,36)`。
DPI 感知调用保证几何为实际像素，而不是本机 300% 下的逻辑坐标。
随仓库保存 19KB Windows 辅助程序，无需用户安装编译器。重建命令见 C 文件头注释。

A 先注入左键，延迟 120ms 查询控件，再向 Steam 发送
`steam://open/keyboard?XPosition=...&YPosition=...&Width=...&Height=...&Mode=...`。
矩形用于原生浮动键盘避让，数字控件使用 Mode=3，其余 Mode=0。
仅 Steam 窗口的 `STEAM_INPUT_FOCUS` 实际接管时暂停注入，不因请求本身提前停光标。
关掉键盘后自动恢复，手动暂停开关不被改写。

验证：57 项自动测试通过；实际编辑控件检测成功。尚未确认重新启动后 A 自动触发、
原生键盘正常绘制、文字回填及输入框避让的整个流程。抓取原生键盘打开时的合成截图
出现黑色区域，不能把请求成功视为键盘可用；已请用户比较 Steam+X 的直接调用结果。
当前 Steam 快捷方式 AllowOverlay=0，但尚无证据证明它导致键盘异常，未擅改此设置。
本节记录的是待实机验收的接入状态，不替代第 20 节已确认的窗口显示修复。


## 22. 后续协议/验证码弹窗被登录窗锁定遮住（2026-10-04）

实机在手机号登录后创建了 680×468 的无标题窗口（`WM_TRANSIENT_FOR` 指向登录窗），
其内容是协议确认；用户描述为验证码阶段弹窗显示异常。旧 `_X.list()` 直接跳过无标题窗，
且 `sync_gamescope()` 始终指定登录窗，导致真实模态窗口存在但不可见。
临时把全局和游戏侧显示控制值都指定为该窗口，合成截图已出现协议确认内容。

修复：保留无标题窗口元数据，按同进程 transient 父子链选择最深的可交互弹窗；
窗口 unmapped/销毁后回到父窗。年龄提示沿用辅助窗规则；鼠标穿透/无激活阴影不被选中；
协议说明小浮层通过配方 `gamescope_ignore` 排除。不能靠 Wine 的 WS_POPUP 位判断，
实机该 style 会改变，误用会排除登录窗本身。

左摇杆：默认鼠标仍仅接右摇杆轴 3/4；另撤掉燕窝的左摇杆菜单导航，菜单只用十字键。
用户确认现象是左摇杆会移动鼠标，后续仍复现。用户要求暂不处理，停止该项排查。
采样记录到轴 3/4 和物理/Steam 虚拟设备的同步事件，但无法据此确定物理摇杆操作，
也没有证明哪条路径导致左摇杆移动。
不能把默认映射测试通过当作实际左摇杆问题已解决。

退出问题：CLI 的 Hub 路径之前只 `.run()`，事件循环返回后从未调用 `.shutdown()`，
会话线程又是 daemon，因而关闭 UI 后可能留下游戏、窗口控制和 Steam 启动包装进程。
现在在 finally 调用 shutdown，停止输入桥并等待会话线程执行正常收尾。
此前 Steam 界面仍卡旧登录画面，重启 steamwebhelper 后截图恢复 Steam 游戏主页。

当前版本验证：61 项自动测试通过。原生键盘完整显示/输入/避让，以及下一次完整登录流程仍待实机确认。


## 23. 原生键盘弹出瞬间年龄窗抢走输入焦点（2026-10-04，已修）

用户反馈：键盘能弹出来了，但**点出键盘的一瞬间**年龄提示卡（`MpayAgeTipsForm`）出现，
然后鼠标光标消失、键盘看着在但**什么都输入不进去**。

实机证据（`DISPLAY=:1`，游戏自己的 XWayland）：
- 正常时 `xdotool getwindowfocus` = `登录`；
- 键盘弹出后 = `MpayAgeTipsForm` → 键盘按键全进到那个空窗口；
- **把年龄窗 unmap 掉，焦点立刻自己回到 `登录`**，且合成截图里登录页完整显示、不再黑屏
  （第 19 节说的"隐藏年龄窗会全黑"只在**没有**指定 baselayer 窗口时成立；
  现在 `gamescope_focus` 已把登录窗钉成 baselayer，隐藏年龄卡是安全的）。

修法（通用，写在窗口规则线程里，不针对燕云硬编码）：
- `WindowRules._guard_focus()`：只要 `gamescope_focus` 指定的目标窗（登录窗）在，就把被
  `gamescope_dialog` 标记的辅助窗**主动 unmap 收起来**（游戏再 map 出来就再收），
  并在游戏显示（`:1`）的 `XGetInputFocus` 不在目标窗时把焦点交还目标窗。
  这些提示窗只需显示、不需要焦点，收起来就能从根上避免原生键盘弹出时被它抢走焦点。
- 被收起的辅助窗记在 `_focus_hidden`，会话结束（`_restore_hidden`）时统一 `map` 回来。
- 规则循环周期从 2s 收紧到 0.5s，抢焦点能很快被纠正。

自动测试 63 项通过（新增焦点守卫 2 项）。当前正在跑的会话可用
`tools/live-focus-guard.py` 热打补丁，无需重启燕窝。


## 24. 文本框命中区和 Win32 子控件焦点（2026-10-04，继续修正）

用户再次反馈：键盘能弹出，但年龄卡出现后无法输入。第 23 节的“已修”只覆盖了
X11 顶层窗口，不能据此认定具体文本输入已经修好。

邮箱/手机号的自绘白色输入行高于内部 EditWnd。实机有输入控件矩形
`(76,348)-(576,384)`，鼠标落在 `(143,400)`；控件已有焦点，但旧 PtInRect 判定拒绝了点击。
现在仅对 MPAY_LOGIN 内的 EditWnd 按文本高度补足行内边距，普通 Edit 保持原检测范围。

在确认点击了可编辑行后，检测程序对同 Windows 进程的 MPAY_AGE_TIPS 设置
WS_EX_NOACTIVATE 并调用 SW_HIDE，避免 X11 unmap 后 Win32 内部仍认为年龄窗可见、激活。
不会收起真实的协议/验证模态窗。年龄窗和这些原生属性随游戏进程结束销毁。
同时通过 AttachThreadInput + SetFocus 保留具体 Edit 子控件。启动一个无窗口辅助进程，
在键盘弹出最初两秒内检查同 GUI 线程焦点；被改成非编辑窗口时恢复原 Edit，
若用户转到另一个编辑框、父窗禁用或控件消失就停止。辅助进程不保持账号/密码内容。

已将重新编译的辅助程序替换到当前会话使用的路径，无需重启即可使用。
64 项自动测试通过；已请求用户确认“键盘打开后字符实际进入邮箱/手机号”的结果，
尚不能把焦点准备/测试通过等同于完整输入已验证。
