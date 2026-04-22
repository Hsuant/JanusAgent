"""知识库检索 MCP 工具。"""

from typing import Any, Dict, Optional

from fastmcp import FastMCP

from janus_mcp.servers.sandbox.managers.knowledge_manager import KnowledgeManager


def register_knowledge_tools(mcp: FastMCP, knowledge_manager: KnowledgeManager) -> None:
    """注册知识库工具。"""

    @mcp.tool()
    async def knowledge_search_cve(query: str, limit: int = 10,
                                   min_severity: Optional[str] = None) -> Dict[str, Any]:
        results = knowledge_manager.search_cve(query, limit, min_severity)
        return {"results": results, "count": len(results), "query": query}

    @mcp.tool()
    async def knowledge_get_cve(cve_id: str) -> Dict[str, Any]:
        cve = knowledge_manager.get_cve(cve_id)
        return cve if cve else {"error": "not found"}

    @mcp.tool()
    async def knowledge_search_product(product: str, version: Optional[str] = None) -> Dict[str, Any]:
        results = knowledge_manager.search_by_product(product, version)
        return {"results": results, "count": len(results)}