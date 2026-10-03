"""Bounded, read-only bridges to the existing platform tools."""
import json
import re
import subprocess
import tempfile
from urllib.parse import parse_qs, urlsplit

from .network import ReachError
from .settings import child_env, tool_path

MAX_TOOL_BYTES = 4 * 1024 * 1024


def redact_child_output(text, env):
    from agent_reach.utils.text import scrub_url_credentials
    text = scrub_url_credentials(text)
    for key, secret in env.items():
        if any(marker in key.upper() for marker in ("TOKEN", "KEY", "PASSWORD", "COOKIE", "SECRET")) and len(secret) >= 8:
            text = text.replace(secret, "[REDACTED]")
    return text


def command_output(command, args, timeout=90, env=None):
    path = tool_path(command, env)
    if not path:
        raise ReachError(f"未安装 {command}；运行 reachkit install 检查所需依赖。")
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        try:
            run = subprocess.run([path, *args], stdin=subprocess.DEVNULL, stdout=output, stderr=errors,
                                 timeout=timeout, env=env or child_env())
        except subprocess.TimeoutExpired:
            raise ReachError(f"{command} 超时；查看对应技能恢复指南。") from None
        except OSError:
            raise ReachError(f"{command} 无法执行，请修复或重新安装该工具。") from None
        output.seek(0)
        body = output.read(MAX_TOOL_BYTES + 1)
        if len(body) > MAX_TOOL_BYTES:
            raise ReachError(f"{command} 返回内容超过 4 MB。")
        if run.returncode:
            # Raw stderr may contain credentials. Never copy it into results.
            kind = {66: "empty", 69: "network", 75: "network", 77: "risk", 78: "configuration"}.get(run.returncode, "unknown") if command == "opencli" else "unknown"
            raise ReachError(f"{command} 执行失败（退出码 {run.returncode}）；请按平台指南确认登录态和接口。", kind)
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        raise ReachError(f"{command} 没有返回内容。", "empty")
    try:
        value = json.loads(text)
        if value is None or value is False:
            raise ReachError(f"{command} 返回空结果或业务错误。", "empty")
    except ValueError:
        value = None
    if isinstance(value, dict) and value.get("isError") is True:
        raise ReachError(f"{command} 返回 MCP 工具错误。", "empty")
    if isinstance(value, dict) and isinstance(value.get("content"), list):
        # MCP content envelopes may contain another JSON business response.
        inner = "\n".join(block.get("text", "") for block in value["content"] if isinstance(block, dict))
        if inner:
            text = inner
            try:
                value = json.loads(inner)
            except ValueError:
                value = None
    if value == [] or value == {} or isinstance(value, dict) and (
        value.get("ok") is False or value.get("success") is False or value.get("error")
        or value.get("code") not in (None, 0, "0", 200, "200")
        or value.get("status") in ("error", "failed")
        or any(key in value and value[key] == [] for key in ("items", "results", "entries", "data"))
    ):
        raise ReachError(f"{command} 返回空结果或业务错误；未获得有效内容。", "empty")
    if re.search(r"\b(?:AUTH_EXPIRED|ENVIRONMENT_RISK|ACCOUNT_RISK|login required|not logged in)\b", text, re.I):
        raise ReachError(f"{command} 返回登录或风险状态；停止请求，按平台指南处理。", "risk")
    return redact_child_output(text, env or child_env())


def reddit_id(url):
    match = re.search(r"/comments/([A-Za-z0-9]+)", urlsplit(url).path)
    if match:
        return match[1]
    if urlsplit(url).hostname == "redd.it":
        return urlsplit(url).path.strip("/")
    raise ReachError("Reddit 请提供具体帖子链接。")


