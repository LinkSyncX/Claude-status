# Claude Status · Claude 账号管理与用量统计

[![CI](https://github.com/LinkSyncX/Claude-status/actions/workflows/ci.yml/badge.svg)](https://github.com/LinkSyncX/Claude-status/actions/workflows/ci.yml)
[![最新版本](https://img.shields.io/github/v/release/LinkSyncX/Claude-status?include_prereleases&label=%E6%9C%80%E6%96%B0%E7%89%88%E6%9C%AC)](https://github.com/LinkSyncX/Claude-status/releases)

基于本仓库的 `md3`（PySide6 Material Design 3 组件库）构建的桌面工具：
管理多个 Claude 账号，一键切换 Claude Code 与 Claude Desktop 的登录，查看各
账号的 5 小时与每周额度，并从本机 Claude Code 日志统计 token 用量、估算费用、
绘制活跃热力图。提供 Windows、macOS 与 Linux 版本。

![账号管理](docs/screenshots/accounts.png)

| 数据统计 | 活跃热力图 |
| --- | --- |
| ![数据统计](docs/screenshots/dashboard.png) | ![活跃热力图](docs/screenshots/heatmap.png) |

<sub>截图使用演示数据（`--demo`）。</sub>

## 功能

- **账号管理**：新建 / 编辑 / 删除（可撤销）、收藏、状态标记（正常 / 受限 /
  已过期 / 已停用）；卡片与列表两种视图，支持搜索、状态筛选与排序；账号卡片
  显示 5 小时与本周额度、两个客户端的登录状态（`Code 使用中` / `Desktop 使用中`）
  与本月用量；右侧详情面板显示额度（含按模型的周额度与 Desktop 采样走势）、
  资料与近 30 天用量；月度预算进度与超支提醒；复制密钥或终端环境变量；JSON
  导入导出（可选是否包含密钥）。
- **在本工具中登录**：“新建账号 → 登录 Claude 账号”在浏览器中完成登录并自动
  保存，无需再到终端运行 `claude /login`；登录过期时可一键重新登录。
- **一键切换**：账号卡片上的“切换”按钮把 Claude Code 与（可选）Claude Desktop
  一起切换到该账号；也可以在菜单或“客户端”页只切换其中一个。
- **客户端**：
  - Claude Code：当前生效的是订阅登录还是中转 / API 配置、令牌有效期；保存
    当前登录、把当前中转配置保存为账号、可切换账号列表。
  - Claude Desktop：安装方式与版本、运行状态、当前登录的账号；关联到账号
    （不需要退出 Desktop）、保存会话、登录新账号、退出 / 启动 Desktop；已保存
    的会话、额度走势与 MCP 服务器列表。
  - 用量归属：Claude Code、Claude Desktop 与中转三种来源各自计入哪个账号，
    有未归属用量时给出一键修复。
- **导出**：本工具的 JSON（可选是否包含密钥），以及 sub2api、CPA（CLIProxyAPI）
  的导入格式。
- **数据统计**：7 天 / 30 天 / 90 天 / 1 年 / 全部，按 Token、费用或请求数
  查看；关键指标与上一个等长区间对比；按模型系列堆叠的用量趋势、模型分布、
  用量分布（按账号或按请求来源）、项目排行、Token 构成、缓存命中率与模型
  明细表。
- **热力图**：GitHub 风格的活跃日历（近一年或按年份），连续活跃天数、单日
  峰值；点击任意一天查看当日明细与 24 小时分布；一周时段分布（星期 × 小时）；
  账号 × 月份矩阵。
- **设置**：数据源与日志目录；切换与额度（切换时是否包含 Desktop、切换后是否
  重启 Desktop、是否联网查询额度、代理）；界面风格（Material 动态配色 / 极简白）、
  深色模式与主题色；模型单价表与自定义单价；数据目录管理。

## 安装与运行

### 下载程序

各平台的程序由 GitHub Actions 自动构建，运行时不需要安装 Python。从
[Releases](https://github.com/LinkSyncX/Claude-status/releases) 下载最新版本：

| 系统 | 下载 | 说明 |
| --- | --- | --- |
| Windows 10 / 11（x64） | [ClaudeStatus-windows-x64.exe][win-x64] | 单个 exe（约 35 MB），双击运行，没有控制台窗口 |
| Windows 11（ARM64） | [ClaudeStatus-windows-arm64.exe][win-arm64] | 骁龙等 ARM 处理器的设备 |
| macOS 13 及以上（Apple 芯片） | [ClaudeStatus-macos-arm64.zip][mac-arm64] | 解压得到 `Claude Status.app` |
| macOS 13 及以上（Intel） | [ClaudeStatus-macos-x64.zip][mac-x64] | 同上 |
| Linux（x64） | [ClaudeStatus-linux-x64.tar.gz][linux-x64] | 解压后运行 `./claude-status`；需要 glibc 2.35+（Ubuntu 22.04、Debian 12 及以上） |
| Linux（ARM64） | [ClaudeStatus-linux-arm64.tar.gz][linux-arm64] | 同上；需要 glibc 2.39+（Ubuntu 24.04、Debian 13 及以上） |

[win-x64]: https://github.com/LinkSyncX/Claude-status/releases/latest/download/ClaudeStatus-windows-x64.exe
[win-arm64]: https://github.com/LinkSyncX/Claude-status/releases/latest/download/ClaudeStatus-windows-arm64.exe
[mac-arm64]: https://github.com/LinkSyncX/Claude-status/releases/latest/download/ClaudeStatus-macos-arm64.zip
[mac-x64]: https://github.com/LinkSyncX/Claude-status/releases/latest/download/ClaudeStatus-macos-x64.zip
[linux-x64]: https://github.com/LinkSyncX/Claude-status/releases/latest/download/ClaudeStatus-linux-x64.tar.gz
[linux-arm64]: https://github.com/LinkSyncX/Claude-status/releases/latest/download/ClaudeStatus-linux-arm64.tar.gz

每个版本都附带 `SHA256SUMS.txt`，可用来校验下载的文件。想试用还没有发布的最新
代码，可以在 [Actions](https://github.com/LinkSyncX/Claude-status/actions/workflows/ci.yml?query=branch%3Amain+is%3Asuccess)
中打开最近一次成功的运行，在页面底部下载（需要登录 GitHub）。

几点说明：

- 程序没有代码签名。从网上下载后首次运行时，Windows 可能提示“Windows 已保护
  你的电脑”，点“更多信息 → 仍要运行”；macOS 会拦截打开，可在“系统设置 →
  隐私与安全性”中点“仍要打开”。
- Linux 版需要图形桌面环境。Qt 依赖 `libxcb-cursor0` 等系统库，启动报 xcb
  相关错误时安装即可（Ubuntu / Debian：`sudo apt install libxcb-cursor0`）。
- Windows 以外的系统没有 DPAPI，保存的登录以带标记的明文存放在数据目录中
  （设置页会提示）。macOS 上 Claude Code 的订阅凭据保存在钥匙串中，暂不支持
  切换（见[数据存储与安全](#数据存储与安全)）。

### 从源码运行

推荐使用 Python 3.14（发布版与 CI 使用的版本）：

```bash
pip install -r requirements.txt
python main.py
```

### 命令行参数

打包后的程序与 `python main.py` 的参数相同（`--help` 查看全部），数据目录也
相同，两种运行方式可以混用。常用参数：

| 参数 | 说明 |
| --- | --- |
| `--demo` | 本次启动使用演示数据（首次启动时还会添加示例账号）；演示模式下不会切换真实的客户端 |
| `--offline` | 不联网查询额度 |
| `--dark` | 以深色主题启动（并记住该选择） |
| `--data-dir DIR` | 使用指定的配置目录（便于试用而不影响正式数据） |
| `--page clients` | 启动后直接打开某个页面（accounts / clients / dashboard / heatmap / settings） |
| `--screenshot DIR` | 不显示窗口，把每个页面渲染为 PNG 后退出（总是离线） |

## 添加账号并切换

顶部应用栏的 ? 按钮随时可以查看这份说明。

**Claude Code（订阅账号）**

1. 账号页“新建账号 → 登录 Claude 账号…”：浏览器会打开 Claude 的登录页，登录
   并授权后自动回到本工具，登录保存到对应账号（没有时新建）。每个账号登录一次
   即可，账号 A、B 分别登录。
2. 点击账号卡片上的“切换”即可在 A、B 之间切换；还没有登录的账号点“切换”时会
   先提示登录。切换前会自动备份当前配置，提示条中可以撤销；正在使用的中转配置
   也会先保存为账号，随时可以切回。切换后新启动的 Claude Code 使用新账号，已在
   运行的会话建议重新启动。
3. 登录过期或失效时，在账号菜单或“客户端”页的账号行点“重新登录”。

也可以像以前一样在终端运行 `claude /login`，再到“客户端”页点击“保存当前登录”。

**在本工具中登录是怎么完成的**：与 Claude Code 的 `/login` 完全相同的 OAuth
流程（授权地址、权限范围、PKCE 与令牌接口均取自官方客户端 2.1.280）。本工具在
`127.0.0.1` 的随机端口临时监听回调，浏览器授权后带着一次性授权码回到本机，本
工具换取令牌并读取账号资料（邮箱、组织、套餐）。登录在浏览器中完成，本工具不
接触账号密码。浏览器无法回到本机时（例如在另一台设备上登录），点“改用授权码”，
把官方页面上显示的授权码粘贴回来即可。每次登录都是一份独立的授权，与 Claude
Code 当前的登录互不影响。

中转 / API 账号在账号编辑对话框中填写 Base URL、密钥与“额外环境变量”（每行
一个 `KEY=VALUE`，例如 `ANTHROPIC_DEFAULT_SONNET_MODEL=…` 模型映射），切换
时写入 `~/.claude/settings.json` 的 `env`（只替换 `ANTHROPIC_*` 与
`CLAUDE_CODE_SUBAGENT_MODEL`，其余设置保持不变）；切回订阅账号时移除这些变量。
如果 `settings.json` 里已经有中转配置，可在“客户端”页一键保存为账号。

**Claude Desktop**

1. 在 Desktop 中登录账号 A，然后在“客户端”页（或账号页顶部的提示条）点击
   “关联到账号…”并选择账号。**关联不需要退出 Desktop**，关联后账号卡片立即
   显示它的 5 小时 / 每周额度，Code 标签页的用量也会计入它。
2. 要一键切换回这个账号，再点击“保存会话…”（需要退出 Desktop，完成后自动
   重新启动）。
3. 点击“登录新账号…”：当前会话先被保存，然后清空登录并启动 Desktop，登录
   账号 B 后同样关联、保存。
4. 之后一键切换即可。切换需要退出 Desktop：会先征得确认并请求其正常退出，
   若它最小化到托盘而没有退出，会再询问是否强制结束；完成后按设置重新启动。

Desktop 的登录会话包括 Chromium 存储（Cookie、Local Storage、IndexedDB 等）
与 `config.json` 中的账号相关键；主题等普通设置、MCP 配置、Desktop 内置的
Claude Code 会话与额度采样属于全局数据，不随账号切换。恢复时任何一步失败都会
回滚到原状态。无法归属到账号的会话会另存备份，不会丢失。

## 导出到 sub2api / CPA

账号页右上角的 ⋮ 菜单 → “导出到 sub2api…” 或 “导出到 CPA（CLIProxyAPI）…”，
勾选要导出的账号：

| 格式 | 生成内容 | 使用方式 |
| --- | --- | --- |
| sub2api | 一个 `sub2api-data` JSON：订阅账号为 `anthropic` / `oauth`（凭据含 `access_token`、`refresh_token`、`expires_at`），API 与中转账号为 `apikey`（`api_key`、`base_url`） | 在 sub2api 管理后台的账号管理中导入 |
| CPA | 每个订阅账号一个 `claude-<哈希>-<邮箱>.json`，与 CLIProxyAPI 自己登录生成的文件同名同格式；API 与中转账号生成 `claude-api-key.yaml` 片段 | JSON 放进认证目录（默认 `~/.cli-proxy-api`），片段合并到 `config.yaml` |

- 两种工具使用与 Claude Code 相同的 OAuth 客户端，因此导出的是**Claude Code
  的登录**（保存过的，或 Claude Code 当前的登录）。Claude Desktop 的登录由
  Desktop 加密且属于另一个 OAuth 客户端，不能导出：在账号菜单中选择“登录…”，
  在本工具中登录该账号后即可导出。
- 刷新令牌会轮换，同一份登录只能由一方使用。导出 Claude Code 正在使用的登录
  后，建议在本工具中重新登录该账号，让本机与代理各用一份登录。
- 导出的文件包含明文令牌与密钥，请妥善保管，导入后删除。

## 额度

每个订阅账号显示 5 小时窗口与本周窗口的使用率和重置时间（详情面板中还有按
模型的周额度），来源按新旧取最新：

- **联网查询**（默认开启，每 10 分钟一次，也可在账号页手动刷新）：用保存的
  登录令牌请求 `api.anthropic.com/api/oauth/usage`。**Claude Code 正在使用的
  登录只读取、从不刷新令牌**，因为刷新会让令牌轮换，导致正在运行的 Claude Code
  掉线；其他账号的令牌过期或被拒绝时才刷新，并写回加密保存的登录。
- **Claude Desktop 采样**：Desktop 大约每 15 分钟记录一次所登录组织的使用率
  （`plan-usage-history.json`），详情面板与“客户端”页据此绘制走势。
- **Claude Code 缓存**：`~/.claude.json` 中 Claude Code 自己缓存的使用率。

## 数据来源

- **本机 Claude Code 日志**：读取 `~/.claude/projects/**/*.jsonl`（设置了
  `CLAUDE_CONFIG_DIR` 时从该目录读取）中助手消息的 `usage` 字段。同一次 API
  响应会按内容块拆成多行、续接会话时还会复制历史，因此按 `message.id` 全局
  去重，否则用量会被重复计算数倍。只读取用量相关字段，不读取对话内容。扫描在
  后台线程进行并按文件缓存，每分钟增量刷新一次。
- **按来源归属**：日志不记录账号，但记录了请求来自哪个客户端（`entrypoint`：
  `cli` / `claude-desktop` / `claude-desktop-3p`），官方服务的响应还带有
  `req_` 开头的请求 ID。据此把用量分为三种来源：Claude Code（官方订阅或 API
  Key）、Claude Desktop（Code 标签页）与中转 / 第三方。本工具运行时持续记录
  各来源正在使用的身份（订阅账号、Desktop 登录的账号与组织、中转配置的不可逆
  指纹），Desktop 的额度采样还能补上过去约 12 小时；每条用量按发生时刻的身份
  计入对应账号，因此切换账号后历史用量不会“搬家”。身份还没有对应账号时显示为
  “未归属”，关联 Desktop 账号或把中转配置保存为账号后自动归属。“客户端”页的
  “用量归属”与统计页“用量分布 → 按来源”可以查看各来源的用量。
- 从未观察到的来源（例如很早以前、本工具还没运行过的时期）计入“用量默认归属”
  账号，可在账号菜单或编辑对话框中设置。
- **Claude Desktop 里的聊天不写入本机日志**，因此只能看到它的额度（来自 Desktop
  的额度采样），无法统计聊天的 token 用量。
- **演示数据**：根据账号列表按套餐强度、工作日与时段节律模拟生成，用于预览
  图表效果；同一账号每次生成的数据一致。

## 费用估算

单价取自 Anthropic 一方 API 价格（美元 / 百万 token，2026-06 版），见
`claude_status/pricing.py`。缓存写入按输入单价的 1.25 倍（5 分钟）与 2 倍
（1 小时）计算，缓存读取单价按模型单列。订阅套餐（Pro / Max 等）并不按
token 计费，金额只是“按 API 计价的参考值”。第三方中转或非 Claude 模型没有
内置单价，会显示为“未计价”，可在 **设置 → 模型单价** 中添加自定义单价。

## 数据存储与安全

数据目录为 `~/.claude-status`（可用环境变量 `CLAUDE_STATUS_HOME` 覆盖；0.1
版本的 `%APPDATA%\ClaudeStatus` 会自动迁移过来）。不放在 `%APPDATA%` 下，是
因为从 Microsoft Store 版 Claude Desktop 内部启动的进程（例如其内置 Claude Code
执行的命令）写入 `%APPDATA%` 时会被重定向到 Desktop 的包目录，数据会分裂成两份。

| 位置 | 内容 |
| --- | --- |
| `config.json` | 账号与设置；写入时原子替换并保留上一版 `.bak`，损坏时改名隔离 |
| `vault/<账号 ID>/` | 保存的 Claude Code 登录（`code.bin`）与 Desktop 会话快照（`desktop/`） |
| `backups/` | 每次切换 Claude Code 前的配置备份（保留最近 20 份） |

Windows 上，API Key、名称像密钥的环境变量（含 TOKEN / KEY / SECRET / HEADER）、
保存的登录与配置备份都用 **DPAPI** 加密，只有当前 Windows 用户能解密；配置
复制到其他电脑后密钥无法解密，会被清空并提示重新填写。导出账号时默认不包含
密钥。Desktop 会话快照按原样复制 Desktop 的会话文件（其中的 Cookie 等由
Desktop 自行加密），请像保护 Desktop 的数据目录一样保护本目录。

Claude Desktop 的数据目录：Microsoft Store 版为
`%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude`，安装程序版为
`%APPDATA%\Claude`；可用环境变量 `CLAUDE_STATUS_DESKTOP_DIR` 覆盖。识别 Desktop
进程时按安装位置判断：Desktop 内置的 Claude Code 与命令行 Claude Code 也叫
`claude.exe`，本工具不会结束它们。macOS 上的 Claude Code 订阅凭据保存在钥匙串
中，暂不支持切换。

## 开发

### 测试

```bash
python -m unittest discover -s tests -t .
```

测试使用 Qt 的 offscreen 平台，不需要显示器。Claude Code 配置、Desktop 数据
目录与进程列表全部指向临时目录中的假数据，不会联网，也不会改动或结束本机
真实的 Claude Code / Claude Desktop。每次推送后，CI 会在 Windows、Linux 与
macOS 上自动运行全部测试。

### 本地打包

```bash
pip install -r requirements-build.txt
python build.py
```

生成的程序在 `dist/` 下：Windows 为 `ClaudeStatus.exe`，Linux 为
`claude-status`，macOS 为 `Claude Status.app`。PyInstaller 不能交叉编译，在
哪个系统上构建就得到哪个系统的程序；发布版由 CI 在各平台上分别构建（见下一节）。

- `python build.py --onedir`：生成目录而不是单个文件。单文件程序每次启动都要
  先解压到临时目录，目录形式启动更快。
- `python build.py --console`：保留控制台窗口，程序出错时能看到报错信息。
- 构建完成后，脚本会用演示数据在后台启动一次程序、渲染全部页面，确认程序可用。
- 构建定义在 `ClaudeStatus.spec` 中，熟悉 PyInstaller 的话也可以直接运行
  `pyinstaller ClaudeStatus.spec`。Windows 版去掉了本程序用不到的 Qt 组件
  （软件 OpenGL、虚拟键盘及其带入的 Qt Quick / QML、PDF 插件、网络 TLS 插件与
  翻译文件），体积小了约四成，单文件版启动也更快。

### 持续集成与发布

GitHub Actions 流水线定义在 `.github/workflows/ci.yml`：

| 触发 | 执行 |
| --- | --- |
| 推送到任意分支，或 fork 发来的 PR | 在 Windows、Linux 与 macOS 上运行测试；全部通过后在[下载程序](#下载程序)表中的 6 个平台上分别打包，并用演示数据启动检查。产物可在运行页面底部下载，保留 30 天 |
| 推送 `v` 开头的标签 | 同上，然后把各平台的程序与 `SHA256SUMS.txt` 发布到对应的 Release，并附上自动生成的更新说明 |
| 在 Actions 页面手动运行 | 同推送到分支 |

只修改文档（`*.md`、`docs/`）的推送不会触发流水线；同一分支上有新的推送时，
还在进行的旧运行会被取消。

发布新版本：

1. 把 `claude_status/__init__.py` 中的 `__version__` 改为新版本号（如
   `0.2.0`），提交并推送。
2. 打上 `v` 加版本号的标签并推送：

   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```

3. 流水线完成后，Release 页面会出现各平台的程序。标签与 `__version__` 不一致
   时不会发布；版本号带字母的（如 `0.2.0rc1`）会标记为预发布。

### 项目结构

```
claude_status/
  app.py              入口：参数解析、字体回退、主题安装、截图模式
  app_icon.py         应用图标（QPainter 绘制），打包时导出为 .ico / .icns
  main_window.py      导航轨 + 应用栏 + 页面切换
  state.py            AppState：账号 / 设置 / 用量数据与后台扫描
  client_state.py     ClientManager：两个客户端的实时登录、额度查询与切换
  attribution.py      本机用量按来源与身份时间线归属到账号
  themes.py           界面风格：Material 动态配色与极简白（深色模式下为极简黑）
  exporters.py        导出为 sub2api 与 CPA（CLIProxyAPI）的导入格式
  oauth_login.py      在本工具中登录：PKCE、本机回调、换取令牌与账号资料
  switcher.py         切换与保存登录（备份、撤销、保留当前配置）
  code_config.py      Claude Code 凭据与 settings.json 供应商变量的读写
  claude_desktop.py   Desktop 安装检测、进程控制、会话快照与额度采样
  quota.py            额度模型与 OAuth 用量接口
  vault.py            保存的登录与会话快照
  secure.py           DPAPI 加密
  tasks.py            后台任务（QThread）
  models.py           Account、UsageRecord、Settings 等数据模型
  claude_code.py      Claude Code 日志解析（去重、缓存）与登录信息读取
  analytics.py        Dataset 聚合：逐日、模型、账号、项目、时段、连续天数
  pricing.py          模型单价与费用估算
  storage.py          配置读写、导入导出与合并
  demo_data.py        示例账号、演示用量与演示额度
  formatting.py       数字、金额与时间的中文格式化
  pages/              账号、客户端、统计、热力图、设置页面，账号对话框与切换编排
  widgets/            账号卡片、额度条、日历热力图、统计卡片、稀疏坐标轴图表等
tests/                单元测试与界面测试
docs/screenshots/     README 中的截图（演示数据，用 --screenshot 生成）
main.py               启动脚本
build.py              打包为可执行程序：检查环境、调用 PyInstaller、启动检查
ClaudeStatus.spec     PyInstaller 构建定义（收集的文件与 Qt 组件裁剪）
.github/workflows/    GitHub Actions：三个系统上测试，六个平台打包，打标签时发布
```
