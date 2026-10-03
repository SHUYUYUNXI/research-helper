"""Chinese public sources verified during development, 2026-10-03."""

import base64
import json
import re
import urllib.parse

from .network import ReachError
from .parsers import page_text, parse_feed


FEEDS = {
    "sspai": ("少数派", "https://sspai.com/feed", "sspai.com"),
    "cnblogs": ("博客园", "https://www.cnblogs.com/rss", "cnblogs.com"),
    "oschina": ("开源中国", "https://www.oschina.net/news/rss", "oschina.net"),
    "douban": ("豆瓣影评", "https://movie.douban.com/feed/review/movie", "douban.com"),
    "ruanyifeng": ("阮一峰的网络日志", "https://www.ruanyifeng.com/blog/atom.xml", "ruanyifeng.com"),
}
DOMAINS = {**{key: item[2] for key, item in FEEDS.items()},
           "gitee": "gitee.com", "baidu": "top.baidu.com", "juejin": "juejin.cn", "csdn": "blog.csdn.net"}
SAMPLES = {**{key: item[1] for key, item in FEEDS.items()},
           "gitee": "https://gitee.com/mirrors/iptv", "baidu": "https://top.baidu.com/board?tab=realtime",
           "juejin": "https://juejin.cn/", "csdn": "https://blog.csdn.net/2401_85122467/article/details/139470188"}


def build(*args, **kwargs):
    from .providers import result
    return result(*args, **kwargs)


def ensure_domain(platform, url):
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    domain = DOMAINS[platform]
    if host != domain and not host.endswith("." + domain):
        raise ReachError("链接域名与指定平台不匹配。")


def feed_reader(platform):
    def read(http, url, backend="direct", limit=10):
        ensure_domain(platform, url)
        name, feed, domain = FEEDS[platform]
        path = urllib.parse.urlsplit(url).path
        is_feed = path in {"", "/", "/feed", "/rss", "/news/rss", "/blog/atom.xml", "/feed/review/movie"}
        if is_feed:
            response = http.get(feed)
            title, items = parse_feed(response.body, response.url, limit)
            return build(platform, "official-feed", title or name, response.url, items=items,
                         warnings=["条目正文长度由站点订阅源决定；标题和链接可用于继续读取文章。"])
        if platform == "douban":
            raise ReachError("豆瓣新增功能目前为热门影评订阅列表；影评正文页面需要浏览器访问。")
        response = http.get(url, {"User-Agent": "Mozilla/5.0"})
        selectors = {"cnblogs": {"target_id": "cnblogs_post_body"}, "sspai": {"target_class": "article-body"}}
        title, text = page_text(response.text, **selectors.get(platform, {}))
        return build(platform, "public-article", title or url, response.url, text)
    return read


def csdn(http, url, backend="direct", limit=10):
    ensure_domain("csdn", url)
    if not re.fullmatch(r"/[^/]+/article/details/\d+/?", urllib.parse.urlsplit(url).path):
        raise ReachError("CSDN 请提供具体的博客文章链接。")
    response = http.get(url, {"User-Agent": "Mozilla/5.0"})
    title, text = page_text(response.text, target_id="content_views")
    return build("csdn", "public-article", title or url, response.url, text)


def gitee(http, url, backend="direct", limit=10):
    ensure_domain("gitee", url)
    parts = urllib.parse.urlsplit(url).path.strip("/").split("/")
    if len(parts) != 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", value) for value in parts):
        raise ReachError("Gitee 请提供公开仓库首页链接。")
    api = "https://gitee.com/api/v5/repos/" + "/".join(parts)
    data = http.json(api)
    readme = http.json(api + "/readme")
    if readme.get("encoding") != "base64":
        raise ReachError("Gitee README 编码发生变化。")
    try:
        text = base64.b64decode(readme["content"]).decode("utf-8", "replace")
    except (KeyError, ValueError):
        raise ReachError("Gitee README 返回内容异常。") from None
    return build("gitee", "gitee-api", data["full_name"], data["html_url"], text,
                 metadata={"description": data.get("description"), "stars": data.get("stargazers_count"),
                           "default_branch": data.get("default_branch")})


def baidu(http, url, backend="direct", limit=10):
    ensure_domain("baidu", url)
    response = http.get("https://top.baidu.com/board?tab=realtime", {"User-Agent": "Mozilla/5.0"})
    match = re.search(r"<!--s-data:(.*?)-->", response.text, re.S)
    try:
        data = json.loads(match[1]) if match else {}
        cards = data["data"]["cards"]
        rows = next(card["content"] for card in cards if card.get("component") == "hotList")
    except (KeyError, ValueError, StopIteration, TypeError):
        raise ReachError("百度热搜页面结构发生变化，未提取到榜单。") from None
    items = [{"title": row["word"], "url": row.get("url") or row.get("appUrl") or row.get("rawUrl") or url,
              "text": row.get("desc") or "", "rank": row.get("index"), "hot_score": row.get("hotScore")} for row in rows[:limit]]
    return build("baidu", "public-hot-list", "百度热搜", response.url, items=items)


def juejin(http, url, backend="direct", limit=10):
    ensure_domain("juejin", url)
    path = urllib.parse.urlsplit(url).path
    match = re.fullmatch(r"/post/(\d+)/?", path)
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://juejin.cn/"}
    if match:
        response = http.get(url, headers)
        title, text = page_text(response.text, target_class="markdown-body")
        return build("juejin", "public-article", title or url, response.url, text)
    if path not in {"", "/", "/recommended"}:
        raise ReachError("掘金请提供首页或 /post/文章编号。")
    data = http.json("https://api.juejin.cn/recommend_api/v1/article/recommend_all_feed", headers,
                     {"id_type": 2, "client_type": 2608, "sort_type": 200, "limit": limit, "cursor": "0"})
    if data.get("err_no") != 0:
        raise ReachError("掘金拒绝了推荐列表请求。")
    items = []
    for row in data.get("data") or []:
        info = (row.get("item_info") or {}).get("article_info") or {}
        if not info.get("article_id"):
            continue
        items.append({"title": info.get("title") or "", "url": "https://juejin.cn/post/" + str(info["article_id"]),
                      "text": info.get("brief_content") or ""})
    return build("juejin", "public-recommend-api", "掘金推荐", "https://juejin.cn/", items=items[:limit])


READERS = {**{platform: feed_reader(platform) for platform in FEEDS}, "csdn": csdn, "gitee": gitee, "baidu": baidu, "juejin": juejin}
SEARCHERS = {}
