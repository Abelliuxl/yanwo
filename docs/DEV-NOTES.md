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

## 17. gamescope 的视觉层级 ≠ X 堆叠顺序（2026-10-04 二次实测）

- 我们用 `XLowerWindow` 把 `MpayAgeTipsForm` 从堆叠索引 9 降到 0（`XQueryTree` 确认），
  但**玩家看到的画面没变**，那个小窗仍在前面。
- 结论：game mode 下想靠"调整层级"解决"某个窗口挡着"是行不通的。可行的是
  **让那个窗口消失**（`close` = WM_DELETE_WINDOW，应用自己关；或 `hide` = unmap）。
- 所以窗口规则里 `lower` 只对 desktop(KWin) 有意义；game mode 请用 `close`/`hide`。

## 18. 输入桥和 Steam 覆盖界面会打架（2026-10-04 用户反馈）

- 我们的桥**只读设备、不独占**（故意的：这样游戏自己仍能拿到手柄），
  所以唤出 Steam 覆盖界面/切窗口时，**两边同时收到手柄** → 光标和覆盖界面抢输入。
- 缓解：`[bridge] pause_combo = ["select","third"]`（Select+X）——按一次暂停桥（一个字节都不注入），
  再按恢复；暂停状态会显示在 Hub 底部（`⏸ 已暂停`）。
- 也留了 `pause_windows`（标题正则）用于"某窗口出现就自动暂停"，但 Steam 覆盖界面在 game mode 下
  通常是 gamescope 自己画的、**没有 X 窗口**，所以主要靠上面的快捷键。
