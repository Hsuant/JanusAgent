"""提示词模块。

提供从 Markdown 文件加载提示词模板的功能。
"""

from pathlib import Path
from typing import Dict, Optional


class PromptManager:
    """提示词管理器。

    负责加载和管理各类提示词模板，支持变量替换。
    """

    def __init__(self, prompts_dir: Optional[str] = None) -> None:
        """初始化提示词管理器。

        Args:
            prompts_dir: 提示词文件所在目录，默认为当前文件所在目录。
        """
        if prompts_dir is None:
            prompts_dir = str(Path(__file__).parent)
        self.prompts_dir = Path(prompts_dir)
        self._cache: Dict[str, str] = {}

    def load_prompt(self, name: str) -> str:
        """加载指定名称的提示词。

        Args:
            name: 提示词文件名（不含 .md 扩展名），如 "pentest_agent"。

        Returns:
            str: 提示词内容。

        Raises:
            FileNotFoundError: 文件不存在时抛出。
        """
        if name in self._cache:
            return self._cache[name]

        prompt_file = self.prompts_dir / f"{name}.md"
        if not prompt_file.exists():
            raise FileNotFoundError(f"提示词文件不存在: {prompt_file}")

        with open(prompt_file, "r", encoding="utf-8") as f:
            content = f.read()

        self._cache[name] = content
        return content

    def get_pentest_agent_prompt(self) -> str:
        """获取渗透测试 Agent 的系统提示词。

        Returns:
            str: 系统提示词。
        """
        return self.load_prompt("pentest_agent")

    def get_task_planner_prompt(self) -> str:
        """获取任务规划提示词模板。

        Returns:
            str: 规划提示词模板，包含 JSON 格式说明。
        """
        return self.load_prompt("task_planner")


# 全局单例
_default_manager: Optional[PromptManager] = None


def get_prompt_manager() -> PromptManager:
    """获取全局提示词管理器单例。

    Returns:
        PromptManager: 提示词管理器实例。
    """
    global _default_manager
    if _default_manager is None:
        _default_manager = PromptManager()
    return _default_manager


__all__ = ["PromptManager", "get_prompt_manager"]