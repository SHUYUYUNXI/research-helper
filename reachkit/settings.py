"""Reuse explicit upstream configuration in actual child processes and HTTP."""
import os
import re
import sys
import subprocess
from pathlib import Path

from agent_reach.config import Config
from .network import ReachError


def settings():
    try:
        return Config(read_only=True)
    except (OSError, ValueError, RuntimeError):
        raise ReachError("无法读取工具配置，请检查 ~/.agent-reach/config.yaml。") from None


def child_env(config=None):
    config = config if config is not None else settings()
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    env["REACHKIT_PYTHON"] = sys.executable
    # Absolute-Python MCP launches and Windows scripts need their own venv CLIs.
    executable_dir = os.path.dirname(sys.executable)
    env["PATH"] = os.pathsep.join([executable_dir, os.path.join(executable_dir, "Scripts"), env.get("PATH", "")])
    for key, field in (("GH_TOKEN", "github_token"), ("TWITTER_AUTH_TOKEN", "twitter_auth_token"),
                       ("TWITTER_CT0", "twitter_ct0"), ("GROQ_API_KEY", "groq_api_key"),
                       ("OPENAI_API_KEY", "openai_api_key")):
        if key == "GH_TOKEN" and env.get("GITHUB_TOKEN"):
            continue
        if not env.get(key) and config.get(field):
            env[key] = str(config.get(field))
    proxy = config.get("proxy")
    if proxy:
        for key in ("HTTP_PROXY", "HTTPS_PROXY"):
            if not env.get(key) and not env.get(key.lower()):
                env[key] = str(proxy)
    return env


def tool_path(command, env=None):
    import shutil
    return shutil.which(command, path=(env or child_env()).get("PATH", ""))


def bash_path(env=None):
    """Find an executable GNU Bash, including Git Bash on Windows."""
    env = env if env is not None else child_env()
    candidates = []
    if os.name == "nt":
        for key in ("ProgramFiles", "PROGRAMFILES", "PROGRAMFILES(X86)"):
            if env.get(key):
                candidates.append(str(Path(env[key]) / "Git/bin/bash.exe"))
        candidates.append("C:/Program Files/Git/bin/bash.exe")
    discovered = tool_path("bash", env)
    if discovered:
        candidates.append(discovered)
    for candidate in dict.fromkeys(candidates):
        try:
            probe = subprocess.run([candidate, "--version"], env=env,
                                   capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if probe.returncode == 0 and "GNU bash" in probe.stdout:
            return candidate
    raise ReachError("播客脚本需要 GNU Bash，Windows 可使用 Git Bash。")


def ytdlp_options(config=None):
    config = config if config is not None else settings()
    args = []
    browser = config.get("youtube_cookies_from")
    if browser:
        # yt-dlp supports browser[:profile]; configuration is explicit opt-in.
        if not re.fullmatch(r"(?:chrome|chromium|edge|brave|firefox|opera|safari|vivaldi)(?::[^\r\n]+)?", str(browser)):
            raise ReachError("YouTube Cookie 来源无效，请配置浏览器名或 浏览器:profile。")
        args += ["--cookies-from-browser", str(browser)]
    import shutil
    if shutil.which("deno"):
        args += ["--js-runtimes", "deno"]
    elif shutil.which("node"):
        args += ["--js-runtimes", "node"]
    return args
