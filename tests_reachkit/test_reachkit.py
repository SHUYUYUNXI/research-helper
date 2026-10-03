import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reachkit.core import collect, doctor, export, read, search
from reachkit.network import HTTP, ReachError, Response, public_url
from reachkit.parsers import page_text, parse_feed, subtitle_text
from reachkit.providers import route


class FakeHTTP:
    def __init__(self, text="", kind="text/html", values=None):
        self.text, self.kind, self.values = text, kind, values or {}
        self.requests = []

    def get(self, url, headers=None, data=None):
        self.requests.append(url)
        return Response(url, self.text, self.kind, self.text.encode("utf-8"))

    def json(self, url, headers=None, payload=None):
        self.requests.append((url, payload))
        value = self.values.get(url)
        if isinstance(value, Exception):
            raise value
        return value


class SourcesTest(unittest.TestCase):
    def test_url_boundary(self):
        for url in ("file:///etc/passwd", "http://127.0.0.1/", "http://127.1/", "http://2130706433/", "http://[::1]/", "http://localhost/", "https://name:pass@example.com", "https://example.com\\@localhost"):
            with self.subTest(url=url), self.assertRaises(ReachError):
                public_url(url)
        self.assertEqual(public_url("example.com/a#fragment"), "https://example.com/a")

    def test_domain_spoof_is_not_routed(self):
        self.assertEqual(route("https://github.com.evil.example/x/y"), "web")
        self.assertEqual(route("https://gitee.com.evil.example/x/y"), "web")
        self.assertEqual(route("https://sspai.com/post/1"), "sspai")

    def test_article_omits_navigation_script_and_recommendations(self):
        source = '<title>标题</title><nav>导航</nav><div id="content_views"><p>正文 A</p><script>bad()</script><p>正文 B</p></div><p>推荐广告</p>'
        title, text = page_text(source, target_id="content_views")
        self.assertEqual(title, "标题")
        self.assertIn("正文 B", text)
        for unwanted in ("bad", "推荐广告", "导航"):
            self.assertNotIn(unwanted, text)

    def test_atom_namespace_relative_url_and_full_content(self):
        source = '<feed xmlns="http://www.w3.org/2005/Atom" xml:base="https://example.com/blog/"><title>源</title><entry><title>文章</title><link href="one"/><content type="html">&lt;p&gt;正文&lt;/p&gt;</content><updated>2026-10-03</updated></entry></feed>'
        title, entries = parse_feed(source, "https://example.com/feed")
        self.assertEqual(title, "源")
        self.assertEqual(entries[0]["url"], "https://example.com/blog/one")
        self.assertEqual(entries[0]["text"], "正文")

    def test_feed_encoded_content_preferred(self):
        source = '<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>T</title><item><title>X</title><description>短摘要</description><content:encoded><![CDATA[<p>完整正文</p>]]></content:encoded></item></channel></rss>'
        self.assertEqual(parse_feed(source, "https://example.com")[1][0]["text"], "完整正文")

    def test_feed_rejects_dtd_and_empty_feed(self):
        for source in ('<!DOCTYPE x [<!ENTITY a "x">]><rss/>', '<rss><channel/></rss>', '<html/>'):
            with self.assertRaises(ReachError):
                parse_feed(source, "https://example.com")

    def test_subtitle_repeated_rolling_captions(self):
        source = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhello\nhello\nhello world\n\n00:00:02.000 --> 00:00:03.000\nsecond line"
        self.assertEqual(subtitle_text(source), "hello world\nsecond line")

    def test_empty_and_challenge_pages_fail(self):
        for source in ('<html><script>only script</script></html>', '<title>Just a moment...</title><body>Verify</body>'):
            with self.assertRaises(ReachError):
                read("https://example.com", http=FakeHTTP(source))

    def test_csdn_content_selector(self):
        data = read("https://blog.csdn.net/name/article/details/123", http=FakeHTTP('<title>T</title><div id="content_views">文章正文</div><div>推荐</div>'))
        self.assertEqual(data["platform"], "csdn")
        self.assertEqual(data["text"], "文章正文")
        self.assertIn("fetched_at", data)

    def test_gitee_readme_decode(self):
        api = "https://gitee.com/api/v5/repos/a/b"
        http = FakeHTTP(values={api: {"full_name": "a/b", "html_url": "https://gitee.com/a/b"}, api + "/readme": {"encoding": "base64", "content": base64.b64encode("# 文档".encode()).decode()}})
        self.assertEqual(read("https://gitee.com/a/b", http=http)["text"], "# 文档")

    def test_baidu_hotlist_structure(self):
        payload = {"data": {"cards": [{"component": "hotList", "content": [{"word": "热点", "url": "https://www.baidu.com/s?wd=x", "hotScore": "100"}]}]}}
        data = read("https://top.baidu.com", http=FakeHTTP("<!--s-data:" + json.dumps(payload) + "-->"))
        self.assertEqual(data["items"][0]["title"], "热点")
        with self.assertRaises(ReachError):
            read("https://top.baidu.com", http=FakeHTTP("<title>empty</title>"))

    def test_juejin_feed_and_api_rejection(self):
        api = "https://api.juejin.cn/recommend_api/v1/article/recommend_all_feed"
        values = {api: {"err_no": 0, "data": [{"item_info": {"article_info": {"article_id": "123", "title": "文章", "brief_content": "摘要"}}}]}}
        self.assertEqual(read("https://juejin.cn", http=FakeHTTP(values=values))["items"][0]["url"], "https://juejin.cn/post/123")
        values[api] = {"err_no": 2, "data": None}
        with self.assertRaises(ReachError):
            read("https://juejin.cn", http=FakeHTTP(values=values))

    def test_platform_mismatch(self):
        with self.assertRaises(ReachError):
            read("https://example.com/a/b", platform="gitee", http=FakeHTTP())

    def test_batch_deduplicates_and_keeps_success_on_failure(self):
        http = FakeHTTP("<article>正文</article>")
        data = collect(["https://example.com/a", "https://example.com/a#fragment", "http://127.0.0.1"], http=http)
        self.assertEqual(data["summary"], {"succeeded": 1, "failed": 1, "total": 2})
        self.assertFalse(data["ok"])
        self.assertEqual(len(http.requests), 1)

    def test_malformed_platform_json_becomes_error(self):
        with self.assertRaises(ReachError):
            read("https://gitee.com/a/b", http=FakeHTTP())

    def test_export_keeps_sources_and_does_not_overwrite(self):
        data = read("https://example.com", http=FakeHTTP("<article>正文</article>"))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "sources.md"
            export(data, target, "md")
            content = target.read_text(encoding="utf-8")
            self.assertIn("https://example.com", content)
            self.assertIn("正文", content)
            with self.assertRaises(ReachError):
                export(data, target, "md")
            self.assertEqual(target.read_text(encoding="utf-8"), content)

    def test_doctor_does_not_send_requests_without_live(self):
        http = FakeHTTP()
        with patch("reachkit.catalog.tool_path", return_value=None), patch.dict("os.environ", {}, clear=True):
            data = doctor(http=http)
        self.assertFalse(http.requests)
        self.assertFalse(any(item["status"] == "verified" for item in data["channels"]))

    def test_blank_search_and_empty_results_fail(self):
        with self.assertRaises(ReachError):
            search(" ")
        with self.assertRaises(ReachError):
            search("none", platform="github", http=FakeHTTP(values={"https://api.github.com/search/repositories?q=none&per_page=10&sort=stars": {"items": []}}))


if __name__ == "__main__":
    unittest.main()

