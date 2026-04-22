"""知识库管理器。

提供 CVE 漏洞知识库的检索功能，支持关键词搜索和语义匹配。
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class CVEEntry:
    """CVE 条目数据类。

    Attributes:
        cve_id: CVE 编号，如 "CVE-2021-44228"。
        description: 漏洞描述。
        severity: 严重程度（Critical/High/Medium/Low）。
        cvss_score: CVSS 评分。
        affected_versions: 受影响版本。
        references: 参考链接列表。
        exploits: 已知利用方式。
        mitigations: 缓解措施。
    """

    def __init__(
        self,
        cve_id: str,
        description: str = "",
        severity: str = "Unknown",
        cvss_score: float = 0.0,
        affected_versions: Optional[List[str]] = None,
        references: Optional[List[str]] = None,
        exploits: Optional[List[str]] = None,
        mitigations: Optional[List[str]] = None,
    ) -> None:
        """初始化 CVE 条目。

        Args:
            cve_id: CVE 编号。
            description: 漏洞描述。
            severity: 严重程度。
            cvss_score: CVSS 评分。
            affected_versions: 受影响版本。
            references: 参考链接。
            exploits: 利用方式。
            mitigations: 缓解措施。
        """
        self.cve_id = cve_id
        self.description = description
        self.severity = severity
        self.cvss_score = cvss_score
        self.affected_versions = affected_versions or []
        self.references = references or []
        self.exploits = exploits or []
        self.mitigations = mitigations or []

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式。

        Returns:
            Dict: CVE 条目的字典表示。
        """
        return {
            "cve_id": self.cve_id,
            "description": self.description,
            "severity": self.severity,
            "cvss_score": self.cvss_score,
            "affected_versions": self.affected_versions,
            "references": self.references,
            "exploits": self.exploits,
            "mitigations": self.mitigations,
        }


