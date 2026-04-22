"""工具库配置管理。

支持从 YAML 文件、环境变量和字典加载配置，并提供默认值。
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from tools.exceptions import ConfigurationError


@dataclass
class BrowserConfig:
    """浏览器工具配置。

    Attributes:
        headless: 是否使用无头模式。
        default_timeout: 默认超时时间（毫秒）。
        viewport_width: 视口宽度。
        viewport_height: 视口高度。
        user_agent: 自定义 User-Agent，为空则使用默认。
    """

    headless: bool = True
    default_timeout: int = 30000
    viewport_width: int = 1280
    viewport_height: int = 720
    user_agent: str = ""


@dataclass
class TerminalConfig:
    """终端工具配置。

    Attributes:
        session_name_prefix: 会话名称前缀。
        default_shell: 默认 Shell 命令。
        command_timeout: 命令执行超时时间（秒）。
        max_output_lines: 最大输出行数限制。
    """

    session_name_prefix: str = "aegiscracker_"
    default_shell: str = "/bin/bash"
    command_timeout: int = 60
    max_output_lines: int = 500


@dataclass
class NoteConfig:
    """笔记工具配置。

    Attributes:
        storage_path: 笔记存储目录路径。
        auto_save: 是否自动保存。
        index_enabled: 是否启用全文索引。
    """

    storage_path: str = "./notes"
    auto_save: bool = True
    index_enabled: bool = True


@dataclass
class ExecutorConfig:
    """代码执行器配置。

    Attributes:
        kernel_name: Jupyter 内核名称。
        max_sessions: 最大并发会话数。
        execution_timeout: 代码执行超时时间（秒）。
        session_timeout: 会话空闲超时时间（秒）。
        workspace_path: 工作目录路径。
    """

    kernel_name: str = "python3"
    max_sessions: int = 5
    execution_timeout: int = 30
    session_timeout: int = 3600
    workspace_path: str = "./workspace"


@dataclass
class ToolsetConfig:
    """工具库总配置。

    Attributes:
        browser: 浏览器配置。
        terminal: 终端配置。
        note: 笔记配置。
        executor: 代码执行器配置。
        debug: 是否开启调试模式。
    """

    browser: BrowserConfig = field(default_factory=BrowserConfig)
    terminal: TerminalConfig = field(default_factory=TerminalConfig)
    note: NoteConfig = field(default_factory=NoteConfig)
    executor: ExecutorConfig = field(default_factory=ExecutorConfig)
    debug: bool = False


class ConfigLoader:
    """配置加载器。

    支持从多种来源加载配置，优先级从高到低：
    1. 直接传入的字典参数
    2. 环境变量
    3. YAML 配置文件
    4. 默认值
    """

    # 环境变量映射
    ENV_MAPPING = {
        "BROWSER_HEADLESS": "browser.headless",
        "BROWSER_TIMEOUT": "browser.default_timeout",
        "NOTE_STORAGE_PATH": "note.storage_path",
        "EXECUTOR_WORKSPACE": "executor.workspace_path",
        "TOOLSET_DEBUG": "debug",
    }

    @classmethod
    def from_yaml(cls, path: Optional[str] = None) -> ToolsetConfig:
        """从 YAML 文件加载配置。

        Args:
            path: 配置文件路径，默认为当前目录下的 config.yaml。

        Returns:
            ToolsetConfig: 配置对象。

        Raises:
            ConfigurationError: 配置文件不存在或格式错误。
        """
        if path is None:
            path = os.environ.get("TOOLSET_CONFIG", "./toolset.yaml")

        config_path = Path(path)
        if not config_path.exists():
            # 没有配置文件时返回默认配置
            return cls.from_defaults()

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ConfigurationError(f"解析 YAML 配置文件失败: {e}") from e
        except IOError as e:
            raise ConfigurationError(f"读取配置文件失败: {e}") from e

        return cls.from_dict(data)

    @classmethod
    def from_env(cls, base_config: Optional[ToolsetConfig] = None) -> ToolsetConfig:
        """从环境变量覆盖配置。

        Args:
            base_config: 基础配置对象，如果为 None 则使用默认配置。

        Returns:
            ToolsetConfig: 覆盖后的配置对象。
        """
        config = base_config or cls.from_defaults()

        # 将配置对象转换为纯字典（递归转换子配置对象）
        config_dict = {
            'browser': config.browser.__dict__.copy() if config.browser else {},
            'terminal': config.terminal.__dict__.copy() if config.terminal else {},
            'note': config.note.__dict__.copy() if config.note else {},
            'executor': config.executor.__dict__.copy() if config.executor else {},
            'debug': config.debug,
        }

        for env_var, config_path in cls.ENV_MAPPING.items():
            value = os.environ.get(env_var)
            if value is not None:
                cls._set_nested_value(config_dict, config_path, value)

        return cls.from_dict(config_dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ToolsetConfig:
        """从字典构建配置。

        Args:
            data: 配置字典。

        Returns:
            ToolsetConfig: 配置对象。
        """
        config = ToolsetConfig()

        # 浏览器配置
        if "browser" in data:
            browser_data = data["browser"]
            config.browser = BrowserConfig(
                headless=browser_data.get("headless", config.browser.headless),
                default_timeout=browser_data.get("default_timeout", config.browser.default_timeout),
                viewport_width=browser_data.get("viewport_width", config.browser.viewport_width),
                viewport_height=browser_data.get("viewport_height", config.browser.viewport_height),
                user_agent=browser_data.get("user_agent", config.browser.user_agent),
            )

        # 终端配置
        if "terminal" in data:
            term_data = data["terminal"]
            config.terminal = TerminalConfig(
                session_name_prefix=term_data.get("session_name_prefix", config.terminal.session_name_prefix),
                default_shell=term_data.get("default_shell", config.terminal.default_shell),
                command_timeout=term_data.get("command_timeout", config.terminal.command_timeout),
                max_output_lines=term_data.get("max_output_lines", config.terminal.max_output_lines),
            )

        # 笔记配置
        if "note" in data:
            note_data = data["note"]
            config.note = NoteConfig(
                storage_path=note_data.get("storage_path", config.note.storage_path),
                auto_save=note_data.get("auto_save", config.note.auto_save),
                index_enabled=note_data.get("index_enabled", config.note.index_enabled),
            )

        # 执行器配置
        if "executor" in data:
            exec_data = data["executor"]
            config.executor = ExecutorConfig(
                kernel_name=exec_data.get("kernel_name", config.executor.kernel_name),
                max_sessions=exec_data.get("max_sessions", config.executor.max_sessions),
                execution_timeout=exec_data.get("execution_timeout", config.executor.execution_timeout),
                session_timeout=exec_data.get("session_timeout", config.executor.session_timeout),
                workspace_path=exec_data.get("workspace_path", config.executor.workspace_path),
            )

        if "debug" in data:
            config.debug = bool(data["debug"])

        return config

    @classmethod
    def from_defaults(cls) -> ToolsetConfig:
        """返回默认配置。

        Returns:
            ToolsetConfig: 默认配置对象。
        """
        return ToolsetConfig()

    @classmethod
    def _set_nested_value(cls, data: Dict[str, Any], path: str, value: str) -> None:
        """设置嵌套字典的值。

        Args:
            data: 目标字典。
            path: 点分隔的路径，如 "browser.headless"。
            value: 要设置的值（字符串，会自动转换类型）。
        """
        parts = path.split(".")
        current = data

        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]

        # 尝试转换值类型
        converted_value = cls._convert_value(value)
        current[parts[-1]] = converted_value

    @staticmethod
    def _convert_value(value: str) -> Any:
        """将字符串值转换为适当的类型。

        Args:
            value: 字符串值。

        Returns:
            Any: 转换后的值（bool、int、float 或保持 str）。
        """
        lower_value = value.lower()
        if lower_value in ("true", "yes", "1"):
            return True
        if lower_value in ("false", "no", "0"):
            return False
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value


# 全局配置单例
_global_config: Optional[ToolsetConfig] = None


def get_config(reload: bool = False) -> ToolsetConfig:
    """获取全局配置单例。

    Args:
        reload: 是否强制重新加载配置。

    Returns:
        ToolsetConfig: 全局配置对象。
    """
    global _global_config
    if _global_config is None or reload:
        _global_config = ConfigLoader.from_env(ConfigLoader.from_yaml())
    return _global_config


def set_config(config: ToolsetConfig) -> None:
    """设置全局配置。

    Args:
        config: 配置对象。
    """
    global _global_config
    _global_config = config