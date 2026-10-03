# 联网找资料助手安装指南

## Python 包和技能

Windows 使用项目目录的 `setup.ps1` 创建 `.venv` 并安装本地包，再运行 `reachkit.ps1 skill --install`。指定 Python 可设置 `REACHKIT_PYTHON`。

通用方式：创建并激活 Python 3.10+ 虚拟环境，运行 `python -m pip install .`。离线分发可使用构建的 `reachkit-0.2.1-py3-none-any.whl`，基础依赖需要预先安装或可访问包源。

```bash
reachkit --version
reachkit capabilities
reachkit doctor
reachkit skill --install
```

`skill --path` 指技能根目录，其下创建 `reachkit` 子目录；包含 SKILL.md 和全部 10 份参考文档。默认语言中文，`--lang en` 选择英文入口。已有技能默认保留，更新使用 `--force`，预览使用 `--dry-run`。

## 平台工具

`reachkit install --env=auto` 默认检查系统与依赖，不代表已安装全部平台。实际安装选定工具使用 `--system --channels=...`；桌面/服务器、Node/uv/pipx/Chrome/Docker 等要求沿用上游安装器，运行 `reachkit install --help` 查看选项。

例如：

```bash
reachkit install --system --channels=opencli,bilibili
reachkit doctor --upstream
```

OpenCLI 还需要 Chrome 扩展桥接、明确选择的浏览器和对应平台登录态。Boss 需要专用 Chrome CDP 浏览器，不能把 `session.enc` 当成已验证的 CDP 登录。小红书详情需要搜索结果中完整的 xsec_token 链接。小宇宙需要 Bash、ffmpeg、Groq Key 和安装的转录脚本。

配置沿用 `~/.agent-reach/config.yaml`。运行 `reachkit configure --help` 或 `reachkit setup`；技能中的 social、career、video 指南描述具体平台流程。Cookie 由用户明确提供或在用户指定的浏览器中配置。

## MCP

```bash
python -m pip install ".[mcp]"
python -m reachkit.mcp_server
```

在宿主 MCP 配置中填入已安装该包的 Python **绝对路径**，参数 `-m reachkit.mcp_server`，通过 stdio 连接。不要把未安装依赖的 Python 当成 MCP 运行环境。

## 验证与卸载

默认体检验证本地适配器；`doctor --upstream` 探测原工具；`doctor --live` 测试公开内容。需要会话的平台应按用户实际任务执行一次 read/search 确认。

`reachkit uninstall` 或 `skill --uninstall` 只移除本工具管理的技能文件，保留用户自建文件、平台配置和共享外部工具。Python 包可在其安装环境中执行 `python -m pip uninstall reachkit`。

Twitter 配置接线：`reachkit read/search` 和 `reachkit tool twitter ...` 会把已保存的 Cookie 传为子进程的 `TWITTER_AUTH_TOKEN`、`TWITTER_CT0`；直接执行原始 `twitter` 命令仍需自行设置这两个环境变量。

## 招聘与登录配置

**LinkedIn (个人、公司与人才资料)**：先由用户登录，使用当前 stdio 服务：

```bash
uvx mcp-server-linkedin@latest --login
mcporter config add linkedin --command uvx --arg mcp-server-linkedin@latest --env UV_HTTP_TIMEOUT=300 --scope home
```

用户说“帮我配 Boss直聘”时，AI 按 career 指南安装工具、启动专用 Chrome，再由用户手动登录并验证。安装 `reachkit install --env=local --system --channels=boss`；保留的兼容命令是 `agent-reach install --env=local --system --channels=boss`。专用 Chrome 使用 `--remote-debugging-address=127.0.0.1`，只在回环地址开放 CDP；CDP 允许对该专用浏览器完全控制，使用独立 profile 并长期复用登录态。

小红书 OpenCLI 只复用已经存在且明确控制的浏览器会话。`xhs-cookies` 导入供 MCP/存量工具使用，不会把 Cookie 注入 OpenCLI 或 Chrome。详情读取使用搜索结果中的完整签名链接。