class KnowledgeManager:
    """知识库管理器。

    管理 CVE 漏洞知识库的加载和检索。

    Attributes:
        knowledge_base_path: 知识库根目录路径。
        _cve_entries: CVE 条目缓存字典，键为 CVE ID。
        _search_index: 搜索索引，用于快速关键词匹配。
    """

    def __init__(self, knowledge_base_path: str = "/opt/knowledge_base") -> None:
        """初始化知识库管理器。

        Args:
            knowledge_base_path: 知识库根目录路径。
        """
        self.knowledge_base_path = Path(knowledge_base_path)
        self.knowledge_base_path.mkdir(parents=True, exist_ok=True)

        self._cve_entries: Dict[str, CVEEntry] = {}
        self._search_index: Dict[str, List[str]] = {}  # 关键词 -> CVE ID 列表
        self._load_knowledge_base()

        logger.info(
            "知识库管理器初始化完成，路径: %s，已加载 %d 条 CVE",
            self.knowledge_base_path,
            len(self._cve_entries)
        )

    def _load_knowledge_base(self) -> None:
        """加载知识库。"""
        cve_dir = self.knowledge_base_path / "cve"
        if not cve_dir.exists():
            logger.warning("CVE 知识库目录不存在: %s", cve_dir)
            return

        # 加载 JSON 索引文件
        index_file = cve_dir / "index.json"
        if index_file.exists():
            self._load_from_index(index_file)
        else:
            # 直接扫描目录
            self._scan_cve_directory(cve_dir)

        # 构建搜索索引
        self._build_search_index()

    def _load_from_index(self, index_file: Path) -> None:
        """从索引文件加载知识库。

        Args:
            index_file: 索引文件路径。
        """
        try:
            with open(index_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data.get("cves", []):
                    entry = CVEEntry(
                        cve_id=item.get("cve_id", ""),
                        description=item.get("description", ""),
                        severity=item.get("severity", "Unknown"),
                        cvss_score=item.get("cvss_score", 0.0),
                        affected_versions=item.get("affected_versions", []),
                        references=item.get("references", []),
                        exploits=item.get("exploits", []),
                        mitigations=item.get("mitigations", []),
                    )
                    self._cve_entries[entry.cve_id] = entry
            logger.info("从索引文件加载了 %d 条 CVE", len(self._cve_entries))
        except Exception as e:
            logger.error("加载索引文件失败: %s", e)

    def _scan_cve_directory(self, cve_dir: Path) -> None:
        """扫描 CVE 目录加载知识库。

        Args:
            cve_dir: CVE 目录路径。
        """
        for json_file in cve_dir.glob("*.json"):
            if json_file.name == "index.json":
                continue
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # 支持单个 CVE 或 CVE 列表
                    cve_list = data if isinstance(data, list) else [data]
                    for item in cve_list:
                        entry = CVEEntry(
                            cve_id=item.get("cve_id", item.get("id", "")),
                            description=item.get("description", ""),
                            severity=item.get("severity", "Unknown"),
                            cvss_score=item.get("cvss_score", 0.0),
                            affected_versions=item.get("affected_versions", []),
                            references=item.get("references", []),
                            exploits=item.get("exploits", []),
                            mitigations=item.get("mitigations", []),
                        )
                        if entry.cve_id:
                            self._cve_entries[entry.cve_id] = entry
            except Exception as e:
                logger.warning("加载 CVE 文件 %s 失败: %s", json_file, e)

    def _build_search_index(self) -> None:
        """构建搜索索引。"""
        self._search_index.clear()

        for cve_id, entry in self._cve_entries.items():
            # 提取关键词
            text = f"{cve_id} {entry.description}"
            words = re.findall(r"[a-zA-Z0-9\-_]+", text.lower())

            for word in set(words):
                if len(word) < 3:  # 忽略过短的关键词
                    continue
                if word not in self._search_index:
                    self._search_index[word] = []
                self._search_index[word].append(cve_id)

    def search_cve(
        self,
        query: str,
        limit: int = 10,
        min_severity: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """搜索 CVE 漏洞。

        Args:
            query: 搜索关键词，可以是 CVE 编号、产品名称或关键词。
            limit: 返回数量限制。
            min_severity: 最小严重程度过滤。

        Returns:
            List[Dict]: 匹配的 CVE 条目列表。
        """
        query_upper = query.upper()
        query_lower = query.lower()

        # 严重程度权重
        severity_weight = {
            "Critical": 10,
            "High": 8,
            "Medium": 5,
            "Low": 3,
            "Unknown": 1,
        }

        matches: List[Tuple[int, CVEEntry]] = []

        for cve_id, entry in self._cve_entries.items():
            # 严重程度过滤
            if min_severity:
                severity_order = ["Low", "Medium", "High", "Critical"]
                min_idx = severity_order.index(min_severity) if min_severity in severity_order else -1
                entry_idx = severity_order.index(entry.severity) if entry.severity in severity_order else -1
                if entry_idx < min_idx:
                    continue

            score = 0

            # 精确匹配 CVE 编号
            if query_upper == cve_id.upper():
                score += 100
            elif query_upper in cve_id.upper():
                score += 50

            # 描述匹配
            desc_lower = entry.description.lower()
            if query_lower in desc_lower:
                score += 20

            # 关键词匹配
            query_words = re.findall(r"[a-zA-Z0-9\-_]+", query_lower)
            for word in query_words:
                if len(word) >= 3 and word in desc_lower:
                    score += 5

            if score > 0:
                matches.append((score, entry))

        # 按分数排序
        matches.sort(key=lambda x: x[0], reverse=True)

        result = []
        for score, entry in matches[:limit]:
            result.append({
                **entry.to_dict(),
                "relevance_score": score,
            })

        logger.debug("搜索 CVE '%s' 返回 %d 条结果", query, len(result))
        return result

    def get_cve(self, cve_id: str) -> Optional[Dict[str, Any]]:
        """获取指定 CVE 的详细信息。

        Args:
            cve_id: CVE 编号。

        Returns:
            Optional[Dict]: CVE 条目字典，如果不存在则返回 None。
        """
        entry = self._cve_entries.get(cve_id.upper())
        if entry:
            return entry.to_dict()
        return None

    def list_recent_cves(self, limit: int = 20) -> List[Dict[str, Any]]:
        """列出最近的 CVE。

        根据 CVE 编号中的年份推断，返回最近年份的 CVE。

        Args:
            limit: 返回数量限制。

        Returns:
            List[Dict]: CVE 条目列表。
        """
        # 按 CVE 编号排序（年份越新越靠前）
        sorted_cves = sorted(
            self._cve_entries.keys(),
            key=lambda x: x.split("-")[1] if len(x.split("-")) > 1 else "0",
            reverse=True,
        )

        result = []
        for cve_id in sorted_cves[:limit]:
            entry = self._cve_entries[cve_id]
            result.append(entry.to_dict())

        return result

    def get_vulnerability_patterns(self, category: str) -> List[Dict[str, Any]]:
        """获取特定类别的漏洞模式。

        Args:
            category: 漏洞类别，如 "sql_injection", "xss", "rce"。

        Returns:
            List[Dict]: 漏洞模式列表。
        """
        category_patterns = {
            "sql_injection": ["SQL", "injection", "query", "database"],
            "xss": ["XSS", "cross-site", "script", "javascript"],
            "rce": ["remote code execution", "RCE", "command injection"],
            "lfi": ["local file inclusion", "LFI", "path traversal"],
            "csrf": ["CSRF", "cross-site request forgery"],
            "ssrf": ["SSRF", "server-side request forgery"],
            "xxe": ["XXE", "XML external entity"],
        }

        keywords = category_patterns.get(category.lower(), [category])

        matches = []
        for entry in self._cve_entries.values():
            desc_lower = entry.description.lower()
            for keyword in keywords:
                if keyword.lower() in desc_lower:
                    matches.append(entry.to_dict())
                    break

        return matches[:20]

    def search_by_product(self, product: str, version: Optional[str] = None) -> List[Dict[str, Any]]:
        """按产品搜索 CVE。

        Args:
            product: 产品名称。
            version: 版本号。

        Returns:
            List[Dict]: 匹配的 CVE 列表。
        """
        product_lower = product.lower()
        version_lower = version.lower() if version else None

        matches = []
        for entry in self._cve_entries.values():
            desc_lower = entry.description.lower()
            if product_lower not in desc_lower:
                continue

            if version_lower:
                version_match = False
                for affected in entry.affected_versions:
                    if version_lower in affected.lower():
                        version_match = True
                        break
                if not version_match:
                    continue

            matches.append(entry.to_dict())

        return matches[:20]