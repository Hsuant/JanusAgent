"""配置加载器模块。

负责加载 agent.yaml、llm.yaml、mcp.yaml 等配置文件，
并提供统一的访问接口。
"""

import os
import re
from pathlib import Path
from typing import Any, Dict

import yaml


class ConfigLoader:
    """配置加载器。

    支持从多个 YAML 文件加载配置，并解析环境变量占位符。

    Attributes:
        config_dir: 配置文件目录路径。
    """

    def __init__(self, config_dir: str = "config") -> None:
        """初始化配置加载器。

        Args:
            config_dir: 配置文件目录路径。
        """
        self.config_dir = Path(config_dir)

    def load_agent_config(self) -> Dict[str, Any]:
        """加载 Agent 自身配置。

        Returns:
            Dict: Agent 配置字典。
        """
        return self._load_yaml("agent.yaml")

    def load_llm_config(self) -> Dict[str, Any]:
        """加载 LLM 配置。

        Returns:
            Dict: LLM 配置字典。
        """
        return self._load_yaml("llm.yaml")

    def load_mcp_config(self) -> Dict[str, Any]:
        """加载 MCP 配置。

        Returns:
            Dict: MCP 配置字典，包含 servers 列表。
        """
        return self._load_yaml("mcp.yaml")

    def load_skills_config(self) -> Dict[str, Any]:
        """加载技能配置。

        Returns:
            Dict: 技能配置字典。
        """
        return self._load_yaml("skills.yaml")

    def load_tools_config(self) -> Dict[str, Any]:
        """加载本地工具配置。

        Returns:
            Dict: 工具配置字典。
        """
        return self._load_yaml("tools.yaml")

    def load_all(self) -> Dict[str, Any]:
        """加载所有配置文件。

        Returns:
            Dict: 包含所有配置节的字典，键为配置类型（agent, llm, mcp, skills, tools）。
        """
        return {
            "agent": self.load_agent_config(),
            "llm": self.load_llm_config(),
            "mcp": self.load_mcp_config(),
            "skills": self.load_skills_config(),
            "tools": self.load_tools_config(),
        }

    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        """加载单个 YAML 文件并处理环境变量。

        Args:
            filename: YAML 文件名。

        Returns:
            Dict: 处理后的配置字典，若文件不存在则返回空字典。
        """
        file_path = self.config_dir / filename
        if not file_path.exists():
            return {}

        with open(file_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        return self._substitute_env_vars(raw)

    def _substitute_env_vars(self, config: Any) -> Any:
        """递归替换配置中的环境变量占位符。

        支持格式：${VAR_NAME} 或 ${VAR_NAME:default}。

        Args:
            config: 原始配置（可以是字典、列表、字符串等）。

        Returns:
            Any: 替换后的配置。
        """
        if isinstance(config, dict):
            return {k: self._substitute_env_vars(v) for k, v in config.items()}
        if isinstance(config, list):
            return [self._substitute_env_vars(item) for item in config]
        if isinstance(config, str):
            return self._replace_env_vars(config)
        return config

    def _replace_env_vars(self, value: str) -> str:
        """替换字符串中的环境变量占位符。

        Args:
            value: 包含占位符的字符串。

        Returns:
            str: 替换后的字符串。
        """
        pattern = r"\$\{([^}:]+)(?::([^}]*))?\}"
        matches = re.findall(pattern, value)
        if not matches:
            return value

        result = value
        for var_name, default in matches:
            env_value = os.environ.get(var_name)
            if env_value is None:
                replacement = default
            else:
                replacement = env_value
            full_match = f"${{{var_name}" + (f":{default}" if default else "") + "}"
            result = result.replace(full_match, replacement)
        return result