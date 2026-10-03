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
