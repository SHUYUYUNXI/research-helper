"""One operation-aware capability catalog for both built-in and upstream tools."""
from .providers import READERS, SEARCHERS
from .settings import tool_path

EXTERNAL = {
    "twitter": {"name": "Twitter/X", "read": ["twitter-cli", "opencli"], "search": ["twitter-cli", "opencli"], "guide": "social", "features": ["推文及回复", "长文", "用户时间线", "首页 Feed"]},
    "xiaohongshu": {"name": "小红书", "read": ["opencli", "xiaohongshu-mcp", "xhs-cli"], "search": ["opencli", "xiaohongshu-mcp", "xhs-cli"], "guide": "social", "features": ["搜索", "笔记", "楼中楼评论", "推荐流", "用户公开笔记"]},
    "reddit": {"name": "Reddit", "read": ["opencli", "rdt-cli"], "search": ["opencli", "rdt-cli"], "guide": "social", "features": ["帖子和评论", "Subreddit", "热门", "社区信息"]},
    "facebook": {"name": "Facebook", "read": ["opencli"], "search": ["opencli"], "guide": "social", "features": ["用户/主页", "Feed", "可见群组列表"]},
    "instagram": {"name": "Instagram", "read": ["opencli"], "search": ["opencli"], "guide": "social", "features": ["用户搜索", "用户帖子", "Explore", "收藏"]},
    "linkedin": {"name": "LinkedIn", "read": ["linkedin-mcp"], "search": ["linkedin-mcp"], "guide": "career", "features": ["个人资料", "公司资料", "人才搜索", "职位搜索"]},
    "boss": {"name": "Boss直聘", "read": [], "search": ["boss-cdp"], "guide": "career", "features": ["岗位搜索", "JD 全文（按指南调用上游公开 API）"]},
    "xiaoyuzhou": {"name": "小宇宙", "read": [], "search": [], "guide": "video", "features": ["播客转录", "标点和分段", "来源与时长"]},
    "xueqiu": {"name": "雪球", "read": ["xueqiu-api"], "search": ["xueqiu-api"], "guide": "finance", "features": ["行情", "股票搜索", "热帖", "热股"]},
}
COMMANDS = {"twitter-cli": "twitter", "opencli": "opencli", "rdt-cli": "rdt", "bili-cli": "bili", "xiaohongshu-mcp": "mcporter", "xhs-cli": "xhs", "linkedin-mcp": "mcporter", "boss-cdp": "boss", "exa-mcp": "mcporter", "gh-cli": "gh"}
NATIVE_FEATURES = {
    "github": ["仓库与 README", "仓库搜索", "Issue/PR 讨论", "代码搜索、PR diff、Actions、Release（tool/指南）"],
    "youtube": ["字幕与自动字幕", "视频搜索", "显式音频转录"],
    "bilibili": ["视频信息", "视频搜索", "字幕、热门（tool/指南）"],
    "v2ex": ["主题与回复", "热门主题"], "web": ["HTML/文本正文", "显式 Jina Reader"], "rss": ["RSS/Atom 列表与摘要"],
    "exa": ["Exa MCP 搜索", "配置 API Key 的搜索"],
    "baidu": ["热搜榜", "描述、热度与来源"], "juejin": ["推荐文章", "公开文章正文"],
    "csdn": ["公开博客正文"], "sspai": ["最新文章订阅", "公开正文"], "cnblogs": ["首页文章订阅", "公开正文"],
    "oschina": ["新闻订阅与摘要"], "douban": ["热门影评订阅列表"], "gitee": ["公开仓库信息与 README"], "ruanyifeng": ["博客/周刊订阅"],
}
READ_PLATFORMS = tuple(dict.fromkeys([*READERS, *(key for key, item in EXTERNAL.items() if item["read"])]))
SEARCH_PLATFORMS = tuple(dict.fromkeys([*SEARCHERS, *(key for key, item in EXTERNAL.items() if item["search"])]))


