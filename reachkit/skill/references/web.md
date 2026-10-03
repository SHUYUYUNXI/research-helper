统一读取和导出：`reachkit read "URL" --format md`；批量归档：`reachkit collect --file links.txt --format md -o sources.md`。Jina 是显式选择：`--platform web --backend jina`。RSS 解析不等于自动订阅监控；用户要求持续监控时才配置宿主的调度功能。

# 网页阅读

通用网页、RSS。

## 通用网页 (Jina Reader)

```bash
# 读取任意网页内容
curl -s "https://r.jina.ai/URL"

# 示例
curl -s "https://r.jina.ai/https://example.com/article"
```

**适用场景**: 大多数网页可以直接用 Jina Reader 读取。

## RSS (feedparser)

```python
python3 -c "
import feedparser
for e in feedparser.parse('FEED_URL').entries[:5]:
    print(f'{e.title} — {e.link}')
"
```

**适用场景**: 订阅博客、新闻源、播客等 RSS feed。

## 选择指南

| 场景 | 推荐工具 |
|-----|---------|
| 通用网页 | Jina Reader (`curl r.jina.ai`) |
| RSS 订阅 | feedparser |
