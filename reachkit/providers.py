"""Small, independent adapters. Each adapter returns actual source content."""

import json
import os
import re
import subprocess
import tempfile
import urllib.parse
from pathlib import Path

from .network import ReachError, public_url
from .parsers import clean_text, page_text, parse_feed, subtitle_text


def result(platform, backend, title, url, text="", items=None, warnings=None, metadata=None):
    if not str(text).strip() and not items:
        raise ReachError("返回内容为空，不能算作获取成功。", "empty")
    return {"platform": platform, "backend": backend, "title": title, "url": url,
            "text": text, "items": items or [], "warnings": warnings or [], "metadata": metadata or {}}


def web(http, url, backend="direct", limit=10):
    if backend == "jina":
        response = http.get("https://r.jina.ai/" + url, {"Accept": "text/plain"})
        text = response.text.strip()
        title = next((line[7:].strip() for line in text.splitlines() if line.startswith("Title: ")), url)
        low = text[:8000].lower()
        if "requiring captcha" in low or "performing security verification" in low:
            raise ReachError("Jina 返回验证页面，未获取到正文。")
        return result("web", "jina", title, url, text,
                      warnings=["本次链接交由 Jina Reader 处理。"])
    response = http.get(url)
    if "html" in response.content_type:
        title, text = page_text(response.text)
        low = response.text[:12000].lower()
        if ("/cdn-cgi/challenge-platform/" in low
                or title.lower() in {"just a moment...", "attention required! | cloudflare"}):
            raise ReachError("网站要求浏览器验证，可改用浏览器或显式指定 --backend jina。")
        return result("web", "direct-html", title or url, response.url, text,
                      warnings=["采用 HTML 文本提取，动态加载内容和部分布局信息可能缺失。"])
    if response.content_type.startswith("text/") or response.content_type in {"application/json", "application/xml"}:
        return result("web", "direct-text", url, response.url, response.text)
    raise ReachError("此链接返回二进制文件；第一版支持网页、文本和 RSS，不支持 PDF/图片解析。")


def rss(http, url, backend="direct", limit=10):
    response = http.get(url)
    title, items = parse_feed(response.body, response.url, limit)
    return result("rss", "xml", title or url, response.url, items=items)


def github_headers():
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    from .settings import child_env
    env = child_env()
    token = env.get("GH_TOKEN") or env.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    return headers


def github(http, url, backend="direct", limit=10):
    path = urllib.parse.urlsplit(url).path.strip("/").split("/")
    if len(path) < 2:
        raise ReachError("请提供 GitHub 仓库链接或 Issue/PR 链接。")
    owner, name = path[:2]
    name = name.removesuffix(".git")
    if not all(re.fullmatch(r"[A-Za-z0-9_.-]+", value) for value in (owner, name)):
        raise ReachError("GitHub 仓库名称无效。")
    api = f"https://api.github.com/repos/{owner}/{name}"
    headers = github_headers()
    if len(path) == 4 and path[2] in {"issues", "pull"} and path[3].isdigit():
        issue = http.json(api + "/issues/" + path[3], headers)
        comments = http.json(api + f"/issues/{path[3]}/comments?per_page={limit}", headers)
        items = [{"title": "评论 · " + item["user"]["login"], "url": item["html_url"],
                  "text": item.get("body") or "", "published_at": item["created_at"]} for item in comments]
        return result("github", "github-api", issue["title"], issue["html_url"], issue.get("body") or issue["title"], items,
                      warnings=[f"最多读取 {limit} 条评论；PR 此处读取讨论，未读取代码差异。"],
                      metadata={"state": issue["state"], "author": issue["user"]["login"]})
    if len(path) > 2:
        raise ReachError("GitHub 渠道暂支持仓库首页和 Issue/PR；文件页面可指定 --platform web。")
    repo = http.json(api, headers)
    body = repo.get("description") or ""
    warnings = []
    try:
        readme = http.get(api + "/readme", {**headers, "Accept": "application/vnd.github.raw+json"})
        body = readme.text
    except ReachError as error:
        warnings.append("README 未获取：" + str(error))
    return result("github", "github-api", repo["full_name"], repo["html_url"], body or repo["full_name"],
                  warnings=warnings, metadata={"description": repo.get("description"),
                  "stars": repo["stargazers_count"], "language": repo.get("language"),
                  "default_branch": repo["default_branch"], "license": (repo.get("license") or {}).get("spdx_id")})


