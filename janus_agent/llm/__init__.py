"""LLM 模块。

提供统一的 LLM 调用接口，支持多提供商、多模型和故障转移。
"""

from janus_agent.llm.base import (
    BaseLLM,
    LLMConfig,
    LLMError,
    LLMMessage,
    LLMResponse,
)
from janus_agent.llm.loader import LLMChain, LLMLoader
from janus_agent.llm.prompts import PromptManager, get_prompt_manager
from janus_agent.llm.providers import (
    AnthropicLLM,
    OpenAILLM,
    OpenAICompatibleLLM,
    LocalLLM,
)

__all__ = [
    # 基础类
    "BaseLLM",
    "LLMConfig",
    "LLMError",
    "LLMMessage",
    "LLMResponse",
    # 提供商
    "AnthropicLLM",
    "OpenAILLM",
    "OpenAICompatibleLLM",
    "LocalLLM",
    # 加载器与调用链
    "LLMLoader",
    "LLMChain",
    # 提示词管理
    "PromptManager",
    "get_prompt_manager",
]