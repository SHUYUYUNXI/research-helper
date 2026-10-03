"""Bounded HTTP requests with explicit errors and public URL validation."""

import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


class ReachError(Exception):
    """An error suitable for the command line, without credential values."""
    def __init__(self, message, kind="unknown"):
        super().__init__(message)
        self.kind = kind


def public_url(value, resolve=False):
    value = str(value).strip()
    if not value or re.search(r"[\s\\\x00-\x1f\x7f]", value):
        raise ReachError("链接不能为空，也不能包含空白或反斜杠。")
    if "://" not in value:
        value = "https://" + value
    try:
        url = urllib.parse.urlsplit(value)
        host = (url.hostname or "").lower().rstrip(".")
        port = url.port
    except ValueError:
        raise ReachError("链接格式错误。") from None
    if (url.scheme not in {"http", "https"} or not host
            or url.username is not None or url.password is not None
            or "%" in host or host == "localhost"
            or host.endswith((".localhost", ".local", ".internal", ".lan"))):
        raise ReachError("只接受不带账号密码的公开 HTTP(S) 链接。")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # Reject abbreviated / numeric IPv4 spellings too.
        try:
            address = ipaddress.ip_address(socket.inet_aton(host))
        except OSError:
            address = None
    if address and not address.is_global:
        raise ReachError("不能抓取本机或内网地址。")
    if not address and "." not in host:
        raise ReachError("不能抓取本机或内网地址。")
    if resolve:
        try:
            records = socket.getaddrinfo(host, port or (443 if url.scheme == "https" else 80), type=socket.SOCK_STREAM)
        except OSError:
            raise ReachError("无法解析目标域名，请检查网络或代理。") from None
        if not records or any(not ipaddress.ip_address(item[4][0]).is_global for item in records):
            raise ReachError("目标域名解析到了非公开地址。")
    return urllib.parse.urlunsplit((url.scheme, url.netloc, url.path, url.query, ""))


class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        newurl = public_url(newurl, resolve=True)
        source = urllib.parse.urlsplit(req.full_url)
        target = urllib.parse.urlsplit(newurl)
        sensitive = {"authorization", "x-api-key", "cookie"}
        if ((source.scheme, source.netloc) != (target.scheme, target.netloc)
                and any(key.lower() in sensitive for key in req.headers)):
            raise ReachError("带凭据的请求发生跨站重定向，已停止。")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass
class Response:
    url: str
    text: str
    content_type: str
    body: bytes


class HTTP:
    def __init__(self, timeout=25, max_bytes=5 * 1024 * 1024):
        self.timeout = timeout
        self.max_bytes = max_bytes
        from .settings import child_env
        env = child_env()
        proxies = {scheme: env.get(scheme.upper() + "_PROXY") or env.get(scheme + "_proxy") for scheme in ("http", "https")}
        proxy_handler = urllib.request.ProxyHandler({key: value for key, value in proxies.items() if value}) if any(proxies.values()) else urllib.request.ProxyHandler()
        self.opener = urllib.request.build_opener(proxy_handler, PublicRedirect())

    def get(self, url, headers=None, data=None):
        url = public_url(url, resolve=True)
        request_headers = {"User-Agent": "ReachKit/0.2 (+public-source-reader)", "Accept": "*/*"}
        request_headers.update(headers or {})
        request = urllib.request.Request(url, headers=request_headers, data=data)
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                body = response.read(self.max_bytes + 1)
                if len(body) > self.max_bytes:
                    raise ReachError("响应超过 5 MB，已停止读取。")
                charset = response.headers.get_content_charset() or "utf-8"
                try:
                    text = body.decode(charset, errors="replace")
                except LookupError:
                    text = body.decode("utf-8", errors="replace")
                return Response(response.geturl(), text, response.headers.get_content_type(), body)
        except urllib.error.HTTPError as error:
            messages = {401: "需要认证", 403: "被平台拒绝或需要登录", 404: "内容不存在", 429: "请求过于频繁"}
            kind = "auth" if error.code in (401, 403) else "rate_limit" if error.code == 429 else "not_found" if error.code == 404 else "network" if error.code >= 500 else "unknown"
            raise ReachError(f"HTTP {error.code}：{messages.get(error.code, '平台请求失败')}。", kind) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ReachError("网络请求失败或超时，请检查网络、代理或稍后重试。", "network") from None

    def json(self, url, headers=None, payload=None):
        if payload is not None:
            headers = {**(headers or {}), "Content-Type": "application/json"}
        response = self.get(url, headers, json.dumps(payload).encode("utf-8") if payload is not None else None)
        try:
            return json.loads(response.text)
        except ValueError:
            raise ReachError("平台返回的不是有效 JSON，可能遇到了验证页面。") from None
