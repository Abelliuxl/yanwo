# 路线图

## P0 · 设计定稿 ✅
- [x] 架构/决策/状态机/命名（见 DESIGN.md）
- [x] 用户在几个关键点上拍板（单条目、不要 root、文字菜单 Demo、桌面+游戏两个入口）

## P1 · 骨架（当前）🟡
- [x] 目录结构、配方协议、`game.toml`（燕云）
- [x] 配方加载 + 变量展开
- [x] 启动链执行（`kind="wine"`，含 DLL 覆盖/软件渲染等踩坑配置）
- [x] 进程识别（进程名 + WINEPREFIX）+ 状态机（LAUNCHER/GAME/收尾）
- [x] 优雅收尾（先关窗、再清理）
- [x] Demo UI：文字上下菜单（tkinter）
- [x] `yanwo list / run / selftest`，`bin/yanwo` 入口，`.desktop`，Steam 快捷方式工具
- [ ] 桌面模式实机跑一遍（人肉确认菜单能开、能进游戏、退出能回菜单）
- [ ] Steam 条目切换到燕窝（保留旧条目一段时间做后备）

## P2 · 输入桥（下一步）
- [ ] `DEV-NOTES` 里的"设备校准"：按一次记录轴/键编号 → `input/profiles/*.toml`
- [ ] evdev 读取（`select` + 非阻塞；注意 js 设备 **不** 吃 `O_NONBLOCK` 的读，必须 select）
- [ ] 输出后端 `xdotool`：摇杆→`mousemove_relative`，A→`click 1`，Start→`key Return`
- [ ] 门控：只在 `bridge.active_when` 阶段 + 目标窗口前台时注入
- [ ] 游戏模式：自动定位 gamescope 的 DISPLAY
- [ ] Hub 菜单本身也吃手柄（Hub 自己直读 evdev，不走 xdotool）
- [ ] 决定与 Steam Input 的关系（文档里要求二选一）

## P3 · 安装/分发
- [ ] `[install]` 真正执行：下载官方安装器 → 在自管 prefix 里装 → 自动打补丁（DPI、DLL 覆盖、软件渲染）
- [ ] prefix 自管（不再借用 `compatdata/2885173776`），放到 `state/prefix/` 或用户指定目录
- [ ] 显存安全阀从独立服务迁进 Hub（`[safety]` 唯一来源）
- [ ] 配方热更新/版本字段（`min_hub_version`）
- [ ] 新用户文档：装燕窝 → 装游戏一步到位

## P4 · 打磨
- [ ] 大图 UI（Qt/QML）：海报墙、手柄焦点、动画；`ui/` 换实现即可
- [ ] 多游戏管理、封面/图标自动获取、最近游玩
- [ ] 更新检查（游戏/燕窝自身）
- [ ] 日志面板 / 故障自检（把今天的坑做成"一键诊断"）

## 待定问题
1. 输入桥默认后端：xdotool（已定）→ 是否再提供 uinput 选项（需要用户自愿配 udev）？
2. 游戏模式里 Steam Input 是否禁用？（禁用→只用燕窝的桥；保留→双重输入）
3. 是否允许配方带 `[[steps]]` 的"等待条件"（例如"等更新器窗口消失再起启动器"）？P1 是顺序起不等。
4. prefix 自管后，老 prefix（`compatdata/2885173776`，122G）怎么迁移/复用？—— 大概率是"沿用现有路径"最简单。
5. 反作弊/内核级检测的游戏，配方里要不要显式标 `unsupported = true`？
