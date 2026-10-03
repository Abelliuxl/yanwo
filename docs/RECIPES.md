# 配方协议（recipes/\<id\>/game.toml）

一个游戏 = 一个目录 + 一个 `game.toml`。**Hub 代码里不允许出现具体游戏名**，
任何游戏差异都靠这份数据表达（见 DESIGN.md D3）。

## 完整示例

```toml
id = "yysls-guofu"                      # 唯一 id，缺省用目录名
name = "燕云十六声（国服）"                # 菜单显示名
subtitle = "网易国服 · 极速版 · GE-Proton"  # 菜单第二行
launcher_kind = "wine"                  # wine | native | steam | url（P1 只跑 wine）

[vars]                                  # 你自定义的变量，可在本文件任何字符串里用 ${name}
compatdata = "~/.local/share/Steam/steamapps/compatdata/2885173776"
prefix = "${compatdata}/pfx"            # 变量之间也可以互相引用

[install]                               # 首次安装（P1 只记录，不执行）
kind = "wine_installer"
installer_url = "https://…/setup.exe"
installer_file = "~/Games/yysls/setup.exe"
expect_user_gui = true                  # 安装器需要用户点几下

[[steps]]                               # 启动链：按顺序各起一个进程
kind = "wine"                           # wine | shell | native | steam
prefix = "${prefix}"                    # → WINEPREFIX
workdir = "${prefix}/drive_c/…/deploy"  # 工作目录（可省）
exe = "launcher.exe"                    # 可执行文件（wine/native 必需）
wine = "${proton_wine}"                 # 用哪个 wine（默认 GE-Proton 的）
proton_dir = "${proton_dir}"            # 自动拼 LD_LIBRARY_PATH
args = ["--foo"]                        # 附加参数（可省）
dll_overrides = ["d3d12=n,b"]           # → WINEDLLOVERRIDES（; 连接）
dll_paths = ["${proton_lib}/wine/vkd3d-proton"]  # → WINEDLLPATH（: 连接）

[steps.env]                             # 附加环境变量（Windows 进程也能看到）
QT_OPENGL = "software"

[windows]                               # 窗口规则（每个游戏都不一样，全在这里声明）
enabled = true
watch_seconds = 180                     # 进游戏后观察多久（窗口是陆续冒出来的）
[[windows.rules]]
name = "年龄提示压到底层"                  # 只用于日志
match = "MpayAgeTipsForm"               # 标题正则（读的是 _NET_WM_NAME，UTF-8，中文可用）
actions = ["lower"]                     # 见下面"动作支持情况"
priority = 20                           # 数字大的先执行
repeat_seconds = 10                     # 可选：窗口集合没变也定期重申
stop = false                            # 可选：true = 这条生效后不再往下匹配
enabled = true                          # 可选：false = 临时关掉这条

[detect]                                # 状态机用它识别人物（进程名，忽略大小写）
launcher_procs = ["launcher.exe"]       # 官方启动器
game_procs = ["yysls.exe"]              # 游戏本体

[policy]
on_game_exit = "wait_launcher"          # wait_launcher | close_launcher
on_launcher_exit = "return_to_hub"
kill_orphan_wine = true                 # 收尾时清残留 wine 进程

[safety]                                # 显存安全阀（独立 vram-guard 在跑时让位）
max_group_vram_gb = 8
max_growth_gb = 4
window_seconds = 60
max_global_vram_pct = 92

[bridge]                                # 输入桥（P2 已实现）
enabled = true                          # false = 这个游戏全程不接管手柄
active_when = ["hub", "launcher"]       # Hub / 官方启动器阶段一直开
profile = "cursor_click"                # 语义档名（实际映射在 input/profiles/*.toml）
backend = "auto"                        # 自动：XTest → xdotool（零 root）

# 游戏本体阶段默认"关"（尊重游戏自己的手柄支持），但只要出现"UI 窗口"就自动打开光标：
cursor_windows = ["^(登录|Login)", "^Mpay", "公告|提示", "^(设置|Options)"]
cursor_on_dialogs = true                # 通用启发式：任何弹窗（WM_TRANSIENT_FOR 非 0）也算
pause_combo = ["select", "third"]       # 手柄组合键：按一次暂停桥、再按恢复（给 Steam 覆盖界面让路）
pause_windows = []                      # 出现这些标题的窗口时自动暂停桥（正则）
```

