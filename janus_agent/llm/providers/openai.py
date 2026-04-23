"""OpenAI API 提供商实现。

提供对 OpenAI GPT 系列模型以及兼容 OpenAI 格式的第三方服务的访问能力。
"""

import asyncio
import json
from typing import Any, Dict, List, Optional

import httpx

from janus_agent.llm.base import BaseLLM, LLMConfig, LLMError, LLMResponse


class OpenAILLM(BaseLLM):
    """OpenAI GPT LLM 实现。

    使用 OpenAI Chat Completions API 进行对话补全。
    支持 GPT-3.5、GPT-4、GPT-4o 等系列模型，也兼容 vLLM、LocalAI 等兼容服务。
    """

    def __init__(self, config: LLMConfig) -> None:
        """初始化 OpenAI LLM 客户端。

        Args:
            config: LLM 配置对象，provider 必须为 "openai"。
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
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(self.config.timeout),
            )
        return self._client

    async def _close_client(self) -> None:
        """关闭 HTTP 客户端连接。"""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "OpenAILLM":
        """异步上下文管理器入口。"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口，自动关闭连接。"""
        await self._close_client()

    async def generate(
        self,
        messages: List[Dict[str, str]],
        **kwargs: Any,
    ) -> LLMResponse:
        """异步生成回复。

        Args:
            messages: 标准字典消息列表，每条包含 "role" 和 "content"。
            **kwargs: 可覆盖配置参数，如 temperature、max_tokens。

        Returns:
            LLMResponse: 生成结果。

        Raises:
            LLMError: API 调用失败或返回错误时抛出。
        """
        client = self._get_client()

        # 构建请求体（消息格式已符合 OpenAI 要求）
        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
        }

        # 合并额外参数
        payload.update(self.config.extra_params)
        payload.update({k: v for k, v in kwargs.items() if k not in ("max_tokens", "temperature")})

        try:
            response = await client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            raise LLMError(
                f"OpenAI API 返回错误状态码 {e.response.status_code}: {e.response.text}",
                provider="openai",
                cause=e,
            ) from e
        except httpx.RequestError as e:
            raise LLMError(f"OpenAI API 请求失败: {str(e)}", provider="openai", cause=e) from e

        # 解析响应
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
            usage = {
                "prompt_tokens": data.get("usage", {}).get("prompt_tokens", 0),
                "completion_tokens": data.get("usage", {}).get("completion_tokens", 0),
                "total_tokens": data.get("usage", {}).get("total_tokens", 0),
            }
            return LLMResponse(
                content=content,
                model=data.get("model", self.config.model),
                usage=usage,
                finish_reason=choice.get("finish_reason"),
                raw_response=data,
            )
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"解析 OpenAI 响应失败: {str(e)}", provider="openai", cause=e) from e

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

        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
            "stream": True,
        }

        try:
            async with client.stream("POST", "/chat/completions", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            event = json.loads(data_str)
                            delta = event.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
        except httpx.HTTPStatusError as e:
            raise LLMError(
                f"OpenAI 流式请求错误 {e.response.status_code}: {e.response.text}",
                provider="openai",
                cause=e,
            ) from e
        except httpx.RequestError as e:
            raise LLMError(f"OpenAI 流式请求失败: {str(e)}", provider="openai", cause=e) from e