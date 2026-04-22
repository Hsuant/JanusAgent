"""笔记管理 MCP 工具。"""

from typing import Any, Dict, List, Optional

from fastmcp import FastMCP

from janus_mcp.servers.sandbox.managers.note_manager import NoteManager


def register_note_tools(mcp: FastMCP, note_manager: NoteManager) -> None:
    """注册笔记工具。"""

    @mcp.tool()
    async def note_create(title: str, content: str, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        note = note_manager.create_note(title, content, tags)
        return note.to_dict()

    @mcp.tool()
    async def note_get(note_id: str) -> Dict[str, Any]:
        note = note_manager.get_note(note_id)
        return note.to_dict() if note else {"error": "not found"}

    @mcp.tool()
    async def note_update(note_id: str, title: Optional[str] = None, content: Optional[str] = None,
                          tags: Optional[List[str]] = None) -> Dict[str, Any]:
        note = note_manager.update_note(note_id, title, content, tags)
        return note.to_dict() if note else {"error": "not found"}

    @mcp.tool()
    async def note_delete(note_id: str) -> Dict[str, Any]:
        success = note_manager.delete_note(note_id)
        return {"success": success}

    @mcp.tool()
    async def note_list(limit: int = 50, offset: int = 0, tag_filter: Optional[str] = None) -> Dict[str, Any]:
        notes = note_manager.list_notes(limit, offset, tag_filter)
        return {"notes": notes, "count": len(notes)}

    @mcp.tool()
    async def note_search(query: str, limit: int = 20) -> Dict[str, Any]:
        results = note_manager.search_notes(query, limit)
        return {"results": results, "count": len(results), "query": query}

    @mcp.tool()
    async def note_append(note_id: str, content: str) -> Dict[str, Any]:
        note = note_manager.append_content(note_id, content)
        return note.to_dict() if note else {"error": "not found"}