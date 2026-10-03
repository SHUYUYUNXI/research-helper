# 中文来源

| 来源 | 输入与范围 |
|---|---|
| 百度热搜 | `https://top.baidu.com/board?tab=realtime`，榜单、描述和热度 |
| 掘金 | `https://juejin.cn/` 推荐列表，`/post/编号` 公开正文 |
| CSDN | `https://blog.csdn.net/用户/article/details/编号` 正文 |
| 少数派 | `https://sspai.com/feed` 文章清单，公开文章 URL 正文 |
| 博客园 | `https://www.cnblogs.com/rss` 清单，公开文章 URL 正文 |
| 开源中国 | `https://www.oschina.net/news/rss` 新闻条目和摘要 |
| 豆瓣 | `https://movie.douban.com/feed/review/movie` 热门影评条目；正文不在此直连适配器范围 |
| Gitee | 公开仓库首页 URL，仓库信息与 README；没有仓库搜索入口 |
| 阮一峰 | `https://www.ruanyifeng.com/blog/atom.xml` 周刊和博客内容 |

调用 `reachkit read "URL" --limit 5`，需要多来源就 `reachkit collect URL1 URL2 --format md -o sources.md`。优先依照返回的标题、正文、条目和来源继续阅读，而不是只向用户列接口。

榜单、RSS、推荐列表提供发现入口，不等于全文已经取得。用户要一篇文章的内容时继续读取具体文章 URL。用户要搜索这些来源时可用 Exa 的 site: 查询；不要虚构 Gitee、百度热搜或豆瓣的直接全文搜索接口。

直连文章失败时，查看错误类型。公开文章可由用户明确选择 `--platform web --backend jina`，或使用已连接浏览器适配器。CSDN 正文未取得、订阅条目为空、登录/验证页均不能记成功；限流时暂停，不连续换代理重试。
