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

[bridge]                                # 输入桥（P2）
active_when = ["hub", "launcher"]       # 哪些阶段需要桥
profile = "cursor_click"
backend = "xdotool"
enabled = false
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

## 约定与注意事项

- 字符串里的 `~` 会自动展开；`${var}` 会展开（支持变量互相引用，最多 5 轮）。
- ⚠️ **TOML 坑**：`[steps.env]` 会把“当前表”切到 `env`，所以它必须放在那个 `[[steps]]`
  所有普通键**之后**，否则后面的 `dll_overrides` 等会被当戍 env 的键（静默不生效）。
- **`detect` 一定要填**：状态机靠它判断“现在轮到谁”，不填就只能看整个进程组。
- `[steps.env]` 在 Wine 里对 Windows 进程可见（Wine 会把 Unix 环境带进去），
  所以 `QT_OPENGL` / `QT_QUICK_BACKEND` 这类 Qt 变量放在这里就生效。
- 一个配方可以有多步 `[[steps]]`（例如“更新器 → 启动器”），P1 是顺序起、不等退出。
- 新增字段时请同步更新本文件与 `src/yanwo/recipe.py`。
