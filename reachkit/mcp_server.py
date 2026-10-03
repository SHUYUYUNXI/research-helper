"""Expose the integrated read/search/research capabilities through MCP stdio."""
import asyncio
import json

from . import core
from .catalog import capabilities, SEARCH_PLATFORMS
from .network import ReachError

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool
    HAS_MCP = True
except ImportError:
    HAS_MCP = False


def create_server():
    if not HAS_MCP:
        raise ReachError('MCP 需要安装可选依赖：python -m pip install ".[mcp]"。')
    server = Server("reachkit")
    lock = asyncio.Lock()
    limit = {"type": "integer", "minimum": 1, "maximum": 20, "default": 5}
    schemas = {
        "get_status": {"type": "object", "properties": {}},
        "list_capabilities": {"type": "object", "properties": {}},
        "read_source": {"type": "object", "properties": {"url": {"type": "string"}, "limit": limit}, "required": ["url"]},
        "search_sources": {"type": "object", "properties": {"query": {"type": "string"}, "platform": {"type": "string", "enum": list(SEARCH_PLATFORMS)}, "limit": limit}, "required": ["query", "platform"]},
        "research_topic": {"type": "object", "properties": {"query": {"type": "string"}, "platforms": {"type": "array", "minItems": 1, "maxItems": 8, "items": {"type": "string", "enum": list(SEARCH_PLATFORMS)}}, "limit": limit}, "required": ["query", "platforms"]},
        "collect_sources": {"type": "object", "properties": {"urls": {"type": "array", "minItems": 1, "maxItems": 50, "items": {"type": "string"}}, "limit": limit}, "required": ["urls"]},
    }

    @server.list_tools()
    async def list_tools():
        descriptions = {"get_status": "检查本地后端状态，不请求平台内容", "list_capabilities": "列出平台、操作、候选后端和指南", "read_source": "按 URL 路由读取来源内容", "search_sources": "在指定平台搜索", "research_topic": "跨平台研究并保留各平台成功和失败结果", "collect_sources": "批量读取、去重并保留来源"}
        return [Tool(name=name, description=descriptions[name], inputSchema={**schema, "additionalProperties": False}) for name, schema in schemas.items()]

    @server.call_tool()
    async def call_tool(name, arguments):
        try:
            if name not in schemas:
                raise ReachError("未知工具。")
            args = arguments or {}
            if not isinstance(args, dict) or set(args) - set(schemas[name]["properties"]):
                raise ReachError("工具参数无效。")
            if any(key not in args for key in schemas[name].get("required", [])):
                raise ReachError("缺少必填工具参数。")
            count = args.get("limit", 5)
            if type(count) is not int or not 1 <= count <= 20:
                raise ReachError("limit 必须在 1—20 之间。")
            for key in ("url", "query", "platform"):
                if key in args and (not isinstance(args[key], str) or not args[key].strip() or len(args[key]) > 8192):
                    raise ReachError("工具字符串参数无效。")
            for key, maximum in (("urls", 50), ("platforms", 8)):
                if key in args and (not isinstance(args[key], list) or not 1 <= len(args[key]) <= maximum or any(not isinstance(item, str) or len(item) > 8192 for item in args[key])):
                    raise ReachError("工具列表参数无效。")
            operations = {
                "get_status": lambda: core.doctor(), "list_capabilities": capabilities,
                "read_source": lambda: core.read(args["url"], limit=count),
                "search_sources": lambda: core.search(args["query"], args["platform"], count),
                "research_topic": lambda: core.research(args["query"], args["platforms"], count),
                "collect_sources": lambda: core.collect(args["urls"], limit=count),
            }
            async with lock:
                result = await asyncio.to_thread(operations[name])
        except ReachError as error:
            result = {"ok": False, "error": str(error)}
        except Exception:
            result = {"ok": False, "error": "工具调用失败，请检查平台状态和配置。"}
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    return server


async def serve():
    server = create_server()
    async with stdio_server() as (reader, writer):
        await server.run(reader, writer, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(serve())
