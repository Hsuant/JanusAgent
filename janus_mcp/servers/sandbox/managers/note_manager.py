"""笔记管理器。

提供笔记的创建、读取、更新、删除和搜索功能，
支持 Markdown 格式和元数据管理。
"""

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Note:
    """笔记数据类。

    Attributes:
        note_id: 笔记唯一标识符。
        title: 笔记标题。
        content: 笔记内容（Markdown 格式）。
        tags: 标签列表。
        created_at: 创建时间戳。
        updated_at: 更新时间戳。
        metadata: 额外元数据。
    """

    def __init__(
        self,
        note_id: Optional[str] = None,
        title: str = "",
        content: str = "",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """初始化笔记。

        Args:
            note_id: 笔记 ID，如果为 None 则自动生成。
            title: 标题。
            content: 内容。
            tags: 标签列表。
            metadata: 额外元数据。
        """
        self.note_id = note_id or self._generate_id()
        self.title = title
        self.content = content
        self.tags = tags or []
        self.created_at = time.time()
        self.updated_at = self.created_at
        self.metadata = metadata or {}

    def _generate_id(self) -> str:
        """生成笔记 ID。

        Returns:
            str: 基于时间戳和随机字符的 ID。
        """
        return f"{int(time.time())}_{uuid.uuid4().hex[:6]}"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式。

        Returns:
            Dict: 笔记的字典表示。
        """
        return {
            "note_id": self.note_id,
            "title": self.title,
            "content": self.content,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Note":
        """从字典创建笔记。

        Args:
            data: 笔记字典数据。

        Returns:
            Note: 笔记实例。
        """
        note = cls(
            note_id=data.get("note_id"),
            title=data.get("title", ""),
            content=data.get("content", ""),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )
        note.created_at = data.get("created_at", note.created_at)
        note.updated_at = data.get("updated_at", note.updated_at)
        return note


class NoteManager:
    """笔记管理器。

    管理笔记的持久化存储和检索。

    Attributes:
        storage_path: 笔记存储目录路径。
        _notes_cache: 笔记缓存字典，键为 note_id。
    """

    def __init__(self, storage_path: str = "/opt/notes") -> None:
        """初始化笔记管理器。

        Args:
            storage_path: 笔记存储目录路径。
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self._notes_cache: Dict[str, Note] = {}
        self._load_all_notes()

        logger.info("笔记管理器初始化完成，存储路径: %s", self.storage_path)

    def _get_note_path(self, note_id: str) -> Path:
        """获取笔记文件路径。

        Args:
            note_id: 笔记 ID。

        Returns:
            Path: 笔记文件路径。
        """
        return self.storage_path / f"{note_id}.json"

    def _save_note(self, note: Note) -> None:
        """保存笔记到文件。

        Args:
            note: 笔记实例。
        """
        file_path = self._get_note_path(note.note_id)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(note.to_dict(), f, ensure_ascii=False, indent=2)
        self._notes_cache[note.note_id] = note

    def _load_all_notes(self) -> None:
        """加载所有笔记到缓存。"""
        for file_path in self.storage_path.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    note = Note.from_dict(data)
                    self._notes_cache[note.note_id] = note
            except Exception as e:
                logger.warning("加载笔记 %s 失败: %s", file_path, e)

        logger.info("已加载 %d 条笔记", len(self._notes_cache))

    def create_note(
        self,
        title: str,
        content: str,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Note:
        """创建新笔记。

        Args:
            title: 笔记标题。
            content: 笔记内容。
            tags: 标签列表。
            metadata: 额外元数据。

        Returns:
            Note: 创建的笔记实例。
        """
        note = Note(
            title=title,
            content=content,
            tags=tags,
            metadata=metadata,
        )
        self._save_note(note)
        logger.info("已创建笔记: %s (ID: %s)", title, note.note_id)
        return note

    def get_note(self, note_id: str) -> Optional[Note]:
        """获取笔记。

        Args:
            note_id: 笔记 ID。

        Returns:
            Optional[Note]: 笔记实例，如果不存在则返回 None。
        """
        return self._notes_cache.get(note_id)

    def update_note(
        self,
        note_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Note]:
        """更新笔记。

        Args:
            note_id: 笔记 ID。
            title: 新标题，如果为 None 则不更新。
            content: 新内容，如果为 None 则不更新。
            tags: 新标签，如果为 None 则不更新。
            metadata: 新元数据，如果为 None 则不更新。

        Returns:
            Optional[Note]: 更新后的笔记，如果笔记不存在则返回 None。
        """
        note = self.get_note(note_id)
        if not note:
            logger.warning("笔记不存在: %s", note_id)
            return None

        if title is not None:
            note.title = title
        if content is not None:
            note.content = content
        if tags is not None:
            note.tags = tags
        if metadata is not None:
            note.metadata = metadata

        note.updated_at = time.time()
        self._save_note(note)
        logger.info("已更新笔记: %s", note_id)
        return note

    def delete_note(self, note_id: str) -> bool:
        """删除笔记。

        Args:
            note_id: 笔记 ID。

        Returns:
            bool: 是否成功删除。
        """
        if note_id not in self._notes_cache:
            return False

        file_path = self._get_note_path(note_id)
        try:
            file_path.unlink(missing_ok=True)
            del self._notes_cache[note_id]
            logger.info("已删除笔记: %s", note_id)
            return True
        except Exception as e:
            logger.error("删除笔记 %s 失败: %s", note_id, e)
            return False

    def list_notes(
        self,
        limit: int = 50,
        offset: int = 0,
        tag_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """列出笔记。

        Args:
            limit: 返回数量限制。
            offset: 偏移量。
            tag_filter: 标签过滤，只返回包含该标签的笔记。

        Returns:
            List[Dict]: 笔记摘要列表。
        """
        notes = list(self._notes_cache.values())
        notes.sort(key=lambda n: n.updated_at, reverse=True)

        if tag_filter:
            notes = [n for n in notes if tag_filter in n.tags]

        result = []
        for note in notes[offset:offset + limit]:
            result.append({
                "note_id": note.note_id,
                "title": note.title,
                "tags": note.tags,
                "created_at": note.created_at,
                "updated_at": note.updated_at,
                "preview": note.content[:200] if note.content else "",
            })

        return result

    def search_notes(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """搜索笔记。

        在标题、内容和标签中搜索关键词。

        Args:
            query: 搜索关键词。
            limit: 返回数量限制。

        Returns:
            List[Dict]: 匹配的笔记摘要列表。
        """
        query_lower = query.lower()
        matches = []

        for note in self._notes_cache.values():
            score = 0
            if query_lower in note.title.lower():
                score += 10
            if query_lower in note.content.lower():
                score += 5
            if any(query_lower in tag.lower() for tag in note.tags):
                score += 3

            if score > 0:
                matches.append((score, note))

        matches.sort(key=lambda x: x[0], reverse=True)

        result = []
        for score, note in matches[:limit]:
            # 高亮匹配的内容
            preview = note.content[:300] if note.content else ""
            result.append({
                "note_id": note.note_id,
                "title": note.title,
                "tags": note.tags,
                "updated_at": note.updated_at,
                "preview": preview,
                "relevance_score": score,
            })

        return result

    def append_content(self, note_id: str, content: str) -> Optional[Note]:
        """向现有笔记追加内容。

        Args:
            note_id: 笔记 ID。
            content: 要追加的内容。

        Returns:
            Optional[Note]: 更新后的笔记。
        """
        note = self.get_note(note_id)
        if not note:
            return None

        note.content += "\n\n" + content
        note.updated_at = time.time()
        self._save_note(note)
        logger.info("已向笔记 %s 追加内容", note_id)
        return note