def candidates(platform, operation):
    if platform in EXTERNAL:
        return list(EXTERNAL[platform][operation])
    if platform == "exa":
        return ["exa-mcp", "exa-api"]
    if platform == "bilibili":
        return ["bili-cli", "direct", "opencli"]
    if platform == "youtube":
        return ["direct", "opencli"] if operation == "read" else ["direct"]
    if platform == "web":
        return ["direct", "jina"]
    if platform == "github":
        return ["direct", "gh-cli"]
    return ["direct"]


def capabilities():
    from .chinese import FEEDS
    from agent_reach.channels import get_all_channels
    names = {("exa" if item.name == "exa_search" else item.name): item.description for item in get_all_channels()}
    names.update({key: value[0] for key, value in FEEDS.items()})
    names.update({"baidu": "百度热搜", "juejin": "掘金", "csdn": "CSDN", "gitee": "Gitee"})
    channels = []
    for platform, name in names.items():
        guide = EXTERNAL.get(platform, {}).get("guide") or ("chinese" if platform in {"baidu", "juejin", "csdn", "gitee", *FEEDS} else "video" if platform in {"youtube", "bilibili"} else "dev" if platform == "github" else "search" if platform == "exa" else "web")
        item = {"platform": platform, "name": name, "read": platform in READ_PLATFORMS, "search": platform in SEARCH_PLATFORMS,
                "read_backends": candidates(platform, "read") if platform in READ_PLATFORMS else [],
                "search_backends": candidates(platform, "search") if platform in SEARCH_PLATFORMS else [],
                "guide": f"references/{guide}.md", "features": EXTERNAL.get(platform, {}).get("features", NATIVE_FEATURES.get(platform, []))}
        if platform == "instagram":
            item["search_scope"] = "用户搜索"
        if platform == "facebook":
            item["read_scope"] = "用户/主页；其他操作通过 social 指南调用"
        if platform == "douban":
            item["read_scope"] = "热门影评订阅列表"
        if platform == "boss":
            item["read_scope"] = "JD 全文由 career 指南调用上游公开 API"
        if platform == "xiaoyuzhou":
            item["transcribe"] = True
        channels.append(item)
    return {"ok": True, "operation": "capabilities", "channels": channels}


def local_status(item):
    platform = item["platform"]
    needed = list(dict.fromkeys(item["read_backends"] + item["search_backends"]))
    found = [backend for backend in needed if backend in COMMANDS and tool_path(COMMANDS[backend])]
    if platform in READERS and platform != "youtube":
        return "ready_local", "内置适配器就绪，尚未验证远端内容。", found
    if platform == "youtube":
        executable = tool_path("yt-dlp")
        if executable:
            from agent_reach.probe import probe_command
            probe = probe_command(executable, ["--ignore-config", "--no-cache-dir", "--version"])
            return ("ready_local" if probe.ok else "dependency_error", "字幕内容尚未验证。" if probe.ok else "yt-dlp 命令存在但不能正常执行。", found)
        return "needs_dependency", "需要 yt-dlp 或已连接的 OpenCLI。", found
    if platform == "exa":
        import os
        from .settings import settings
        if os.environ.get("EXA_API_KEY") or settings().get("exa_api_key"):
            return "configured", "Exa API Key 已配置，尚未请求。", found
        if found:
            return "ready_local", "mcporter 已安装；Exa 服务与搜索结果尚未验证。", found
        return "needs_dependency", "通过 reachkit install --system 配置 Exa MCP，或配置 EXA_API_KEY。", found
    if platform == "xiaoyuzhou":
        return "guided", "使用 video 指南安装播客脚本并配置 Groq。", found
    if found or platform == "xueqiu":
        return "needs_verification", "后端存在；会话和实际内容尚未验证，按对应指南确认。", found
    return "needs_dependency", "先运行 reachkit install，再按对应指南配置平台。", found
