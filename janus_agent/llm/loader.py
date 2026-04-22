"""LLM 配置加载器与工厂类。

负责从 YAML 配置文件加载 LLM 配置，并实例化相应的提供商对象。
支持主模型和备选模型的多层配置。
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

import yaml

from janus_agent.llm.base import BaseLLM, LLMConfig, LLMError
from janus_agent.llm.providers import AnthropicLLM, OpenAILLM, OpenAICompatibleLLM, LocalLLM


class LLMLoader:
    """LLM 配置加载器与工厂。

    负责：
    1. 从 YAML 文件加载 LLM 配置。
    2. 解析环境变量占位符。
    3. 创建 LLM 实例，支持主模型和备选模型链。
    """

    # 提供商名称到类实现的映射
    PROVIDER_MAP: Dict[str, Type[BaseLLM]] = {
        "anthropic": AnthropicLLM,
        "openai": OpenAILLM,
        "openai_compatible": OpenAICompatibleLLM,
        "localhost": LocalLLM,
    }

    def __init__(self, config_path: Optional[str] = None) -> None:
        """初始化加载器。

        Args:
            config_path: LLM 配置文件路径，默认为项目根目录下的 config/llm.yaml。
        """
        if config_path is None:
            # 默认配置文件路径：项目根目录/config/llm.yaml
            project_root = Path(__file__).parent.parent.parent
            config_path = str(project_root / "config" / "llm.yaml")
        self.config_path = config_path
        self._raw_config: Optional[Dict[str, Any]] = None
        self._primary_config: Optional[LLMConfig] = None
        self._fallback_configs: List[LLMConfig] = []
        self._defaults: Dict[str, Any] = {}

    def _substitute_env_vars(self, value: str) -> str:
        """替换字符串中的环境变量占位符。

        支持两种格式：
        - ${VAR_NAME}：必须存在，否则抛出异常。
        - ${VAR_NAME:default}：若环境变量不存在则使用默认值。

        Args:
            value: 包含占位符的原始字符串。

        Returns:
            str: 替换后的字符串。

        Raises:
            ValueError: 当必须的环境变量未设置时抛出。
        """
        if not isinstance(value, str):
            return value

        pattern = r"\$\{([^}:]+)(?::([^}]*))?\}"
        matches = re.findall(pattern, value)
        if not matches:
            return value

        result = value
        for var_name, default in matches:
            env_value = os.environ.get(var_name)
            if env_value is None:
                if default is not None:
                    replacement = default
                else:
                    raise ValueError(
                        f"必需的环境变量 {var_name} 未设置，且没有提供默认值"
                    )
            else:
                replacement = env_value
            # 替换完整占位符
            full_match = f"${{{var_name}" + (f":{default}" if default is not None else "") + "}"
            result = result.replace(full_match, replacement)
        return result

    def _process_config_dict(self, config_dict: Dict[str, Any]) -> Dict[str, Any]:
        """递归处理配置字典，替换其中的环境变量占位符。

        Args:
            config_dict: 原始配置字典。

        Returns:
            Dict[str, Any]: 替换后的配置字典。
        """
        processed = {}
        for key, value in config_dict.items():
            if isinstance(value, str):
                processed[key] = self._substitute_env_vars(value)
            elif isinstance(value, dict):
                processed[key] = self._process_config_dict(value)
            elif isinstance(value, list):
                processed[key] = [
                    self._process_config_dict(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                processed[key] = value
        return processed

    def load(self) -> None:
        """加载并解析 YAML 配置文件。

        Raises:
            FileNotFoundError: 配置文件不存在时抛出。
            yaml.YAMLError: YAML 格式错误时抛出。
            ValueError: 配置内容无效时抛出。
        """
        config_path = Path(self.config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"LLM 配置文件不存在: {self.config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            try:
                raw = yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise yaml.YAMLError(f"解析 YAML 配置文件失败: {e}") from e

        if not raw:
            raise ValueError("LLM 配置文件内容为空")

        # 处理环境变量替换
        self._raw_config = self._process_config_dict(raw)

        # 提取全局默认值
        self._defaults = self._raw_config.get("defaults", {})

        # 解析主模型配置
        primary_raw = self._raw_config.get("primary")
        if not primary_raw:
            raise ValueError("配置文件中缺少 'primary' 主模型配置")
        self._primary_config = self._build_llm_config(primary_raw)

        # 解析备选模型配置
        fallbacks_raw = self._raw_config.get("fallbacks", [])
        self._fallback_configs = [
            self._build_llm_config(fb) for fb in fallbacks_raw
        ]

    def _build_llm_config(self, raw_config: Dict[str, Any]) -> LLMConfig:
        """从原始字典构建 LLMConfig 对象。

        Args:
            raw_config: 单个模型的原始配置字典。

        Returns:
            LLMConfig: 配置数据类实例。

        Raises:
            ValueError: 缺少必需字段时抛出。
        """
        required_fields = ["provider", "model", "base_url", "api_key"]
        for field in required_fields:
            if field not in raw_config:
                raise ValueError(f"LLM 配置缺少必需字段: {field}")

        # 使用默认值填充可选字段
        max_tokens = raw_config.get("max_tokens", self._defaults.get("max_tokens", 4096))
        temperature = raw_config.get("temperature", 0.7)
        timeout = raw_config.get("timeout", self._defaults.get("request_timeout", 120))

        # 提取额外参数（除标准字段外的所有字段）
        standard_fields = {"provider", "model", "base_url", "api_key", "max_tokens", "temperature", "timeout"}
        extra_params = {k: v for k, v in raw_config.items() if k not in standard_fields}

        return LLMConfig(
            provider=raw_config["provider"],
            model=raw_config["model"],
            base_url=raw_config["base_url"],
            api_key=raw_config["api_key"],
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
            extra_params=extra_params,
        )

    def create_primary_llm(self) -> BaseLLM:
        """创建主 LLM 实例。

        Returns:
            BaseLLM: 主模型实例。

        Raises:
            LLMError: 配置未加载或提供商不支持时抛出。
        """
        if self._primary_config is None:
            self.load()
        return self._create_llm_from_config(self._primary_config)  # type: ignore

    def create_fallback_llms(self) -> List[BaseLLM]:
        """创建所有备选 LLM 实例。

        Returns:
            List[BaseLLM]: 备选模型实例列表。
        """
        if self._primary_config is None:
            self.load()
        return [self._create_llm_from_config(cfg) for cfg in self._fallback_configs]

    def _create_llm_from_config(self, config: LLMConfig) -> BaseLLM:
        """根据配置实例化 LLM 对象。

        Args:
            config: LLM 配置对象。

        Returns:
            BaseLLM: 实例化后的 LLM 对象。

        Raises:
            LLMError: 当提供商不支持时抛出。
        """
        provider_class = self.PROVIDER_MAP.get(config.provider.lower())
        if provider_class is None:
            supported = ", ".join(self.PROVIDER_MAP.keys())
            raise LLMError(
                f"不支持的 LLM 提供商: {config.provider}，当前支持: {supported}"
            )
        return provider_class(config)

    def create_llm_chain(self) -> "LLMChain":
        """创建包含主模型和备选模型的调用链。

        该调用链会在主模型失败时自动尝试备选模型。

        Returns:
            LLMChain: LLM 调用链对象。
        """
        if self._primary_config is None:
            self.load()
        primary = self.create_primary_llm()
        fallbacks = self.create_fallback_llms()
        return LLMChain(
            primary=primary,
            fallbacks=fallbacks,
            max_retries=self._defaults.get("max_retries", 3),
            retry_delay=self._defaults.get("retry_delay", 1.0),
        )


class LLMChain:
    """LLM 调用链。

    封装主模型和备选模型的调用逻辑，提供统一的生成接口。
    当主模型调用失败时，会自动依次尝试备选模型。
    """

    def __init__(
        self,
        primary: BaseLLM,
        fallbacks: List[BaseLLM],
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        """初始化 LLM 调用链。

        Args:
            primary: 主 LLM 实例。
            fallbacks: 备选 LLM 实例列表，按优先级排序。
            max_retries: 单个模型的最大重试次数。
            retry_delay: 重试间隔时间（秒）。
        """
        self.primary = primary
        self.fallbacks = fallbacks
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    async def generate(
        self,
        messages: List[Any],
        **kwargs: Any,
    ) -> Any:
        """异步生成回复，自动处理故障转移。

        执行顺序：
        1. 尝试主模型，最多重试 max_retries 次。
        2. 主模型失败后，依次尝试备选模型，每个备选模型最多重试一次。
        3. 所有模型都失败则抛出异常。

        Args:
            messages: 对话消息列表（LLMMessage 列表）。
            **kwargs: 传递给具体模型的参数。

        Returns:
            LLMResponse: 生成结果。

        Raises:
            LLMError: 所有模型均调用失败时抛出。
        """
        import asyncio

        models_to_try = [self.primary] + self.fallbacks
        last_error: Optional[Exception] = None

        for idx, llm in enumerate(models_to_try):
            retries = self.max_retries if idx == 0 else 1  # 主模型多次重试，备选模型只试一次
            for attempt in range(retries):
                try:
                    return await llm.generate(messages, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < retries - 1:
                        await asyncio.sleep(self.retry_delay)
                        continue
                    # 记录失败，尝试下一个模型
                    break

        raise LLMError(
            f"所有 LLM 模型调用均失败，最后一个错误: {str(last_error)}"
        ) from last_error

    def generate_sync(
        self,
        messages: List[Any],
        **kwargs: Any,
    ) -> Any:
        """同步生成回复。

        Args:
            messages: 对话消息列表。
            **kwargs: 传递给具体模型的参数。

        Returns:
            LLMResponse: 生成结果。
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                raise RuntimeError(
                    "在运行中的事件循环里无法使用同步方法，请改用异步方法 generate()"
                )
            return loop.run_until_complete(self.generate(messages, **kwargs))
        except RuntimeError:
            return asyncio.run(self.generate(messages, **kwargs))