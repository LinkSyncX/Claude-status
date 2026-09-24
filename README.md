# Claude Status · Claude 账号管理与用量统计

基于本仓库的 `md3`（PySide6 Material Design 3 组件库）构建的桌面工具：
管理多个 Claude 账号，一键切换 Claude Code 与 Claude Desktop 的登录，查看各
账号的 5 小时与每周额度，并从本机 Claude Code 日志统计 token 用量、估算费用、
绘制活跃热力图。

## 功能

- **账号管理**：新建 / 编辑 / 删除（可撤销）、收藏、状态标记（正常 / 受限 /
  已过期 / 已停用）；卡片与列表两种视图，支持搜索、状态筛选与排序；账号卡片
  显示 5 小时与本周额度、两个客户端的登录状态（`Code 使用中` / `Desktop 使用中`）
  与本月用量；右侧详情面板显示额度（含按模型的周额度与 Desktop 采样走势）、
  资料与近 30 天用量；月度预算进度与超支提醒；复制密钥或终端环境变量；JSON
  导入导出（可选是否包含密钥）。
- **一键切换**：账号卡片上的“切换”按钮把 Claude Code 与（可选）Claude Desktop
  一起切换到该账号；也可以在菜单或“客户端”页只切换其中一个。
- **客户端**：
  - Claude Code：当前生效的是订阅登录还是中转 / API 配置、令牌有效期；保存
    当前登录、把当前中转配置保存为账号、可切换账号列表。
  - Claude Desktop：安装方式与版本、运行状态、当前登录的账号；保存当前登录、
    登录新账号、退出 / 启动 Desktop；已保存的会话、额度走势与 MCP 服务器列表。
- **数据统计**：7 天 / 30 天 / 90 天 / 1 年 / 全部，按 Token、费用或请求数
  查看；关键指标与上一个等长区间对比；按模型系列堆叠的用量趋势、模型分布、
  账号对比、项目排行、Token 构成、缓存命中率与模型明细表。
- **热力图**：GitHub 风格的活跃日历（近一年或按年份），连续活跃天数、单日
  峰值；点击任意一天查看当日明细与 24 小时分布；一周时段分布（星期 × 小时）；
  账号 × 月份矩阵。
- **设置**：数据源与日志目录；切换与额度（切换时是否包含 Desktop、切换后是否
  重启 Desktop、是否联网查询额度、代理）；深色模式与主题色；模型单价表与自定义
  单价；数据目录管理。

## 运行

```bash
pip install -r requirements.txt
python main.py
```

常用参数（`python main.py --help` 查看全部）：

| 参数 | 说明 |
| --- | --- |
| `--demo` | 本次启动使用演示数据（首次启动时还会添加示例账号）；演示模式下不会切换真实的客户端 |
| `--offline` | 不联网查询额度 |
| `--dark` | 以深色主题启动（并记住该选择） |
| `--data-dir DIR` | 使用指定的配置目录（便于试用而不影响正式数据） |
| `--page clients` | 启动后直接打开某个页面（accounts / clients / dashboard / heatmap / settings） |
| `--screenshot DIR` | 不显示窗口，把每个页面渲染为 PNG 后退出（总是离线） |

## 添加账号并切换

**Claude Code（订阅账号）**

1. 在终端运行 `claude /login` 登录账号 A，然后在“客户端”页点击“保存当前
   登录”（没有对应账号时自动新建）。
2. 再次运行 `claude /login` 登录账号 B 并保存。
3. 之后点击账号卡片上的“切换”即可在 A、B 之间切换。切换前会自动备份当前
   配置，提示条中可以撤销。切换后新启动的 Claude Code 使用新账号，已在运行的
   会话建议重新启动。

中转 / API 账号在账号编辑对话框中填写 Base URL、密钥与“额外环境变量”（每行
一个 `KEY=VALUE`，例如 `ANTHROPIC_DEFAULT_SONNET_MODEL=…` 模型映射），切换
时写入 `~/.claude/settings.json` 的 `env`（只替换 `ANTHROPIC_*` 与
`CLAUDE_CODE_SUBAGENT_MODEL`，其余设置保持不变）；切回订阅账号时移除这些变量。
如果 `settings.json` 里已经有中转配置，可在“客户端”页一键保存为账号。

**Claude Desktop**

1. 在 Desktop 中登录账号 A，然后在“客户端”页点击“保存当前登录…”并选择账号。
2. 点击“登录新账号…”：当前会话先被保存，然后清空登录并启动 Desktop，登录
   账号 B 后同样保存。
3. 之后一键切换即可。切换需要退出 Desktop：会先征得确认并请求其正常退出，
   若它最小化到托盘而没有退出，会再询问是否强制结束；完成后按设置重新启动。

Desktop 的登录会话包括 Chromium 存储（Cookie、Local Storage、IndexedDB 等）
与 `config.json` 中的账号相关键；主题等普通设置、MCP 配置、Desktop 内置的
Claude Code 会话与额度采样属于全局数据，不随账号切换。恢复时任何一步失败都会
回滚到原状态。无法归属到账号的会话会另存备份，不会丢失。

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
- 日志不记录请求来自哪个账号，因此本机日志的用量会归属到“关联本机日志”的
  那个账号（同一时间只能关联一个；未关联时显示为“未归属”）。
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

## 项目结构

```
claude_status/
  app.py              入口：参数解析、字体回退、主题安装、截图模式
  main_window.py      导航轨 + 应用栏 + 页面切换
  state.py            AppState：账号 / 设置 / 用量数据与后台扫描
  client_state.py     ClientManager：两个客户端的实时登录、额度查询与切换
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
```

## 测试

```bash
python -m unittest discover -s tests -t .
```

测试使用 Qt 的 offscreen 平台，不需要显示器。Claude Code 配置、Desktop 数据
目录与进程列表全部指向临时目录中的假数据，不会联网，也不会改动或结束本机
真实的 Claude Code / Claude Desktop。

## 关于 md3 的几个问题

开发中发现 `md3` 组件库的三处缺陷，本应用在自己的子类中做了绕过，库代码
未做修改：

1. `charts/bar_chart.py` 的 `_category_progress` 按下标线性累加入场错开量
   （每个分类 0.06），超过约 16 个分类时后面的柱子在动画结束后仍是 0 高度。
   见 `widgets/dense_charts.py` 的 `DenseBarChart`。
2. `feedback/banner.py` 在按钮与文字同行时没有给文字列设置伸展系数，长文字
   会被挤成很窄的一列。见 `widgets/common.py` 的 `InfoBanner`。
3. `core/overlay.py` 的 `FloatingPanel._animate_to` 以 `DeleteWhenStopped`
   启动动画却保留 Python 引用，打开动画结束后再关闭面板（或宿主窗口改变尺寸）
   会访问已删除的对象而抛出 `RuntimeError`，侧边 / 底部面板因此无法正常关闭。
   见 `widgets/common.py` 的 `DetailSheet`。
