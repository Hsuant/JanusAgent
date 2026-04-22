"""LLM 抽象基类定义。

本模块定义了所有 LLM 提供商必须实现的统一接口，确保上层调用的一致性。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class LLMConfig:
    """LLM 配置数据类。

    用于存储单个 LLM 实例的完整配置信息，支持从字典或 YAML 文件加载。

    Attributes:
        provider: 提供商名称，如 "anthropic" 或 "openai"。
        model: 模型名称，如 "claude-sonnet-4-5-20250929"。
        base_url: API 基础 URL。
        api_key: API 密钥。
        max_tokens: 最大生成 token 数。
        temperature: 采样温度，范围 (0, 2]。
        timeout: 请求超时时间，单位秒。
        extra_params: 额外的提供商特定参数。
    """
    provider: str
    model: str
    base_url: str
    api_key: str
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: int = 120
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """LLM 响应数据类。

    封装 LLM 调用返回的统一结果格式。

    Attributes:
        content: 模型生成的文本内容。
        model: 实际使用的模型名称。
        usage: Token 使用统计，包含 prompt_tokens、completion_tokens 和 total_tokens。
        finish_reason: 完成原因，如 "stop"、"length" 等。
        raw_response: 提供商返回的原始响应数据。
    """
    content: str
    model: str
    usage: Dict[str, int]
    finish_reason: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class LLMMessage:
    """LLM 对话消息数据类。

    用于构建对话上下文，支持 system、user、assistant 三种角色。

    Attributes:
        role: 消息角色，可选 "system"、"user"、"assistant"。
        content: 消息文本内容。
    """
    role: str
    content: str


class BaseLLM(ABC):
    """LLM 抽象基类。

    所有具体的 LLM 提供商实现都必须继承此类并实现其抽象方法。
    这确保了 Agent 核心可以透明地切换不同的 LLM 后端。
    """

    def __init__(self, config: LLMConfig) -> None:
        """初始化 LLM 实例。

        Args:
            config: 包含连接和模型参数的配置对象。
        """
        self.config = config
        self._validate_config()

    def _validate_config(self) -> None:
        """验证配置的有效性。

        Raises:
            ValueError: 当必需配置项缺失或无效时抛出。
        """
        if not self.config.provider:
            raise ValueError("LLM provider 不能为空")
        if not self.config.model:
            raise ValueError("LLM model 不能为空")
        if not self.config.api_key:
            raise ValueError(f"LLM api_key 不能为空 (provider={self.config.provider})")

    @abstractmethod
    async def generate(
        self,
        messages: List[LLMMessage],
        **kwargs: Any,
    ) -> LLMResponse:
        """异步生成回复。

        Args:
            messages: 对话消息列表，按时间顺序排列。
            **kwargs: 提供商特定的额外参数，会覆盖配置中的默认值。

        Returns:
            LLMResponse: 包含生成内容和元数据的响应对象。

        Raises:
            LLMError: 当 API 调用失败时抛出。
        """
        pass

    @abstractmethod
    def generate_sync(
        self,
        messages: List[LLMMessage],
        **kwargs: Any,
    ) -> LLMResponse:
        """同步生成回复。

        该方法为便利封装，内部应调用异步方法。在非异步环境中使用。

        Args:
            messages: 对话消息列表。
            **kwargs: 提供商特定的额外参数。

        Returns:
            LLMResponse: 响应对象。
        """
        pass

    @abstractmethod
    async def stream_generate(
        self,
        messages: List[LLMMessage],
        **kwargs: Any,
    ):
        """异步流式生成回复。

        Args:
            messages: 对话消息列表。
            **kwargs: 提供商特定的额外参数。

        Yields:
            str: 流式返回的文本片段。
        """
        pass


class LLMError(Exception):
    """LLM 调用相关异常基类。

    用于统一封装不同提供商返回的错误，便于上层统一处理。
    """

    def __init__(self, message: str, provider: Optional[str] = None, cause: Optional[Exception] = None) -> None:
        """初始化 LLM 异常。

        Args:
            message: 错误描述信息。
            provider: 发生错误的提供商名称。
            cause: 原始异常对象（可选）。
        """
        super().__init__(message)
        self.provider = provider
        self.cause = cause