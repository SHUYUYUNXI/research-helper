# 安装与维护

从交付的联网找资料助手源码目录安装 `python -m pip install .`，然后 `reachkit install` 检查依赖。用户已授权系统安装时运行 `reachkit install --system --channels=所需平台`；它沿用原安装器并注册联网找资料助手技能。

技能可独立安装：`reachkit skill --install`；指定根目录：`--path PATH`；英语：`--lang en`；更新现有技能：`--force`。默认保留已有技能，自定义文件不被批量删除。

配置使用 `reachkit configure KEY` 隐藏输入或 `--stdin`。KEY 包括 proxy/github-token/groq-key/openai-key/twitter-cookies/youtube-cookies/xhs-cookies。浏览器 Cookie 显式导入和 profile 选择按对应平台指南进行。

`reachkit doctor` 统一显示能力及本地状态；`--upstream` 追加上游诊断，`--live` 验证公开样例。`verified_operation` 只说明此次样例；例如 RSS 列表成功不能当成网站全部正文成功。

`reachkit watch` 输出未就绪项供外部调度器使用；它自身不创建定时任务。`reachkit check-update` 检查底层 Agent-Reach 更新，联网找资料助手自身按交付的新版包更新。更新后运行 `reachkit skill --install --force`、`reachkit doctor`，并读取所需平台的内容确认功能。

`reachkit uninstall --dry-run` 预览技能清理，正式清理仅移除本工具清单里的技能文件。平台配置、浏览器会话和共享上游工具保留；若用户要求完整清理，再按明确范围处理。

MCP：安装 `python -m pip install ".[mcp]"`，以 `python -m reachkit.mcp_server` 启动 stdio 服务。工具包括 get_status/list_capabilities/read_source/search_sources/research_topic/collect_sources。