def platform_args(platform, operation, value, backend, limit=10):
    if backend == "opencli":
        if platform == "twitter":
            return "opencli", ["twitter", "search" if operation == "search" else "thread", value, "--limit", str(limit), "-f", "json"]
        if platform == "xiaohongshu":
            if operation == "read" and not parse_qs(urlsplit(value).query).get("xsec_token"):
                raise ReachError("小红书详情需要带 xsec_token 的完整搜索结果链接；先搜索再读取。")
            return "opencli", [platform, "search" if operation == "search" else "note", value, *(["--limit", str(limit)] if operation == "search" else []), "-f", "json"]
        if platform == "reddit":
            return "opencli", [platform, "search" if operation == "search" else "read", value if operation == "search" else reddit_id(value), *(["--limit", str(limit)] if operation == "search" else []), "-f", "json"]
        if platform == "youtube" and operation == "read":
            return "opencli", ["youtube", "transcript", value, "-f", "json"]
        if platform == "bilibili":
            return "opencli", [platform, "search" if operation == "search" else "video", value, *(["--limit", str(limit)] if operation == "search" else []), "-f", "json"]
        if platform == "facebook":
            slug = value if operation == "search" else urlsplit(value).path.strip("/")
            if operation == "read" and (not slug or "/" in slug):
                raise ReachError("Facebook 此入口读取用户/主页 URL；帖子、Feed 和群组操作见 social 指南。")
            return "opencli", [platform, "search" if operation == "search" else "profile", slug, "-f", "json"]
        if platform == "instagram":
            slug = value if operation == "search" else urlsplit(value).path.strip("/")
            if operation == "read" and (not slug or "/" in slug):
                raise ReachError("Instagram 请提供用户主页；search 搜索用户，user 读取指定用户帖子。")
            return "opencli", [platform, "search" if operation == "search" else "user", slug, "-f", "json"]
    if platform == "twitter" and backend == "twitter-cli":
        env = child_env()
        if not env.get("TWITTER_AUTH_TOKEN") or not env.get("TWITTER_CT0"):
            raise ReachError("Twitter CLI 需要明确配置的 Cookie；先 reachkit configure twitter-cookies。")
        return "twitter", ["search", value, "-n", str(limit)] if operation == "search" else ["tweet", value]
    if platform == "reddit" and backend == "rdt-cli":
        from agent_reach.channels.reddit import RedditChannel
        checked = RedditChannel()._check_rdt()
        if checked is None or "检测到显式保存的 Reddit Cookie" not in checked[1]:
            raise ReachError("rdt-cli 需要已有且有效的显式 Cookie；查看 social 登录指南。")
        return "rdt", ["search", value, "--limit", str(limit)] if operation == "search" else ["read", reddit_id(value)]
    if platform == "bilibili" and backend == "bili-cli":
        return "bili", ["search", value, "--type", "video", "-n", str(limit)] if operation == "search" else ["video", value]
    if platform == "xiaohongshu" and backend == "xhs-cli":
        from agent_reach.channels.xiaohongshu import XiaoHongShuChannel
        checked = XiaoHongShuChannel()._check_xhs_cli()
        if checked is None or "检测到显式保存的 Cookie" not in checked[1]:
            raise ReachError("xhs-cli 仅复用已有的有效显式 Cookie；按 social 指南配置 MCP 或 OpenCLI。")
        if operation == "read" and not parse_qs(urlsplit(value).query).get("xsec_token"):
            raise ReachError("小红书详情需要带 xsec_token 的完整结果链接。")
        return "xhs", ["search" if operation == "search" else "read", value]
    if platform == "xiaohongshu" and backend == "xiaohongshu-mcp":
        if operation == "search":
            return "mcporter", ["call", "xiaohongshu.search_feeds", f"keyword={value}", "--timeout", "120000"]
        parsed = urlsplit(value)
        token = parse_qs(parsed.query).get("xsec_token", [""])[0]
        note = parsed.path.strip("/").split("/")[-1]
        if not token or not re.fullmatch(r"[A-Za-z0-9_-]+", note):
            raise ReachError("小红书需要带 xsec_token 的完整笔记 URL，先搜索再读取。")
        return "mcporter", ["call", "xiaohongshu.get_feed_detail", f"feed_id={note}", f"xsec_token={token}", "--timeout", "120000"]
    if platform == "linkedin" and backend == "linkedin-mcp":
        if operation == "search":
            return "mcporter", ["call", "linkedin.search_people", f"keywords={value}"]
        parts = urlsplit(value).path.strip("/").split("/")
        if len(parts) != 2 or parts[0] not in {"in", "company"}:
            raise ReachError("LinkedIn 请提供 /in/用户 或 /company/公司 页面。")
        tool, parameter = ("get_person_profile", "linkedin_username") if parts[0] == "in" else ("get_company_profile", "company_name")
        return "mcporter", ["call", "linkedin." + tool, f"{parameter}={parts[1]}"]
    if platform == "boss" and backend == "boss-cdp" and operation == "search":
        from agent_reach.channels.boss import BossChannel
        channel = BossChannel()
        channel.check()
        if channel.active_backend is None:
            raise ReachError("Boss CDP 链路未就绪；按 career 指南配置专用 Chrome 并手动登录。")
        if channel.browser_login_cookie is not True:
            raise ReachError("Boss 浏览器登录态未确认；请在专用 Chrome 中确认登录后重试。", "configuration")
        return "boss", ["--browser-source", "existing-browser", "--cdp-url", "http://localhost:9222", "--json", "search", value, "--page", "1"]
    raise ReachError("该操作没有此后端；用 reachkit capabilities 查看能力和指南。")