def github_search(http, query, limit):
    url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode({"q": query, "per_page": limit, "sort": "stars"})
    data = http.json(url, github_headers())
    items = [{"title": item["full_name"], "url": item["html_url"], "text": item.get("description") or "",
              "stars": item["stargazers_count"]} for item in data.get("items", [])]
    return result("github", "github-api", query, "https://github.com/search?" + urllib.parse.urlencode({"q": query, "type": "repositories"}),
                  items=items, metadata={"total_count": data.get("total_count")})


def bili_json(http, endpoint):
    data = http.json("https://api.bilibili.com" + endpoint,
                     {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"})
    if data.get("code") != 0:
        raise ReachError(f"B站接口拒绝请求（code={data.get('code')}），可能需要登录或浏览器验证。")
    return data.get("data") or {}


def bilibili(http, url, backend="direct", limit=10):
    match = re.search(r"/video/(BV[A-Za-z0-9]+)", urllib.parse.urlsplit(url).path)
    if not match:
        raise ReachError("请提供包含 BV 号的 B站视频链接；短链接暂不支持。")
    data = bili_json(http, "/x/web-interface/view?" + urllib.parse.urlencode({"bvid": match[1]}))
    title = data.get("title")
    if not title:
        raise ReachError("B站接口没有返回视频信息。")
    return result("bilibili", "bilibili-public-api", title, f"https://www.bilibili.com/video/{match[1]}",
                  data.get("desc") or title, warnings=["本次获取视频简介和元数据，未获取字幕或视频画面。"],
                  metadata={"author": (data.get("owner") or {}).get("name"), "duration_seconds": data.get("duration"),
                            "statistics": data.get("stat"), "published_at_unix": data.get("pubdate")})


def bilibili_search(http, query, limit):
    data = bili_json(http, "/x/web-interface/search/type?" + urllib.parse.urlencode({"search_type": "video", "keyword": query, "page": 1}))
    items = [{"title": page_text(item.get("title", ""))[1], "url": "https://www.bilibili.com/video/" + item["bvid"],
              "text": item.get("description") or "", "author": item.get("author")} for item in data.get("result", [])[:limit]]
    return result("bilibili", "bilibili-public-api", query, "https://search.bilibili.com/all?" + urllib.parse.urlencode({"keyword": query}), items=items)


def v2ex(http, url, backend="direct", limit=10):
    path = urllib.parse.urlsplit(url).path
    if path in {"", "/", "/?tab=hot"}:
        topics = http.json("https://www.v2ex.com/api/topics/hot.json")
        items = [{"title": topic["title"], "url": topic["url"], "text": topic.get("content") or ""} for topic in topics[:limit]]
        return result("v2ex", "v2ex-public-api", "V2EX 热门", url, items=items)
    match = re.fullmatch(r"/t/(\d+)/?", path)
    if not match:
        raise ReachError("V2EX 暂支持首页热门或 /t/帖子编号。")
    topics = http.json("https://www.v2ex.com/api/topics/show.json?id=" + match[1])
    if not topics:
        raise ReachError("未找到该 V2EX 帖子。")
    replies = http.json("https://www.v2ex.com/api/replies/show.json?" + urllib.parse.urlencode({"topic_id": match[1], "page": 1}))
    items = [{"title": "回复 · " + reply["member"]["username"], "url": url,
              "text": reply.get("content") or ""} for reply in replies[:limit]]
    return result("v2ex", "v2ex-public-api", topics[0]["title"], topics[0]["url"], topics[0].get("content") or topics[0]["title"], items,
                  warnings=[f"只读取首页最多 {limit} 条回复。"])


def run_ytdlp(arguments):
    from .settings import tool_path
    command = tool_path("yt-dlp")
    if not command:
        raise ReachError("未找到 yt-dlp。请先安装 yt-dlp，并确保该命令在 PATH 中。")
    from .settings import child_env, ytdlp_options
    # Explicit configured cookies/JS runtime are passed without shell interpolation.
    try:
        process = subprocess.run([command, "--ignore-config", "--no-cache-dir", "--socket-timeout", "20", "--retries", "1", *ytdlp_options(), *arguments],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=150, env=child_env())
    except subprocess.TimeoutExpired:
        raise ReachError("yt-dlp 超时，已停止。") from None
    except OSError:
        raise ReachError("yt-dlp 无法执行，请检查安装。") from None
    if process.returncode:
        raise ReachError(f"yt-dlp 执行失败（退出码 {process.returncode}）；可能需要更新工具、字幕不可用或遇到平台验证。")
    try:
        return json.loads(process.stdout)
    except ValueError:
        raise ReachError("yt-dlp 未返回有效的视频数据。") from None


def youtube(http, url, backend="direct", limit=10):
    # Input is restricted to video URLs; arbitrary URLs never go to the downloader.
    parsed = urllib.parse.urlsplit(url)
    if parsed.hostname == "youtu.be":
        video_id = parsed.path.strip("/")
    elif parsed.path == "/watch":
        video_id = urllib.parse.parse_qs(parsed.query).get("v", [""])[0]
    else:
        match = re.fullmatch(r"/(shorts|live|embed)/([A-Za-z0-9_-]{11})/?", parsed.path)
        video_id = match[2] if match else ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ReachError("请提供单个 YouTube 视频链接。")
    canonical = "https://www.youtube.com/watch?v=" + video_id
    with tempfile.TemporaryDirectory(prefix="reachkit-subtitles-") as folder:
        data = run_ytdlp(["--no-playlist", "--skip-download", "--no-simulate", "--write-subs", "--write-auto-subs", "--sub-langs", "zh.*,en.*", "--sub-format", "vtt", "--dump-single-json", "-o", str(Path(folder) / "video.%(ext)s"), "--", canonical])
        subtitles = sorted(Path(folder).glob("video.*.vtt"), key=lambda p: (".zh" not in p.name, p.name))
        transcript = next((text for file in subtitles if (text := subtitle_text(file.read_text(encoding="utf-8")))), "")
    if not transcript:
        raise ReachError("没有取得字幕；可换 OpenCLI，或显式运行 reachkit transcribe 转写音频。", "no_subtitles")
    return result("youtube", "yt-dlp", data.get("title") or canonical, canonical, transcript,
                  warnings=["字幕可能是自动生成；文本未包含视频画面信息。"],
                  metadata={"author": data.get("uploader"), "duration_seconds": data.get("duration")})


def youtube_search(http, query, limit):
    data = run_ytdlp(["--flat-playlist", "--dump-single-json", "--", f"ytsearch{limit}:{query}"])
    items = [{"title": entry.get("title") or entry["id"], "url": "https://www.youtube.com/watch?v=" + entry["id"],
              "text": entry.get("description") or ""} for entry in data.get("entries", []) if entry]
    return result("youtube", "yt-dlp", query, "https://www.youtube.com/results?" + urllib.parse.urlencode({"search_query": query}), items=items)


def exa_search(http, query, limit):
    from .settings import settings
    key = os.environ.get("EXA_API_KEY") or settings().get("exa_api_key")
    if not key:
        raise ReachError("全网搜索需要 EXA_API_KEY 环境变量；Exa 按你的账号额度或计费规则收费。")
    data = http.json("https://api.exa.ai/search", {"x-api-key": key},
                     {"query": query, "numResults": limit, "type": "auto", "contents": {"highlights": True}})
    items = [{"title": item.get("title") or item["url"], "url": item["url"],
              "text": item.get("text") or "\n".join(item.get("highlights") or []),
              "published_at": item.get("publishedDate")} for item in data.get("results", [])]
    return result("exa", "exa-api", query, "https://exa.ai", items=items,
                  metadata={"cost_dollars": data.get("costDollars")})


def exa_mcp_search(query, limit):
    from .runtime import command_output
    text = command_output("mcporter", ["call", "exa.web_search_exa", f"query={query}", f"numResults={limit}"])
    return result("exa", "exa-mcp", query, "https://exa.ai", text)


READERS = {"web": web, "rss": rss, "github": github, "bilibili": bilibili, "v2ex": v2ex, "youtube": youtube}
SEARCHERS = {"github": github_search, "bilibili": bilibili_search, "youtube": youtube_search, "exa": exa_search}


def route(url):
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    for platform, domains in {"twitter": ("x.com", "twitter.com"), "xiaohongshu": ("xiaohongshu.com", "xhslink.com"), "reddit": ("reddit.com", "redd.it"), "facebook": ("facebook.com", "fb.com", "fb.watch"), "instagram": ("instagram.com", "instagr.am"), "linkedin": ("linkedin.com",), "boss": ("zhipin.com",), "xiaoyuzhou": ("xiaoyuzhoufm.com",), "xueqiu": ("xueqiu.com",)}.items():
        if any(host == domain or host.endswith("." + domain) for domain in domains):
            return platform
    from .chinese import DOMAINS
    for platform, domain in DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            return platform
    for domain, platform in (("github.com", "github"), ("bilibili.com", "bilibili"), ("youtube.com", "youtube"), ("youtu.be", "youtube"), ("v2ex.com", "v2ex")):
        if host == domain or host.endswith("." + domain):
            return platform
    if re.search(r"(?:/(?:feed|rss|atom)(?:/|$)|\.(?:rss|xml)$)", parsed.path, re.I):
        return "rss"
    return "web"


from . import chinese

READERS.update(chinese.READERS)
SEARCHERS.update(chinese.SEARCHERS)

