"""Register the 联网找资料助手 skill and reuse the maintained upstream installer."""
import importlib.resources
import json
import os
from pathlib import Path
import sys

from agent_reach.utils.paths import atomic_write_private_text, ensure_no_symlink_path
from .network import ReachError


def skill_roots(path=None):
    if path:
        return [Path(path).expanduser().absolute()]
    roots = [Path.home() / item for item in (".codex/skills", ".agents/skills", ".config/opencode/skills", ".openclaw/skills", ".claude/skills")]
    extra = os.environ.get("OPENCLAW_HOME")
    if extra:
        roots.append(Path(extra) / ".openclaw/skills")
    existing = list(dict.fromkeys(root for root in roots if root.is_dir()))
    return existing or [Path.home() / ".agents/skills"]


def skill(install=True, path=None, lang="zh", force=False, dry_run=False):
    package = importlib.resources.files("reachkit").joinpath("skill")
    outcomes = []
    for root in skill_roots(path):
        target = root / "reachkit"
        ensure_no_symlink_path(target)
        marker = target / ".reachkit-skill.json"
        if install:
            if (target / "SKILL.md").exists() and not force:
                outcomes.append({"path": str(target), "status": "preserved", "hint": "使用 --force 更新已安装技能。"})
                continue
            files = {"SKILL.md": package.joinpath("SKILL_en.md" if lang == "en" else "SKILL.md").read_text(encoding="utf-8")}
            for item in package.joinpath("references").iterdir():
                if item.name.endswith(".md"):
                    files["references/" + item.name] = item.read_text(encoding="utf-8")
            if not dry_run:
                for name, text in files.items():
                    atomic_write_private_text(target / name, text)
                atomic_write_private_text(marker, json.dumps({"name": "reachkit", "files": list(files)}, ensure_ascii=False))
            outcomes.append({"path": str(target), "status": "planned" if dry_run else "installed", "resources": len(files)})
        else:
            if not marker.is_file():
                outcomes.append({"path": str(target), "status": "unmanaged_or_missing"})
                continue
            managed = json.loads(marker.read_text(encoding="utf-8"))
            if managed.get("name") != "reachkit":
                raise ReachError("技能目录没有有效的联网找资料助手管理标记。")
            for name in [*managed["files"], marker.name]:
                relative = Path(name)
                if relative.is_absolute() or ".." in relative.parts:
                    raise ReachError("技能管理清单包含无效路径。")
                item = target / relative
                ensure_no_symlink_path(item)
                if not dry_run:
                    item.unlink(missing_ok=True)
            if not dry_run:
                for item in (target / "references", target):
                    try:
                        item.rmdir()
                    except OSError:
                        pass  # Preserve files not managed by 联网找资料助手.
            outcomes.append({"path": str(target), "status": "planned" if dry_run else "removed"})
    return {"ok": True, "operation": "skill", "results": outcomes}


def delegate(command, args):
    from agent_reach import cli
    from unittest.mock import patch
    def install_reachkit_skill(force=True):
        result = skill(force=force)
        for item in result["results"]:
            print(f"联网找资料助手 skill: {item['status']} {item['path']}")
        return True
    if command == "check-update":
        print("检查底层 Agent-Reach 的更新；联网找资料助手自身通过本地发布包更新。")
    # The patch lives only for this invocation. The legacy entry point remains available.
    from .settings import child_env
    with patch.object(sys, "argv", ["agent-reach", command, *args]), patch.object(cli, "_install_skill", install_reachkit_skill), patch.dict(os.environ, {"PATH": child_env()["PATH"]}):
        cli.main()
    return 0


def transcribe(args):
    import argparse
    from urllib.parse import urlsplit
    parser = argparse.ArgumentParser(prog="reachkit transcribe")
    parser.add_argument("source")
    parser.add_argument("--provider", choices=["auto", "groq", "openai"], default="auto")
    parser.add_argument("--allow-provider-fallback", action="store_true")
    parser.add_argument("--polish", action="store_true", help="小宇宙播客补标点和分段")
    parser.add_argument("-o", "--output")
    parsed = parser.parse_args(args)
    host = (urlsplit(parsed.source).hostname or "").lower()
    if host == "xiaoyuzhoufm.com" or host.endswith(".xiaoyuzhoufm.com"):
        if parsed.provider == "openai" or parsed.allow_provider_fallback:
            raise ReachError("小宇宙专用脚本使用 Groq；通用本地音频转写可选择 OpenAI。")
        script = Path.home() / ".agent-reach/tools/xiaoyuzhou/transcribe.sh"
        if not script.is_file():
            raise ReachError("先运行 reachkit install --system --channels=xiaoyuzhou 安装播客脚本。")
        from .settings import child_env, bash_path
        import subprocess
        env = child_env()
        bash = bash_path(env)
        def shell_path(path):
            path = Path(path).resolve().as_posix()
            if os.name == "nt" and len(path) > 2 and path[1] == ":":
                return "/" + path[0].lower() + path[2:]
            return path
        command = [bash, shell_path(script), *( ["--polish"] if parsed.polish else []), parsed.source]
        if parsed.output:
            command.append(shell_path(parsed.output))
        try:
            result = subprocess.run(command, env=env, timeout=1800)
        except subprocess.TimeoutExpired:
            raise ReachError("播客转录超过 30 分钟，停止调用；请检查网络和供应商状态。") from None
        except OSError:
            raise ReachError("无法启动播客转录脚本，请检查 Bash 和安装路径。") from None
        return result.returncode
    if parsed.polish:
        raise ReachError("--polish 用于小宇宙播客；普通音频使用 transcribe。")
    return delegate("transcribe", args)