## 内置变量（不用定义就能用）

| 变量 | 值 |
|---|---|
| `${home}` | `~` |
| `${repo}` | 仓库根目录 |
| `${recipe_id}` / `${recipe_dir}` | 本配方的 id / 目录 |
| `${steam}` | `~/.local/share/Steam` |
| `${proton_dir}` | GE-Proton 目录（默认 `…/compatibilitytools.d/GE-Proton10-32`） |
| `${proton_wine}` | `…/files/bin/wine` |
| `${proton_lib}` | `…/files/lib` |

## 输入桥的三个模式

| 阶段 | 模式 | 手柄行为 |
|---|---|---|
| Hub 菜单 | `hub` | 十字键/左摇杆选择、A 启动、B 退出 |
| 官方启动器 | `launcher` | 左摇杆=光标、A 左键、B 右键、Start 回车、X Esc |
| **游戏本体（有 UI 窗口）** | `cursor` | 同上（登录窗、公告、设置面板手柄点不了） |
| 游戏本体（只剩主窗口） | `off` | 完全不碰，交给游戏自己的手柄支持 |

`cursor_windows` 命中或出现任意弹窗 → 从 `off` 切到 `cursor`；弹窗关掉只剩主窗口 → 切回 `off`。

## 窗口规则的动作支持情况（2026-10-04 实测）

引擎执行每条动作后会**回读验证**，把"没生效"写进日志，所以不同游戏可以自己试。

| 动作 | 写法 | game mode（gamescope） | desktop mode（KWin） |
|---|---|---|---|
| `activate` | **game mode 唯一有效的"置前"**（EWMH 请求，让 WM 自己去 raise）|
| `lower` | `"lower"` | ✅ **有效**（把碍事的窗口压到最底，别的主窗口自然到前面） | ✅ |
| `close` | `"close"` | ✅ 发 WM_DELETE_WINDOW（让应用自己关） | ✅ |
| `focus` | `"focus"` | ❌ 被忽略 | ✅ |
| `raise` | `"raise"` | ❌ 被忽略 | ✅ |
| `move` | `"move:0,0"` | ❌ 被忽略 | ✅ |
| `resize` | `"resize:1280,720"` | ❌ 被忽略 | ✅ |
| `remap` | `"remap"` | ❌ 被忽略 | 视 WM |
| `hide` | `"hide"` | 未实测 | ✅ |
| `click` | `"click"` | 走 XTest 点击窗口中心（是否有效取决于窗口是否拿到输入） | ✅ |

> **结论（2026-10-04，读 gamescope 源码 + 实测确认）**：game mode 下想让某个窗口到最前，
> 只能用 **`activate`**（发 EWMH `_NET_ACTIVE_WINDOW`）。gamescope 收到后会调用**它自己**的
> `XRaiseWindow` → `restack_win()` 改它内部的绘制列表，所以画面层级真的会变（实测堆叠 3→4）。
> 而我们**自己**发 `raise`/`lower` 属于外部请求，WM 直接吞掉 —— 这就是"lower 看着没反应"的原因。
> gamescope 还有个坑：它**从不**把 `_NET_ACTIVE_WINDOW` 写到 root 上，所以别拿这个属性当判据，
> 要看**堆叠索引**（`verdict_activate()` 已经这么做了）。

## 约定与注意事项

- 字符串里的 `~` 会自动展开；`${var}` 会展开（支持变量互相引用，最多 5 轮）。
- ⚠️ **TOML 坑**：`[steps.env]` 会把“当前表”切到 `env`，所以它必须放在那个 `[[steps]]`
  所有普通键**之后**，否则后面的 `dll_overrides` 等会被当戍 env 的键（静默不生效）。
- **`detect` 一定要填**：状态机靠它判断“现在轮到谁”，不填就只能看整个进程组。
- `[steps.env]` 在 Wine 里对 Windows 进程可见（Wine 会把 Unix 环境带进去），
  所以 `QT_OPENGL` / `QT_QUICK_BACKEND` 这类 Qt 变量放在这里就生效。
- 一个配方可以有多步 `[[steps]]`（例如“更新器 → 启动器”），P1 是顺序起、不等退出。
- 新增字段时请同步更新本文件与 `src/yanwo/recipe.py`。
