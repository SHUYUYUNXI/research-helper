import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from reachkit import core, lifecycle, mcp_server, runtime, settings
from reachkit.catalog import capabilities
from reachkit.network import ReachError


class Config:
    def __init__(self, **data):
        self.data = data
    def get(self, key):
        return self.data.get(key)


class IntegratedTest(unittest.TestCase):
    def test_bash_discovery_rejects_wsl_stub_and_uses_gnu(self):
        with patch("reachkit.settings.tool_path", return_value="bash"), patch("reachkit.settings.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="WSL launcher")):
            with self.assertRaises(ReachError):
                settings.bash_path({"PATH": "x"})
        with patch("reachkit.settings.tool_path", return_value="bash"), patch("reachkit.settings.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="GNU bash version 5")):
            self.assertTrue(settings.bash_path({"PATH": "x"}))

    def test_bash_discovery_handles_timeout(self):
        import subprocess
        with patch("reachkit.settings.tool_path", return_value="bash"), patch("reachkit.settings.subprocess.run", side_effect=subprocess.TimeoutExpired("bash", 5)):
            with self.assertRaises(ReachError):
                settings.bash_path({"PATH": "x"})

    def test_boss_search_requires_known_browser_login(self):
        for cookie in (None, False):
            with self.subTest(cookie=cookie), patch("agent_reach.channels.boss.BossChannel") as channel:
                channel.return_value.active_backend = "boss-agent-cli (CDP)"
                channel.return_value.browser_login_cookie = cookie
                with self.assertRaises(ReachError):
                    runtime.platform_args("boss", "search", "Python", "boss-cdp")
        with patch("agent_reach.channels.boss.BossChannel") as channel:
            channel.return_value.active_backend = "boss-agent-cli (CDP)"
            channel.return_value.browser_login_cookie = True
            command, args = runtime.platform_args("boss", "search", "Python", "boss-cdp")
            self.assertEqual(command, "boss")
            self.assertEqual(args[args.index("--browser-source")+1], "existing-browser")

    def test_fallback_preserves_failure_and_selected_backend(self):
        with patch("reachkit.settings.settings", return_value=Config()), patch("reachkit.core._dispatch", side_effect=[ReachError("工具损坏"), {"platform": "bilibili", "backend": "direct", "text": "视频介绍"}]) as dispatch:
            data = core.read("https://www.bilibili.com/video/BV1GJ411x7h7")
        self.assertEqual(dispatch.call_count, 2)
        self.assertEqual(data["backend"], "direct")
        self.assertEqual([item["ok"] for item in data["attempts"]], [False, True])

    def test_rate_limit_does_not_retry_another_backend(self):
        with patch("reachkit.settings.settings", return_value=Config()), patch("reachkit.core._dispatch", side_effect=ReachError("限流", "rate_limit")) as dispatch:
            with self.assertRaises(ReachError):
                core.search("test", "bilibili")
        self.assertEqual(dispatch.call_count, 1)

    def test_override_and_explicit_backend_do_not_retry(self):
        with patch("reachkit.settings.settings", return_value=Config(bilibili_backend="OpenCLI")), patch("reachkit.core._dispatch", return_value={"backend": "opencli", "text": "内容"}) as dispatch:
            core.search("test", "bilibili")
            self.assertEqual(dispatch.call_args.args[3], "opencli")
        with patch("reachkit.settings.settings", return_value=Config()), patch("reachkit.core._dispatch", side_effect=ReachError("失败")) as dispatch:
            with self.assertRaises(ReachError):
                core.search("test", "bilibili", backend="direct")
            self.assertEqual(dispatch.call_count, 1)

    def test_research_keeps_partial_sources(self):
        with patch("reachkit.core.search", side_effect=[{"ok": True, "platform": "github", "url": "https://github.com/a/b"}, ReachError("未登录")]):
            data = core.research("测试", ["github", "reddit", "github"])
        self.assertEqual(data["summary"], {"succeeded": 1, "failed": 1, "total": 2})
        self.assertEqual(data["results"][1]["platform"], "reddit")

    def test_env_uses_saved_config_and_preserves_existing_env(self):
        with patch.dict(os.environ, {"GH_TOKEN": "existing-token", "HTTP_PROXY": "http://existing:123"}, clear=True):
            env = settings.child_env(Config(github_token="saved-token", twitter_auth_token="saved-auth", twitter_ct0="saved-ct0", proxy="http://saved:123"))
            self.assertEqual(env["GH_TOKEN"], "existing-token")
            self.assertEqual(env["HTTP_PROXY"], "http://existing:123")
            self.assertEqual(env["HTTPS_PROXY"], "http://saved:123")
            self.assertEqual(env["TWITTER_AUTH_TOKEN"], "saved-auth")
            self.assertNotIn("TWITTER_AUTH_TOKEN", os.environ)

    def test_ytdlp_cookie_source_is_explicit_and_validated(self):
        with patch("shutil.which", return_value=None):
            self.assertEqual(settings.ytdlp_options(Config()), [])
            self.assertEqual(settings.ytdlp_options(Config(youtube_cookies_from="chrome:Profile 2")), ["--cookies-from-browser", "chrome:Profile 2"])
            with self.assertRaises(ReachError):
                settings.ytdlp_options(Config(youtube_cookies_from="--exec something"))

    def test_social_url_routes_and_signed_note_requirement(self):
        from reachkit.providers import route
        self.assertEqual(route("https://www.xiaohongshu.com/explore/123?xsec_token=abc"), "xiaohongshu")
        self.assertEqual(route("https://www.reddit.com/r/python/comments/abc/name"), "reddit")
        with self.assertRaises(ReachError):
            runtime.platform_args("xiaohongshu", "read", "https://www.xiaohongshu.com/explore/123", "opencli")
        command, args = runtime.platform_args("reddit", "read", "https://www.reddit.com/r/python/comments/abc/name", "opencli")
        self.assertEqual(args[:3], ["reddit", "read", "abc"])
        self.assertEqual(command, "opencli")

    def test_tool_rejects_writes_and_configuration_commands(self):
        for command, args in (("gh", ["issue", "create", "--title", "x"]), ("opencli", ["twitter", "post", "x"]), ("rdt", ["login"]), ("bili", ["login"])):
            with self.subTest(command=command), self.assertRaises(ReachError):
                runtime.advanced_tool(command, args)
        with patch("agent_reach.channels.reddit.RedditChannel._check_rdt", return_value=("warn", "没有可用的显式 Cookie")), patch("reachkit.runtime.command_output") as command:
            with self.assertRaises(ReachError):
                runtime.advanced_tool("rdt", ["popular"])
            command.assert_not_called()
        with patch("reachkit.runtime.command_output", return_value="code result"):
            self.assertTrue(runtime.advanced_tool("gh", ["search", "code", "query"])["ok"])

    def test_command_rejects_mcp_nested_business_errors(self):
        def fake_run(argv, stdout, stderr, **kwargs):
            stdout.write(json.dumps({"content": [{"text": '{"ok": false, "error": "bad"}'}]}).encode())
            return SimpleNamespace(returncode=0)
        with patch("shutil.which", return_value="tool"), patch("reachkit.runtime.subprocess.run", side_effect=fake_run):
            with self.assertRaises(ReachError):
                runtime.command_output("tool", [], env={"PATH": "x"})

    def test_command_does_not_echo_stderr_credentials(self):
        def fake_run(argv, stdout, stderr, **kwargs):
            stderr.write(b"secret-value")
            return SimpleNamespace(returncode=1)
        with patch("shutil.which", return_value="tool"), patch("reachkit.runtime.subprocess.run", side_effect=fake_run):
            with self.assertRaises(ReachError) as error:
                runtime.command_output("tool", [], env={"PATH": "x"})
            self.assertNotIn("secret-value", str(error.exception))

    def test_skill_install_preserve_update_and_scoped_uninstall(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installed = lifecycle.skill(path=root)
            target = root / "reachkit"
            self.assertEqual(installed["results"][0]["status"], "installed")
            self.assertTrue((target / "references/chinese.md").is_file())
            self.assertIn("name: reachkit", (target / "SKILL.md").read_text(encoding="utf-8"))
            self.assertEqual(lifecycle.skill(path=root)["results"][0]["status"], "preserved")
            (target / "custom.txt").write_text("keep")
            lifecycle.skill(path=root, lang="en", force=True)
            self.assertIn("# 联网找资料助手", (target / "SKILL.md").read_text(encoding="utf-8"))
            lifecycle.skill(install=False, path=root)
            self.assertFalse((target / "SKILL.md").exists())
            self.assertEqual((target / "custom.txt").read_text(), "keep")

    def test_one_catalog_covers_all_sources_without_invented_search(self):
        items = {item["platform"]: item for item in capabilities()["channels"]}
        self.assertEqual(len(items), 25)
        self.assertFalse(items["gitee"]["search"])
        self.assertEqual(items["instagram"]["search_scope"], "用户搜索")
        self.assertTrue(items["xiaoyuzhou"]["transcribe"])

    def test_xhs_login_negative_text_and_nonzero_exit_are_not_success(self):
        from agent_reach.cli import _xhs_login_verified
        for text in ("not logged in", "logged out", "未登录", '{"logged_in": false}', '{"isError": true, "content": [{"text": "已登录"}]}'):
            self.assertFalse(_xhs_login_verified(SimpleNamespace(returncode=0, stdout=text)))
        self.assertFalse(_xhs_login_verified(SimpleNamespace(returncode=1, stdout="已登录")))
        self.assertTrue(_xhs_login_verified(SimpleNamespace(returncode=0, stdout='{"logged_in": true}')))

    def test_xhs_cleaning_keeps_search_link_and_wrapper_signature(self):
        from agent_reach.channels.xiaohongshu import format_xhs_result
        signed = "https://www.xiaohongshu.com/explore/abc?xsec_token=signed-value"
        row = format_xhs_result({"id": "abc", "xsec_token": "signed-value", "note_card": {"title": "测试"}, "url": signed})
        self.assertEqual(row["url"], signed)
        self.assertEqual(row["id"], "abc")
        self.assertEqual(row["xsec_token"], "signed-value")
        row = format_xhs_result({"id": "abc", "xsec_token": "signed-value", "note_card": {"title": "测试"}})
        self.assertIn("xsec_token=signed-value", row["url"])

    def test_xhs_bridge_keeps_signed_sources_and_caps_items(self):
        signed = "https://www.xiaohongshu.com/explore/abc?xsec_token=signed-value"
        body = json.dumps([{"title": "结果", "url": signed}]*4)
        with patch("agent_reach.backends.opencli.opencli_status", return_value=SimpleNamespace(ready=True)), patch("reachkit.runtime.command_output", return_value=body):
            result = runtime.bridge("xiaohongshu", "search", "关键词", "opencli", limit=2)
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["items"][0]["url"], signed)

    def test_outer_mcp_error_cannot_be_hidden_by_valid_inner_content(self):
        def fake_run(argv, stdout, stderr, **kwargs):
            stdout.write(json.dumps({"isError": True, "content": [{"text": '{"title": "looks valid"}'}]}).encode())
            return SimpleNamespace(returncode=0)
        with patch("shutil.which", return_value="tool"), patch("reachkit.runtime.subprocess.run", side_effect=fake_run):
            with self.assertRaises(ReachError):
                runtime.command_output("tool", [], env={"PATH": "x"})

    def test_gh_fallback_dispatches_issue_and_pr_as_the_right_resource(self):
        with patch("reachkit.runtime.command_output", return_value="正文") as command:
            core._dispatch("github", "read", "https://github.com/a/b/issues/12", "gh-cli", 2, None)
            self.assertEqual(command.call_args.args[1][:2], ["issue", "view"])
            core._dispatch("github", "read", "https://github.com/a/b/pull/12", "gh-cli", 2, None)
            self.assertEqual(command.call_args.args[1][:2], ["pr", "view"])

    def test_http_and_transcript_requests_use_saved_proxy(self):
        from reachkit.network import HTTP
        from agent_reach.transcribe import transcribe_chunk
        with patch("reachkit.settings.child_env", return_value={"HTTP_PROXY": "http://localhost:123", "HTTPS_PROXY": "http://localhost:123"}), patch("reachkit.network.urllib.request.ProxyHandler") as proxy, patch("reachkit.network.urllib.request.build_opener"):
            HTTP()
            proxy.assert_called_once_with({"http": "http://localhost:123", "https": "http://localhost:123"})
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory)/"audio.m4a"
            audio.write_bytes(b"audio")
            with patch("reachkit.settings.child_env", return_value={"HTTP_PROXY": "http://localhost:123", "HTTPS_PROXY": "http://localhost:123"}), patch("agent_reach.transcribe.requests.post", return_value=SimpleNamespace(ok=True, text="文字")) as post:
                self.assertEqual(transcribe_chunk(audio, "groq", config=Config(groq_api_key="mock-key", proxy="http://localhost:123")), "文字")
                self.assertEqual(post.call_args.kwargs["proxies"]["https"], "http://localhost:123")

    def test_upstream_diagnostics_keep_native_readiness_and_normalize_external_state(self):
        result = {"twitter": {"status": "ok", "message": "后端就绪", "active_backend": "OpenCLI"}, "github": {"status": "off", "message": "无 gh", "active_backend": None}}
        with patch("reachkit.catalog.local_status", return_value=("ready_local", "本地入口", [])), patch("agent_reach.doctor.check_all", return_value=result), patch("reachkit.settings.settings", return_value=Config()):
            items = {item["platform"]: item for item in core.doctor(upstream=True)["channels"]}
        self.assertEqual(items["twitter"]["status"], "backend_checked")
        self.assertIsNone(items["twitter"]["verified_at"])
        self.assertEqual(items["github"]["status"], "ready_local")
        self.assertEqual(items["github"]["upstream_probe"]["status"], "off")

    def test_mcp_tools_route_to_actual_core_and_validate_bounds(self):
        class Server:
            def __init__(self, name):
                pass
            def list_tools(self):
                return lambda fn: setattr(self, "list_handler", fn) or fn
            def call_tool(self):
                return lambda fn: setattr(self, "call_handler", fn) or fn
        with patch.multiple(mcp_server, HAS_MCP=True, Server=Server, Tool=lambda **kw: SimpleNamespace(**kw), TextContent=lambda **kw: SimpleNamespace(**kw), create=True):
            server = mcp_server.create_server()
            tools = asyncio.run(server.list_handler())
            self.assertEqual(len(tools), 6)
            with patch("reachkit.mcp_server.core.read", return_value={"ok": True, "text": "正文"}) as read:
                response = asyncio.run(server.call_handler("read_source", {"url": "https://example.com", "limit": 2}))
                self.assertTrue(json.loads(response[0].text)["ok"])
                read.assert_called_once_with("https://example.com", limit=2)
            response = asyncio.run(server.call_handler("read_source", {"url": "https://example.com", "limit": 100}))
            self.assertFalse(json.loads(response[0].text)["ok"])


if __name__ == "__main__":
    unittest.main()