def bridge(platform, operation, value, backend, limit=10):
    from .providers import result
    if backend == "opencli":
        from agent_reach.backends.opencli import opencli_status
        if not opencli_status().ready:
            raise ReachError("OpenCLI 浏览器桥接未连接；打开已登录的浏览器并连接扩展。")
    command, args = platform_args(platform, operation, value, backend, limit)
    text = command_output(command, args, timeout=150 if "mcp" in backend else 90)
    if platform == "xiaohongshu":
        try:
            from agent_reach.channels.xiaohongshu import format_xhs_result
            parsed = json.loads(text)
            candidate = parsed.get("data", parsed) if isinstance(parsed, dict) else parsed
            cleaned = format_xhs_result(candidate)
            # Some MCP envelopes aren't note objects; preserve their content.
            if cleaned and (isinstance(cleaned, list) and any(cleaned) or isinstance(cleaned, dict) and any(k in cleaned for k in ("title", "desc", "content", "id", "note_id"))):
                text = json.dumps(cleaned, ensure_ascii=False, indent=2)
        except (ValueError, TypeError):
            pass
    # Bound returned collections even where the tool only supports a whole page.
    items = []
    try:
        parsed = json.loads(text)
        candidate = parsed.get("data", parsed) if isinstance(parsed, dict) else parsed
        if isinstance(candidate, dict):
            candidate = next((candidate[key] for key in ("items", "results", "feeds", "notes", "jobs", "jobList", "people") if isinstance(candidate.get(key), list)), candidate)
        if isinstance(candidate, list):
            rows = candidate[:limit]
            for row in rows:
                if isinstance(row, dict):
                    items.append({"title": str(row.get("title") or row.get("name") or row.get("jobName") or row.get("id") or "结果"), "url": str(row.get("url") or row.get("share_url") or row.get("link") or ""), "text": json.dumps(row, ensure_ascii=False, indent=2)})
            if items:
                text = ""
    except ValueError:
        pass
    return result(platform, backend, value if operation == "search" else platform + " 内容",
                  value if operation == "read" else "", text, items=items,
                  warnings=["返回的是该后端此次取得的内容；平台其他操作见相应技能参考文档。"])


def advanced_tool(command, args):
    """Preserve advanced upstream read operations with configured child env."""
    allowed = {
        "gh": {"search": {"repos", "code", "issues", "prs"}, "repo": {"view"}, "issue": {"list", "view"}, "pr": {"list", "view", "checks", "diff"}, "run": {"list", "view"}, "workflow": {"list", "view"}, "release": {"list", "view"}},
        "bili": {"video", "search", "hot", "rank"},
        "twitter": {"search", "tweet", "article", "feed", "user", "user-posts"},
        "rdt": {"search", "read", "sub", "popular", "all"},
        "opencli": {"twitter": {"search", "thread", "article", "profile", "timeline"}, "xiaohongshu": {"search", "note", "comments", "feed", "user"}, "bilibili": {"search", "video", "subtitle", "hot", "rank"}, "reddit": {"search", "read", "subreddit", "hot", "popular", "subreddit-info"}, "facebook": {"search", "profile", "feed", "groups"}, "instagram": {"search", "profile", "user", "explore", "saved"}, "xueqiu": {"whoami", "search", "stock", "hot", "hot-stock"}, "youtube": {"search", "transcript"}},
    }
    if not args or command not in allowed:
        raise ReachError("此工具未在只读调用目录中。")
    rule = allowed[command]
    if isinstance(rule, dict):
        if command == "opencli" and args == ["list"]:
            pass
        elif len(args) < 2 or args[0] not in rule or args[1] not in rule[args[0]]:
            raise ReachError("此工具操作不在只读调用目录中，平台高级操作请查看技能指南。")
    elif args[0] not in rule:
        raise ReachError("此操作不在只读调用目录中。")
    if command == "twitter":
        env = child_env()
        if not env.get("TWITTER_AUTH_TOKEN") or not env.get("TWITTER_CT0"):
            raise ReachError("先显式配置 Twitter Cookie。")
    if command == "rdt":
        from agent_reach.channels.reddit import RedditChannel
        checked = RedditChannel()._check_rdt()
        if checked is None or "检测到显式保存的 Reddit Cookie" not in checked[1]:
            raise ReachError("rdt-cli 需要已有的有效显式 Cookie；按 social 指南配置。")
    if command == "opencli" and args != ["list"]:
        from agent_reach.backends.opencli import opencli_status
        if not opencli_status().ready:
            raise ReachError("OpenCLI 浏览器桥接未连接。")
    return {"ok": True, "operation": "tool", "tool": command, "text": command_output(command, args)}
