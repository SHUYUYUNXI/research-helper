"""Source collection and portable, traceable exports."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .network import HTTP, ReachError, public_url
from .providers import READERS, SEARCHERS, route


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _xueqiu(operation, value, limit):
    from agent_reach.channels.xueqiu import XueqiuChannel
    from .providers import result
    channel = XueqiuChannel()
    try:
        if operation == "search":
            items = channel.search_stock(value, limit)
            return result("xueqiu", "xueqiu-api", value, "https://xueqiu.com", items=items)
        import re
        from urllib.parse import urlsplit
        path = urlsplit(value).path
        match = re.fullmatch(r"/S/([A-Za-z0-9.]+)", path)
        quote = channel.get_stock_quote(match[1]) if match else None
        if not quote or not quote.get("name") or quote.get("current") is None:
            raise ReachError("雪球此入口读取 /S/股票代码 页面；未得到有效行情。")
        return result("xueqiu", "xueqiu-api", quote["name"], value, json.dumps(quote, ensure_ascii=False, indent=2))
    except ReachError:
        raise
    except Exception:
        raise ReachError("雪球请求失败，请按 finance 指南核对 Cookie 和接口。") from None


def _dispatch(platform, operation, value, backend, limit, http):
    if backend == "xueqiu-api":
        return _xueqiu(operation, value, limit)
    if backend == "exa-mcp":
        from .providers import exa_mcp_search
        return exa_mcp_search(value, limit)
    if backend == "gh-cli":
        from .runtime import command_output
        from .providers import result
        if operation == "search":
            args = ["search", "repos", value, "--limit", str(limit), "--json", "fullName,url,description"]
        else:
            from urllib.parse import urlsplit
            parts = urlsplit(value).path.strip("/").split("/")
            if len(parts) == 4 and parts[2] in {"issues", "pull"} and parts[3].isdigit():
                args = ["issue" if parts[2] == "issues" else "pr", "view", value, "--json", "title,url,body,comments"]
            elif len(parts) == 2:
                args = ["repo", "view", value]
            else:
                raise ReachError("GitHub 后端读取仓库首页或具体 Issue/PR 链接。", "format")
        text = command_output("gh", args)
        return result("github", "gh-cli", value, value if operation == "read" else "", text)
    if backend not in {"direct", "jina", "exa-api"}:
        from .runtime import bridge
        return bridge(platform, operation, value, backend, limit)
    try:
        if operation == "read":
            return READERS[platform](http or HTTP(), value, backend=backend, limit=limit)
        return SEARCHERS[platform](http or HTTP(), value, limit)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ReachError("平台响应格式发生变化，未获得有效内容。", "format") from None


def _execute(platform, operation, value, backend, limit, http):
    from .catalog import candidates
    from .settings import settings
    cfg = settings()
    choices = candidates(platform, operation)
    override = cfg.get(f"{platform}_backend") or (cfg.get("exa_search_backend") if platform == "exa" else None)
    if override:
        normalized = str(override).lower().replace(" ", "-")
        aliases = {"exa-via-mcporter": "exa-mcp", "gh-cli": "gh-cli", "b站搜索-api": "direct", "yt-dlp": "direct", "xhs-cli-(xiaohongshu-cli)": "xhs-cli", "boss-agent-cli-(cdp-chrome)": "boss-cdp"}
        normalized = aliases.get(normalized, normalized)
        if normalized in choices:
            choices.remove(normalized)
            choices.insert(0, normalized)
    if backend != "auto":
        if backend not in choices:
            raise ReachError("此平台不支持所选后端；用 reachkit capabilities 查看候选。")
        choices = [backend]
    # Sending a URL to Jina is an explicit choice; auto stays with configured tools.
    if backend == "auto":
        choices = [choice for choice in choices if choice != "jina"]
    attempts = []
    for choice in choices:
        try:
            data = _dispatch(platform, operation, value, choice, limit, http)
            data["attempts"] = attempts + [{"backend": choice, "ok": True}]
            return {"ok": True, "operation": operation, "fetched_at": timestamp(), **data}
        except ReachError as error:
            attempts.append({"backend": choice, "ok": False, "error": str(error)})
            if error.kind in {"rate_limit", "not_found", "empty", "format", "risk"} or platform == "boss":
                break
    if not attempts:
        raise ReachError("此操作需按技能参考文档调用上游工具。")
    error = ReachError("；".join(f"{item['backend']}: {item['error']}" for item in attempts))
    error.attempts = attempts
    raise error


def read(url, platform="auto", backend="auto", limit=10, http=None):
    url = public_url(url)
    platform = route(url) if platform == "auto" else platform
    from .catalog import READ_PLATFORMS
    if platform not in READ_PLATFORMS:
        raise ReachError("此渠道操作见技能参考文档，使用 reachkit capabilities 查看入口。")
    if platform != "web" and route(url) != platform:
        raise ReachError("链接域名与指定平台不匹配。")
    return _execute(platform, "read", url, backend, limit, http)


def search(query, platform="github", limit=10, http=None, backend="auto"):
    if not query.strip():
        raise ReachError("搜索词不能为空。")
    from .catalog import SEARCH_PLATFORMS
    if platform not in SEARCH_PLATFORMS:
        raise ReachError("该渠道没有搜索入口，使用 reachkit capabilities 查看能力范围。")
    return _execute(platform, "search", query.strip(), backend, limit, http)


def collect(urls, platform="auto", backend="auto", limit=10, http=None):
    if len(urls) > 50:
        raise ReachError("单次最多采集 50 个链接。")
    results, seen = [], set()
    for index, url in enumerate(urls, 1):
        if not url.strip():
            continue
        try:
            normalized = public_url(url)
            if normalized in seen:
                continue
            seen.add(normalized)
            results.append(read(normalized, platform, backend, limit, http))
        except ReachError as error:
            # Do not echo a rejected URL; it might contain user/password data.
            results.append({"ok": False, "input_index": index,
                            "fetched_at": timestamp(), "error": str(error), "attempts": getattr(error, "attempts", [])})
    if not results:
        raise ReachError("没有可采集的链接。")
    count = sum(item["ok"] for item in results)
    return {"ok": count == len(results), "operation": "collect", "fetched_at": timestamp(),
            "summary": {"succeeded": count, "failed": len(results) - count, "total": len(results)}, "results": results}


def research(query, platforms=("github", "bilibili"), limit=5, http=None):
    platforms = list(dict.fromkeys(platforms))
    from .catalog import SEARCH_PLATFORMS
    if not query.strip() or not platforms or len(platforms) > 8 or any(p not in SEARCH_PLATFORMS for p in platforms):
        raise ReachError("请提供搜索词以及 1—8 个支持搜索的平台。")
    results = []
    for platform in platforms:
        try:
            results.append(search(query, platform, limit, http))
        except ReachError as error:
            results.append({"ok": False, "platform": platform, "error": str(error), "attempts": getattr(error, "attempts", [])})
    count = sum(item["ok"] for item in results)
    return {"ok": count == len(results), "operation": "research", "query": query, "fetched_at": timestamp(),
            "summary": {"succeeded": count, "failed": len(results) - count, "total": len(results)}, "results": results}


def _md_heading(value):
    return str(value).replace("\r", " ").replace("\n", " ").replace("#", "").strip()


def markdown(data):
    if data.get("operation") in {"collect", "research"}:
        summary = data["summary"]
        lines = ["# 联网找资料助手资料集", "", f"成功 {summary['succeeded']} · 失败 {summary['failed']}", ""]
        for number, item in enumerate(data["results"], 1):
            lines += [f"<!-- SOURCE {number} -->", markdown(item), "", "---", ""]
        return "\n".join(lines)
    if not data.get("ok"):
        return "## 获取失败\n\n" + data.get("error", "未知错误") + "\n"
    lines = ["# " + _md_heading(data.get("title", "资料")), "", "来源：" + data.get("url", ""),
             "", "获取时间（UTC）：" + data.get("fetched_at", ""), "",
             f"渠道：{data.get('platform', '')} / {data.get('backend', '')}", ""]
    if data.get("metadata"):
        lines += ["```json", json.dumps(data["metadata"], ensure_ascii=False, indent=2), "```", ""]
    for warning in data.get("warnings", []):
        lines += ["> " + warning, ""]
    if data.get("text"):
        lines += [data["text"], ""]
    for item in data.get("items", []):
        lines += ["## " + _md_heading(item.get("title", "条目")), "", "来源：" + item.get("url", ""), ""]
        if item.get("published_at"):
            lines += ["发布时间：" + str(item["published_at"]), ""]
        lines += [item.get("text", ""), ""]
    return "\n".join(lines)


def export(data, output, fmt="json", overwrite=False):
    path = Path(output)
    text = markdown(data) if fmt == "md" else json.dumps(data, ensure_ascii=False, indent=2)
    # x mode prevents silently overwriting an existing source archive.
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w" if overwrite else "x", encoding="utf-8", newline="\n") as stream:
            stream.write(text + "\n")
    except FileExistsError:
        raise ReachError("输出文件已存在。请更换文件名，或显式使用 --overwrite。") from None
    except OSError:
        raise ReachError("无法写入输出文件，请检查路径和权限。") from None


def doctor(live=False, http=None, upstream=False):
    """Local readiness and optional content verification are separate fields."""
    channels = []
    samples = {"web": "https://example.com", "rss": "https://www.python.org/blogs/rss/",
               "github": "https://github.com/Panniantong/Agent-Reach", "bilibili": "https://www.bilibili.com/video/BV1GJ411x7h7",
               "v2ex": "https://www.v2ex.com/"}
    from .chinese import SAMPLES
    samples.update(SAMPLES)
    from .catalog import capabilities, local_status
    upstream_results = {}
    if upstream:
        from agent_reach.doctor import check_all
        from .settings import settings, child_env
        from unittest.mock import patch
        with patch.dict(os.environ, {"PATH": child_env()["PATH"]}):
            upstream_results = check_all(settings())
    for capability in capabilities()["channels"]:
        name = capability["platform"]
        status, message, available = local_status(capability)
        item = {**capability, "status": status, "message": message, "available_backends": available,
                "verified_at": None, "verified_operation": None, "active_backend": None}
        original = upstream_results.get("exa_search" if name == "exa" else name)
        if original:
            item["upstream_probe"] = original
            item["active_backend"] = original["active_backend"]
            # Preserve native readiness even if its optional CLI is missing.
            if name not in READERS or name == "youtube":
                item["status"] = {"ok": "backend_checked", "warn": "needs_configuration", "off": "needs_dependency", "error": "dependency_error"}.get(original["status"], "needs_verification")
                item["message"] = original["message"]
        if live and name in samples:
            try:
                observed = read(samples[name], platform=name, backend="direct", limit=1, http=http)
                item.update(status="verified", message="样例读取返回非空内容。", verified_at=observed["fetched_at"], verified_operation="read", active_backend=observed["backend"], sample_url=samples[name])
            except ReachError as error:
                item.update(status="request_failed", message=str(error))
        channels.append(item)
    return {"ok": True, "version": __version__, "operation": "doctor", "fetched_at": timestamp(),
            "channels": channels, "upstream_channels": 16,
            "upstream_command": "reachkit doctor --upstream",
            "note": "统一展示 16 类原渠道与 9 个中文来源。默认不请求远端；--live 验证公开样例，--upstream 合并原渠道诊断。verified 只证明列出的样例操作。"}
