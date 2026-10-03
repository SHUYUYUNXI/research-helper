# 联网找资料助手故障处理

1. 启动提示缺依赖：运行项目 `setup.ps1`，或使用同一个 Python 执行 `python -m pip install .`。启动脚本优先使用项目 `.venv`。
2. `needs_dependency`：先 `reachkit install` 查看所需工具，再按需要安装指定渠道。
3. `needs_verification`：工具存在但会话和内容未验证，按该渠道技能指南登录并读取真实来源。
4. `configured` / `ready_local`：配置或本地入口存在，尚未取得该平台内容。
5. `backend_checked`：上游探测已通过，探测深度看 `upstream_probe`；仍应使用实际任务验证内容。
6. `needs_configuration` / `dependency_error`：上游探测发现缺登录、配置或命令故障；使用报告中的消息和指南恢复。
7. `verified`：指定的公开样例操作取得非空内容，查看 `verified_operation`、`verified_at`、`sample_url`。
8. `request_failed`：内容访问失败，检查来源权限、限流和响应变化。

返回的 `attempts` 保存本次候选后端与失败原因。显式 `--backend` 只调用选定后端；自动选择不会在风险状态、限流和确定空结果后反复请求。Boss 的登录/风险错误按 career 指南处理。

小红书 Cookie 导入成功与登录确认分开报告；否定登录文本或非零退出码不会被当作登录成功。YouTube 无字幕时可以显式选择 `transcribe`；付费供应商切换需 `--allow-provider-fallback`。

输出文件已存在时更换路径或明确传入 `--overwrite`。批量部分失败退出码为 3，结果中保留其他成功来源。运行中止退出码为 130。

Twitter 配置接线：`reachkit read/search` 和 `reachkit tool twitter ...` 会把已保存的 Cookie 传为子进程的 `TWITTER_AUTH_TOKEN`、`TWITTER_CT0`；直接执行原始 `twitter` 命令仍需自行设置这两个环境变量。
