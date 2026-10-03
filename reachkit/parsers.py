"""Text extraction, RSS/Atom parsing and subtitle cleanup."""

import html
import re
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

from .network import ReachError


class PageParser(HTMLParser):
    OMIT = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form"}
    BLOCK = {"p", "div", "br", "li", "section", "article", "main", "h1", "h2", "h3", "h4", "pre", "tr"}
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, target_id=None, target_class=None):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.title_parts = []
        self.parts = []
        self.main_parts = []
        self.target_id = target_id
        self.target_class = target_class
        self.target_depth = None
        self.target_parts = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)
            attributes = dict(attrs)
            if ((self.target_id and attributes.get("id") == self.target_id)
                    or (self.target_class and self.target_class in attributes.get("class", "").split())):
                self.target_depth = len(self.stack)
        if tag in self.BLOCK:
            self._text("\n")

    def handle_startendtag(self, tag, attrs):
        if tag in self.BLOCK:
            self._text("\n")

    def handle_endtag(self, tag):
        if tag in self.BLOCK:
            self._text("\n")
        if tag in self.stack:
            index = len(self.stack) - 1 - self.stack[::-1].index(tag)
            del self.stack[index:]
            if self.target_depth is not None and len(self.stack) < self.target_depth:
                self.target_depth = None

    def _text(self, value):
        if any(tag in self.OMIT for tag in self.stack) or "head" in self.stack:
            return
        self.parts.append(value)
        if self.target_depth is not None:
            self.target_parts.append(value)
        if "main" in self.stack or "article" in self.stack:
            self.main_parts.append(value)

    def handle_data(self, data):
        if "title" in self.stack:
            self.title_parts.append(data)
        else:
            self._text(data)


def clean_text(text):
    text = html.unescape(text).replace("\r", "")
    text = re.sub(r"[^\S\n]+", " ", text)
    return re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text).strip()


def page_text(source, target_id=None, target_class=None):
    parser = PageParser(target_id, target_class)
    parser.feed(source)
    if target_id or target_class:
        return clean_text("".join(parser.title_parts)), clean_text("".join(parser.target_parts))
    main = clean_text("".join(parser.main_parts))
    return clean_text("".join(parser.title_parts)), main or clean_text("".join(parser.parts))


def local_name(tag):
    return tag.split("}")[-1].lower()


def child_text(element, *names):
    for name in names:
        for child in element:
            if local_name(child.tag) == name:
                return "".join(child.itertext()).strip()
    return ""


def parse_feed(source, base_url, limit=10):
    # Parse bytes to honor XML encoding declarations. Reject DTDs/entity expansion.
    scan = source.decode("utf-8", "ignore").replace("\x00", "") if isinstance(source, bytes) else source
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", scan, re.I):
        raise ReachError("不支持带 DTD 或实体声明的订阅源。")
    try:
        root = ET.fromstring(source)
    except ET.ParseError:
        raise ReachError("不是有效的 RSS/Atom XML。") from None
    if local_name(root.tag) not in {"rss", "feed", "rdf"}:
        raise ReachError("链接返回的不是 RSS/Atom 订阅源。")
    channel = next((child for child in root if local_name(child.tag) == "channel"), root)
    title = child_text(channel, "title")
    entries = []
    xml_base = "{http://www.w3.org/XML/1998/namespace}base"
    root_base = urllib.parse.urljoin(base_url, root.get(xml_base, ""))
    for item in root.iter():
        if local_name(item.tag) not in {"item", "entry"}:
            continue
        item_base = urllib.parse.urljoin(root_base, item.get(xml_base, ""))
        link = child_text(item, "link")
        for child in item:
            if local_name(child.tag) == "link" and child.get("rel", "alternate") == "alternate" and child.get("href"):
                link = urllib.parse.urljoin(item_base, child.get("href"))
                break
        link = urllib.parse.urljoin(item_base, link) if link else ""
        raw = child_text(item, "encoded", "content", "description", "summary")
        text = page_text(raw)[1] if "<" in raw else clean_text(raw)
        entries.append({"title": child_text(item, "title"), "url": link,
                        "published_at": child_text(item, "pubdate", "published", "updated", "date"),
                        "text": text})
        if len(entries) >= limit:
            break
    if not entries:
        raise ReachError("订阅源有效，但当前没有条目。")
    return title, entries


def subtitle_text(source):
    lines = []
    for line in source.splitlines():
        line = line.strip()
        if not line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")) or "-->" in line or line.isdigit():
            continue
        line = clean_text(re.sub(r"<[^>]*>", "", line))
        if not line:
            continue
        # yt-dlp auto captions can repeat or roll the preceding text forward.
        if lines and line == lines[-1]:
            continue
        if lines and line.startswith(lines[-1] + " "):
            lines[-1] = line
        else:
            lines.append(line)
    return "\n".join(lines)
