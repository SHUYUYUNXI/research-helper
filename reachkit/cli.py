"""CLI: source gathering, search, batch collection and export."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__, __title__
from .core import collect, doctor, export, markdown, read, research, search
from .network import ReachError
from .catalog import READ_PLATFORMS, SEARCH_PLATFORMS, capabilities


def bounded_limit(value):
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("数量必须是整数。") from None
    if not 1 <= number <= 20:
        raise argparse.ArgumentTypeError("数量必须在 1 到 20 之间。")
    return number


def parser():
    root = argparse.ArgumentParser(description=f"{__title__} — AI 互联网能力、平台路由、研究与归档")
    root.add_argument("--version", action="version", version=f"{__title__} {__version__}")
    subs = root.add_subparsers(dest="command", required=True)
    for command in ("read", "collect", "search", "research"):
        sub = subs.add_parser(command)
        if command in {"search", "research"}:
            sub.add_argument("query")
            if command == "search":
                sub.add_argument("--platform", choices=SEARCH_PLATFORMS, default="github")
                sub.add_argument("--backend", default="auto")
            else:
                sub.add_argument("--platforms", default="github,bilibili", help="逗号分隔的搜索平台，最多 8 个")
        else:
            sub.add_argument("urls", nargs="+" if command == "read" else "*")
            sub.add_argument("--platform", choices=["auto", *READ_PLATFORMS], default="auto")
            sub.add_argument("--backend", default="auto", help="auto 或 capabilities 中列出的后端名")
            if command == "collect":
                sub.add_argument("--file", help="UTF-8 文本文件，每行一个链接，# 开头为注释")
        sub.add_argument("--limit", type=bounded_limit, default=10)
        sub.add_argument("--format", choices=["json", "md"], default="json")
        sub.add_argument("-o", "--output")
        sub.add_argument("--overwrite", action="store_true")
    for command in ("doctor", "watch"):
        sub = subs.add_parser(command)
        sub.add_argument("--live", action="store_true", help="读取公开样例，验证是否获得内容")
        sub.add_argument("--upstream", action="store_true", help="合并原渠道诊断，可能请求平台接口")
        sub.add_argument("--strict", action="store_true", help="存在依赖、配置缺失或请求故障时退出码为 3")
    subs.add_parser("capabilities", help="列出统一能力、候选后端与技能指南")
    sub = subs.add_parser("tool", help="带已配置凭据调用上游高级只读操作")
    sub.add_argument("tool", choices=["gh", "opencli", "bili", "twitter", "rdt"])
    sub.add_argument("arguments", nargs=argparse.REMAINDER)
    sub = subs.add_parser("skill", help="安装或移除联网找资料助手技能")
    group = sub.add_mutually_exclusive_group(required=True)
    group.add_argument("--install", action="store_true")
    group.add_argument("--uninstall", action="store_true")
    sub.add_argument("--path", help="技能根目录，技能将安装在其中的 reachkit 子目录")
    sub.add_argument("--lang", choices=["zh", "en"], default="zh")
    sub.add_argument("--force", action="store_true")
    sub.add_argument("--dry-run", action="store_true")
    sub = subs.add_parser("uninstall", help="移除联网找资料助手管理的技能，保留平台配置和共享工具")
    sub.add_argument("--path")
    sub.add_argument("--dry-run", action="store_true")
    # Detailed legacy options are handled by the maintained upstream parser.
    for command in ("install", "configure", "setup", "transcribe", "format", "check-update"):
        subs.add_parser(command, add_help=False, help="联网找资料助手工具链：" + command)
    return root


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        if argv and argv[0] in {"install", "configure", "setup", "transcribe", "format", "check-update"}:
            from .lifecycle import delegate, transcribe
            return transcribe(argv[1:]) if argv[0] == "transcribe" else delegate(argv[0], argv[1:])
        args = parser().parse_args(argv)
        if args.command in {"skill", "uninstall"}:
            from .lifecycle import skill
            data = skill(install=args.command == "skill" and args.install, path=args.path,
                         lang=getattr(args, "lang", "zh"), force=getattr(args, "force", False), dry_run=args.dry_run)
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0
        if args.command == "capabilities":
            print(json.dumps(capabilities(), ensure_ascii=False, indent=2))
            return 0
        if args.command == "tool":
            from .runtime import advanced_tool
            print(json.dumps(advanced_tool(args.tool, args.arguments), ensure_ascii=False, indent=2))
            return 0
        if args.command in {"doctor", "watch"}:
            data = doctor(args.live, upstream=args.upstream)
            if args.command == "watch":
                data["operation"] = "watch"
                data["channels"] = [item for item in data["channels"] if item["status"] not in {"ready_local", "configured", "backend_checked", "verified"}]
            print(json.dumps(data, ensure_ascii=False, indent=2))
            incomplete = any(item["status"] not in {"ready_local", "configured", "backend_checked", "verified"} for item in data["channels"])
            return 3 if args.strict and incomplete else 0
        if args.command == "search":
            data = search(args.query, args.platform, args.limit, backend=args.backend)
        elif args.command == "research":
            data = research(args.query, [item.strip() for item in args.platforms.split(",") if item.strip()], args.limit)
        elif args.command == "read":
            if len(args.urls) != 1:
                raise ReachError("read 只接受一个链接；多个链接请用 collect。")
            data = read(args.urls[0], args.platform, args.backend, args.limit)
        else:
            urls = list(args.urls)
            if args.file:
                try:
                    path = Path(args.file)
                    if path.stat().st_size > 256 * 1024:
                        raise ReachError("链接清单超过 256 KB。")
                    urls.extend(line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines()
                                if line.strip() and not line.lstrip().startswith("#"))
                except (OSError, UnicodeError):
                    raise ReachError("无法读取链接清单，请提供 UTF-8 文本文件。") from None
            data = collect(urls, args.platform, args.backend, args.limit)
        if args.output:
            export(data, args.output, args.format, args.overwrite)
            print(json.dumps({"ok": data["ok"], "output": str(Path(args.output).resolve()), "summary": data.get("summary")}, ensure_ascii=False))
        else:
            print(markdown(data) if args.format == "md" else json.dumps(data, ensure_ascii=False, indent=2))
        return 0 if data["ok"] else 3
    except ReachError as error:
        print(json.dumps({"ok": False, "error": str(error), "attempts": getattr(error, "attempts", [])}, ensure_ascii=False))
        return 1
    except (OSError, ValueError, RuntimeError) as error:
        from agent_reach.utils.text import scrub_url_credentials
        print(json.dumps({"ok": False, "error": scrub_url_credentials(error)}, ensure_ascii=False))
        return 1
    except KeyboardInterrupt:
        print(json.dumps({"ok": False, "error": "用户中止。"}, ensure_ascii=False))
        return 130


if __name__ == "__main__":
    sys.exit(main())
