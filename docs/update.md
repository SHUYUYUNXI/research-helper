# 联网找资料助手更新

联网找资料助手采用本地源码或 wheel 分发。获取新包后，在原安装环境运行 `python -m pip install --upgrade PATH_TO_PACKAGE`；再运行 `reachkit skill --install --force` 更新技能资源，`reachkit doctor` 检查本地状态。

`reachkit check-update` 查询底层 Agent-Reach 的上游版本。不要据此自动用 Agent-Reach 替换联网找资料助手，也不要将其结果当成联网找资料助手自身的在线版本。整合新上游版本前，对照源码差异并运行回归测试。

外部平台工具分别按其官方说明更新，更新后运行对应平台检查与实际内容验证。平台变更可能影响子命令、接口或登录态。

## yt-dlp 更新

保留 default/EJS 依赖。仅在用户选择更新这一工具时，在其安装环境执行；以下为上游兼容的 Bash 命令：

```bash
which yt-dlp  >/dev/null 2>&1 && { pipx install --force 'yt-dlp[default]' 2>/dev/null || uv tool install --force 'yt-dlp[default]' 2>/dev/null || python -m pip install -U 'yt-dlp[default]' 2>/dev/null; }
```
