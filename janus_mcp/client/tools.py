"""Sandbox 工具高层封装。"""

import json
from typing import Any, Dict, List, Optional

from janus_mcp.client.session import MCPSession


class SandboxTools:
    def __init__(self, session: MCPSession):
        self._session = session

    async def execute_code(self, code: str, session_id: Optional[str] = None, timeout: Optional[int] = None) -> Dict:
        args = {"code": code}
        if session_id:
            args["session_id"] = session_id
        if timeout:
            args["timeout"] = timeout
        result = await self._session.call_tool("execute_code", args)
        return self._parse_result(result)

    async def browser_navigate(self, url: str, wait_until: str = "load") -> Dict:
        result = await self._session.call_tool("browser_navigate", {"url": url, "wait_until": wait_until})
        return self._parse_result(result)

    async def browser_get_content(self) -> Dict:
        result = await self._session.call_tool("browser_get_content", {})
        return self._parse_result(result)

    async def note_create(self, title: str, content: str, tags: Optional[List[str]] = None) -> Dict:
        args = {"title": title, "content": content}
        if tags:
            args["tags"] = tags
        result = await self._session.call_tool("note_create", args)
        return self._parse_result(result)

    async def note_search(self, query: str, limit: int = 20) -> Dict:
        result = await self._session.call_tool("note_search", {"query": query, "limit": limit})
        return self._parse_result(result)

    async def knowledge_search_cve(self, query: str, limit: int = 10) -> Dict:
        result = await self._session.call_tool("knowledge_search_cve", {"query": query, "limit": limit})
        return self._parse_result(result)

    @staticmethod
    def _parse_result(result: List[Dict]) -> Dict:
        text = "".join(item.get("text", "") for item in result if item.get("type") == "text")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}