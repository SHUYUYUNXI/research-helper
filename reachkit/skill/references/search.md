统一入口：`reachkit search "关键词" --platform exa`。默认先尝试已配置 Exa MCP，API Key 路径为备用；可用 `--backend exa-mcp` 或 `--backend exa-api` 明确选择。多平台任务用 `reachkit research "关键词" --platforms github,bilibili,exa`，再由宿主 AI 阅读结果并回答。

# 搜索工具

Exa AI 搜索引擎。

## Exa AI 搜索

高质量 AI 搜索引擎，适合查找技术文档、官方示例和相关网页。

```bash
mcporter call exa.web_search_exa query="query" numResults=5
mcporter call exa.web_search_exa query="library API code example" numResults=5
```

### 使用场景

| 场景 | 参数 |
|-----|------|
| 网页搜索 | `web_search_exa(query: "...", numResults: 5)` |
| 技术/代码资料 | `web_search_exa(query: "框架名 API 示例", numResults: 5)` |

> Exa MCP 的 `get_code_context_exa` 已弃用且默认不注册。代码问题也使用
> `web_search_exa`；需要精确搜索仓库内容时，改用 `dev.md` 中的 GitHub 搜索。

### 特点

- 擅长英文内容和技术文档
- 可通过查询词定位官方文档和代码示例
- 结果质量高

