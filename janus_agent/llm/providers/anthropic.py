"""Anthropic Claude API 提供商实现。

提供对 Anthropic Claude 系列模型的访问能力。
"""

import asyncio
import json
from typing import Any, Dict, List, Optional

import httpx

from janus_agent.llm.base import BaseLLM, LLMConfig, LLMError, LLMResponse


class AnthropicLLM(BaseLLM):
    """Anthropic Claude LLM 实现。

    使用 Anthropic 官方 Messages API 进行对话补全。
    支持 Claude 3/3.5/4 系列模型。
    """

    def __init__(self, config: LLMConfig) -> None:
        """初始化 Anthropic LLM 客户端。

        Args:
            config: LLM 配置对象，provider 必须为 "anthropic"。
        """
        super().__init__(config)
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 异步客户端。

        Returns:
            httpx.AsyncClient: 配置好认证头和超时设置的客户端实例。
        """
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url.rstrip("/"),
                headers={
                    "x-api-key": self.config.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                timeout=httpx.Timeout(self.config.timeout),
            )
        return self._client

    async def _close_client(self) -> None:
        """关闭 HTTP 客户端连接。"""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "AnthropicLLM":
        """异步上下文管理器入口。"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口，自动关闭连接。"""
        await self._close_client()

    def _convert_messages(self, messages: List[Dict[str, str]]) -> tuple[Optional[str], List[Dict[str, Any]]]:
        """将字典格式消息转换为 Anthropic API 要求的格式。

        Anthropic 要求 system 提示词作为顶层参数，而非常规消息。
        同时消息中不能有 system 角色。

        Args:
            messages: 标准字典消息列表，每个元素包含 "role" 和 "content"。

        Returns:
            tuple[Optional[str], List[Dict]]: 包含 system 提示词和转换后的消息列表。
        """
        system_prompt = None
        converted = []
        for msg in messages:
            if msg["role"] == "system":
                # 如果有多个 system 消息，取最后一个
                system_prompt = msg["content"]
            else:
                converted.append({"role": msg["role"], "content": msg["content"]})
        return system_prompt, converted

    async def generate(
        self,
        messages: List[Dict[str, str]],
        **kwargs: Any,
    ) -> LLMResponse:
        """异步生成回复。

        Args:
            messages: 标准字典消息列表。
            **kwargs: 可覆盖配置参数，如 temperature、max_tokens。

        Returns:
            LLMResponse: 生成结果。

        Raises:
            LLMError: API 调用失败或返回错误时抛出。
        """
        client = self._get_client()
        system_prompt, api_messages = self._convert_messages(messages)

        # 构建请求体
        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": api_messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
        }
        if system_prompt:
            payload["system"] = system_prompt

        # 合并额外参数
        payload.update(self.config.extra_params)
        payload.update({k: v for k, v in kwargs.items() if k not in ("max_tokens", "temperature")})

        try:
            response = await client.post("/v1/messages", json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            raise LLMError(
                f"Anthropic API 返回错误状态码 {e.response.status_code}: {e.response.text}",
                provider="anthropic",
                cause=e,
            ) from e
        except httpx.RequestError as e:
            raise LLMError(f"Anthropic API 请求失败: {str(e)}", provider="anthropic", cause=e) from e

        # 解析响应
        try:
            content_blocks = data.get("content", [])
            text_content = ""
            for block in content_blocks:
                if block.get("type") == "text":
                    text_content += block.get("text", "")

            usage = {
                "prompt_tokens": data.get("usage", {}).get("input_tokens", 0),
                "completion_tokens": data.get("usage", {}).get("output_tokens", 0),
                "total_tokens": data.get("usage", {}).get("input_tokens", 0) + data.get("usage", {}).get("output_tokens", 0),
            }
            return LLMResponse(
                content=text_content,
                model=data.get("model", self.config.model),
                usage=usage,
                finish_reason=data.get("stop_reason"),
                raw_response=data,
            )
        except (KeyError, TypeError) as e:
            raise LLMError(f"解析 Anthropic 响应失败: {str(e)}", provider="anthropic", cause=e) from e

    def generate_sync(
        self,
        messages: List[Dict[str, str]],
        **kwargs: Any,
    ) -> LLMResponse:
        """同步生成回复。

        Args:
            messages: 标准字典消息列表。
            **kwargs: 可覆盖配置参数。

        Returns:
            LLMResponse: 生成结果。
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                raise RuntimeError(
                    "在运行中的事件循环里无法使用同步方法，请改用异步方法 generate()"
                )
            return loop.run_until_complete(self.generate(messages, **kwargs))
        except RuntimeError:
            return asyncio.run(self.generate(messages, **kwargs))

    async def stream_generate(
        self,
        messages: List[Dict[str, str]],
        **kwargs: Any,
    ):
        """异步流式生成回复。

        Args:
            messages: 标准字典消息列表。
            **kwargs: 可覆盖配置参数。

        Yields:
            str: 流式文本片段。
        """
        client = self._get_client()
        system_prompt, api_messages = self._convert_messages(messages)

        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": api_messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
            "stream": True,
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            async with client.stream("POST", "/v1/messages", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            event = json.loads(data_str)
                            if event.get("type") == "content_block_delta":
                                delta = event.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    yield delta.get("text", "")
                        except json.JSONDecodeError:
                            continue
        except httpx.HTTPStatusError as e:
            raise LLMError(
                f"Anthropic 流式请求错误 {e.response.status_code}: {e.response.text}",
                provider="anthropic",
                cause=e,
            ) from e
        except httpx.RequestError as e:
            raise LLMError(f"Anthropic 流式请求失败: {str(e)}", provider="anthropic", cause=e) from e