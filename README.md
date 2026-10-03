# 联网找资料助手 0.2.4

**让 AI 帮你去不同网站找资料、读内容，再整理成带来源的结果。**

把问题或链接交给 AI，它通过本工具搜索相关网站、读取文章和讨论，汇总资料并保留来源。核心是联网找资料；字幕提取、音频转录、登录配置和故障诊断用于配合资料获取。

基于 Agent-Reach 1.5.0 扩展。原项目的 16 类渠道与 9 个新增中文来源进入统一能力目录；安装器和平台运行指南保留并接入新技能。具体操作范围由 `reachkit capabilities` 展示。

## 安装与开始使用

联网找资料助手沿用 `reachkit` 命令和 Python 包名，需要 Python 3.10+。先下载源码：

```bash
git clone https://github.com/SHUYUYUNXI/research-helper.git
cd research-helper
```

Windows 在源码目录执行：

```powershell
.\setup.ps1
.\找资料.ps1 doctor
.\找资料.ps1 skill --install
```

`setup.ps1` 把 Python 包和基础依赖装进本项目 `.venv`。启动脚本依次选择 `REACHKIT_PYTHON`、项目 `.venv`、PATH 中的 Python、Codex 随附 Python，并检查依赖。

其他环境：

```bash
python -m venv .venv
# 激活环境：Linux/macOS source .venv/bin/activate；Windows .venv\Scripts\Activate.ps1
python -m pip install .
reachkit skill --install
reachkit doctor
```

技能安装会查找已存在的 Codex、Agents、OpenCode、OpenClaw、Claude 技能目录；默认保留同名技能，更新使用 `--force`。也可指定目录：`reachkit skill --install --path /path/to/skills`。

装好技能后可直接对 AI 说：

- “结合 GitHub 和 B站，研究这个项目有哪些使用反馈，给出来源。”
- “读这些 CSDN、掘金、少数派文章，整理成带链接的技术资料。”
- “搜索小红书上的相关笔记，读有完整签名链接的结果，对比不同观点。”
- “把这个视频的字幕整理成要点；需要音频转写时再执行转录。”

AI 按 [技能入口](reachkit/skill/SKILL.md) 和 10 份主题指南调用工具。完整安装方法见 [安装指南](docs/install.md)。

## 统一功能

| 功能 | 用法 |
|---|---|
| URL 自动识别与读取 | `reachkit read "URL" --format md` |
| 指定平台搜索 | `reachkit search "关键词" --platform github --limit 5` |
| 多平台研究、保留成功和失败来源 | `reachkit research "关键词" --platforms github,bilibili --limit 3` |
| 批量读取、去重、来源归档 | `reachkit collect --file links.example.txt --format md -o sources.md` |
| 能力、候选后端和操作范围 | `reachkit capabilities` |
| 本地诊断 / 原渠道诊断 / 公开内容验证 | `reachkit doctor` / `doctor --upstream` / `doctor --live` |
| 安装、配置、交互设置 | `reachkit install` / `configure --help` / `setup` |
| 音频与视频转录 | `reachkit transcribe "URL或本地音频" --provider groq` |
| 小宇宙标点与分段 | `reachkit transcribe "播客URL" --polish` |
| GitHub 代码、PR diff、Actions、Release | `reachkit tool gh search code "关键词"` 等高级只读命令 |
| 平台高级阅读操作 | `reachkit tool opencli twitter timeline --help` 等；参见主题指南 |
| 小红书结果清理 | `reachkit format xhs --help` |
| 一次性状态检查，供宿主调度 | `reachkit watch --upstream` |
| 技能更新与移除 | `reachkit skill --install --force` / `reachkit uninstall` |
| MCP 工具调用 | 安装 `.[mcp]`，运行 `python -m reachkit.mcp_server` |

`research` 执行多平台检索；宿主 AI 使用返回内容完成推理和回答。`collect` 最多 50 个链接，`research` 最多 8 个平台，每个平台数量 1—20；失败项不会丢弃其他来源。JSON/Markdown 均保留来源、时间、后端和调用记录。导出默认不覆盖已有文件。

自动后端选择尊重配置顺序，并记录每次尝试。限流、风险状态、确定的空结果和不存在内容会停止当前来源；安装缺失和普通执行失败可尝试已列出的备用后端。Jina Reader 由用户显式选择：`--platform web --backend jina`。

## 平台能力

原渠道：GitHub、Twitter/X、YouTube、Reddit、Facebook、Instagram、B站、小红书、LinkedIn、Boss直聘、小宇宙、V2EX、雪球、RSS/Atom、Exa、普通网页。需要会话或外部工具的渠道，按技能指南完成配置和实际调用验证。

新增中文来源：

| 来源 | 内置入口 |
|---|---|
| 百度热搜 | 热搜榜、描述、热度、来源链接 |
| 掘金 | 推荐文章列表、公开文章正文 |
| CSDN | 公开博客文章正文 |
| 少数派 | 最新文章订阅、摘要、公开正文 |
| 博客园 | 首页订阅、摘要、公开正文 |
| 开源中国 | 新闻 RSS 列表、摘要 |
| 豆瓣 | 热门影评订阅列表、原文链接 |
| Gitee | 公开仓库信息、README |
| 阮一峰网络日志 | 博客与科技爱好者周刊订阅 |

新增来源的完整 URL 和操作例子见 [中文来源指南](reachkit/skill/references/chinese.md)。Gitee 不提供搜索；Instagram 搜索入口为用户搜索；Facebook 统一读取入口为用户/主页；Boss 的 JD 全文和其他平台高级操作见主题指南。OpenCLI 已安装时可用 `reachkit tool opencli list` 查看本机更多适配器。

## 配置、状态和维护

沿用 `~/.agent-reach/config.yaml`，统一入口把显式配置的 GitHub Token、Twitter Cookie、代理、转写 API Key 传入相关请求或子进程。YouTube 只有配置 `youtube_cookies_from` 后才读取该浏览器的 Cookie；读取字幕失败不会自动调用付费转写。

默认 `install` 检查依赖。用户选择安装工具时执行 `reachkit install --system --channels=opencli,bilibili` 等命令；各渠道安装条件以 `install --help` 与指南为准。

默认 `doctor` 显示本地状态；`--upstream` 记录平台工具/会话探测结果；`--live` 读取公开样例。`verified` 只证明报告中给出的操作与样例。`watch` 执行一轮检查，持续监控由宿主调度。联网找资料助手更新采用新的本地发布包；`check-update` 检查底层 Agent-Reach 版本。

MCP 提供 6 个工具：`get_status`、`list_capabilities`、`read_source`、`search_sources`、`research_topic`、`collect_sources`。参见 [维护指南](reachkit/skill/references/maintenance.md)。

## 开发与来源

```bash
python -m pip install ".[dev]"
python -m unittest discover -s tests_reachkit -v
python -m pytest tests -q
```

核心模块：`catalog.py` 能力目录；`core.py` 读取、研究与归档；`runtime.py` 外部工具桥接；`settings.py` 子进程配置；`lifecycle.py` 安装维护；`mcp_server.py` MCP；`chinese.py` 中文来源。上游平台代码在 `agent_reach/`，平台指南在 `reachkit/skill/references/`。

基于 [Panniantong/Agent-Reach](https://github.com/Panniantong/Agent-Reach)，提交 `a19a171fa980a0785849596492e0af4db800c82f`。保留 MIT [LICENSE](LICENSE) 与 [NOTICE](NOTICE)。新增实现及修改说明见 [变更记录](CHANGELOG.md)。

Twitter 配置接线：`reachkit read/search` 和 `reachkit tool twitter ...` 会把已保存的 Cookie 传为子进程的 `TWITTER_AUTH_TOKEN`、`TWITTER_CT0`；直接执行原始 `twitter` 命令仍需自行设置这两个环境变量。

B站统一入口的后端顺序：bili-cli → 内置 API → OpenCLI。小红书保留上游三后端链路：OpenCLI → xiaohongshu-mcp → xhs-cli；xhs-cli 仅用于已有显式 Cookie 的存量安装，详情见 social 指南。需要招聘功能时可向 AI 说“帮我配 Boss直聘”。
